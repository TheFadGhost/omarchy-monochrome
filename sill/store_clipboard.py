"""Sill clipboard store — a READ-MOSTLY renderer of Omarchy's private store.

THE ARCHITECTURE RULE (sill-plan §0/#3): Sill never runs its own
`wl-paste --watch`. Omarchy's Quickshell clipboard plugin owns the two
capture watchers (Clipboard.qml starts them with pdeathsig and resurrects
them); a second reader would race for the same selection and be another
chance to snapshot a secret. Sill only *reads*
~/.local/state/omarchy/clipboard-history.json — private, undocumented state
with no stability contract, hence the schema guard below.

Entry shape (ClipboardHistory.js::normalizeEntry, ported):
    {type:"text", text}                                — no timestamp at all
    {type:"image", path, mime, capturedAt}             — capturedAt is a
        DISPLAY STRING ("Tuesday 03:45"), not a timestamp.
Real times therefore come from: image file mtimes, plus a sidecar
~/.local/share/sill/seen.json mapping content-key hash -> first-seen epoch
for text entries. Without that, TTL maths would be fiction.

The only writes to Omarchy's store — deliberate, bounded (plan §4):
  * reactive denylist deletion (a just-captured entry whose source window
    class is denylisted),
  * TTL prune + orphan-image prune,
  * purge.
All read-modify-os.replace, milliseconds wide. The theoretical race with the
Quickshell writer can lose at most one concurrent capture — accepted and
documented, in exchange for not forking Omarchy's pacman-owned pipeline.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HOME = os.path.expanduser("~")
STATE_DIR = (os.environ.get("SILL_CLIP_STATE_DIR")  # test seam only
             or os.path.join(os.environ.get("XDG_STATE_HOME")
                             or os.path.join(HOME, ".local/state"), "omarchy"))
STORE = os.path.join(STATE_DIR, "clipboard-history.json")
IMAGE_DIR = os.path.join(STATE_DIR, "clipboard-images")
SEEN = (os.environ.get("SILL_SEEN_FILE")            # test seam only
        or os.path.join(HOME, ".local/share/sill/seen.json"))

# Orphan images are unreachable by ANY consumer (no JSON entry references
# them), so they are pruned even when max_age_days=0 — but only past this
# fallback age, and never younger than the 24 h grace window that protects
# an in-flight capture whose JSON entry hasn't landed yet.
ORPHAN_FALLBACK_DAYS = 7
GRACE_S = 24 * 3600


# ---------------------------------------------------------------- entries

class Entry(dict):
    """Normalised store entry + derived real timestamp.
    kind text : payload = the text itself
    kind image: payload = absolute file path"""

    @property
    def kind(self):
        return self["kind"]

    @property
    def payload(self):
        return self["payload"]

    @property
    def when(self):
        return self["when"]

    @property
    def key(self):
        # Mirrors ClipboardHistory.js::entryKey — dedupe identity.
        if self["kind"] == "image":
            return "image:" + self["payload"]
        return "text:" + self["payload"]


def normalize(value):
    """Python port of ClipboardHistory.js::normalizeEntry. Tolerant: bare
    strings are text, unknown types are skipped, capturedAt is optional and
    kept only as a display string."""
    if isinstance(value, str):
        return Entry(kind="text", payload=value, when=0.0,
                     display_at="") if value.strip() else None
    if not isinstance(value, dict):
        return None
    typ = str(value.get("type") or value.get("kind") or "")
    if typ == "text":
        text = value.get("text")
        text = text if isinstance(text, str) else str(text or "")
        if not text.strip():
            return None
        return Entry(kind="text", payload=text, when=0.0, display_at="")
    if typ == "image":
        path = value.get("path")
        path = path if isinstance(path, str) else str(path or "")
        if not path:
            return None
        return Entry(kind="image", payload=path,
                     mime=str(value.get("mime") or "image/png"),
                     when=0.0,
                     display_at=str(value.get("capturedAt") or ""))
    return None


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:24]


# ---------------------------------------------------------------- sidecar

def _load_seen() -> dict:
    try:
        with open(SEEN, encoding="utf-8") as f:
            raw = json.load(f)
        return {k: float(v) for k, v in raw.items()
                if isinstance(k, str) and isinstance(v, (int, float))}
    except (OSError, ValueError):
        return {}


def _save_seen(seen: dict):
    d = os.path.dirname(SEEN)
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".seen-")
    try:
        os.write(fd, json.dumps(seen).encode())
    finally:
        os.close(fd)
    os.replace(tmp, SEEN)
    try:
        os.chmod(SEEN, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------- writes

def _write_store_raw(raw_list):
    """Atomic write in Omarchy's own on-disk format (2-space indent + \\n,
    matching Clipboard.qml saveHistory) so a diff of the file stays sane."""
    d = os.path.dirname(STORE)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".clip-")
    try:
        os.write(fd, (json.dumps(raw_list, indent=2) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, STORE)
    try:
        os.chmod(STORE, 0o600)
    except OSError:
        pass


def purge():
    """Wipe clipboard history: store -> [], images dir emptied, sidecar
    cleared. Pins are a separate store and are untouched by design.
    GTK-free: callable from the CLI without an app instance."""
    _write_store_raw([])
    try:
        for name in os.listdir(IMAGE_DIR):
            try:
                os.remove(os.path.join(IMAGE_DIR, name))
            except OSError:
                pass
    except OSError:
        pass
    _save_seen({})


# ---------------------------------------------------------------- store

class ClipStore:
    """In-memory model + schema guard state machine.

    state: "ok" | "missing" | "unreadable" | "drift"
    On unreadable/drift the last-good snapshot is kept IN MEMORY only —
    persisting it would duplicate secrets past a purge (plan §4)."""

    def __init__(self, denylist=()):
        self.entries: list[Entry] = []
        self.state = "ok"
        self.raw_count = 0
        self.recognised_count = 0
        self.denylist = list(denylist)
        self.on_change = None          # UI callback, set by the tab
        self._seen = _load_seen()
        self._known_keys = set()       # keys ever seen this session
        self._monitor = None
        self._debounce = 0
        self._retry_pending = False

    # ------------------------------------------------ load & guard
    def load(self, initial=False):
        """Read + normalise the store. Returns True if a parse retry should
        be scheduled (mid-write torn read)."""
        try:
            with open(STORE, encoding="utf-8") as f:
                raw_text = f.read()
        except FileNotFoundError:
            self.state = "missing"
            self.entries = []
            self.raw_count = self.recognised_count = 0
            return False
        except OSError:
            self.state = "unreadable"
            return False

        try:
            raw = json.loads(raw_text)
        except ValueError:
            if not self._retry_pending:
                return True            # ask caller to retry once in 250 ms
            self.state = "unreadable"  # retried and still torn: keep last-good
            return False

        if not isinstance(raw, list):
            self.state = "drift"
            self.raw_count, self.recognised_count = 1, 0
            return False

        entries = []
        for item in raw:
            e = normalize(item)
            if e is not None:
                entries.append(e)
        self.raw_count = len(raw)
        self.recognised_count = len(entries)
        if raw and not entries:
            self.state = "drift"       # parses, recognises nothing: keep last-good
            return False

        self.state = "ok"
        self._stamp(entries, initial)
        self.entries = entries
        self._harden_perms()
        if not initial:
            self._apply_denylist()
        self._known_keys.update(e.key for e in self.entries)
        return False

    def _stamp(self, entries, initial):
        """Derive real timestamps: image file mtime; text via the first-seen
        sidecar (recorded now when new — conservative: an entry is never
        older than the first time Sill saw it)."""
        now = time.time()
        seen = self._seen
        live_keys = set()
        dirty = False
        for e in entries:
            kh = _key_hash(e.key)
            live_keys.add(kh)
            if e.kind == "image":
                try:
                    e["when"] = os.path.getmtime(e.payload)
                except OSError:
                    e["when"] = 0.0    # dead image: ancient -> TTL clears it
                continue
            if kh not in seen:
                seen[kh] = now
                dirty = True
            e["when"] = seen[kh]
        # Sidecar pruned WITH the store: drop hashes for departed entries.
        for kh in [k for k in seen if k not in live_keys]:
            del seen[kh]
            dirty = True
        if dirty:
            _save_seen(seen)

    def _harden_perms(self):
        """Omarchy recreates the store at 644; re-asserting 600/700 is one
        cheap syscall per reload (plan §4)."""
        try:
            os.chmod(STORE, 0o600)
        except OSError:
            pass
        try:
            os.chmod(IMAGE_DIR, 0o700)
        except OSError:
            pass

    # ------------------------------------------------ denylist (reactive)
    def _apply_denylist(self):
        """HONEST LIMITS (documented, not hidden): the store does not record
        the source window, so this checks the *currently focused* window
        class when the new entry is noticed (~250-350 ms after capture) —
        if focus moved in between, the check misses. And the secret existed
        on disk for that window and in the Wayland selection regardless.
        True exclusion needs the capture side, which is pacman-owned.
        Apps that set CLIPBOARD_STATE=sensitive or x-kde-passwordManagerHint
        are already excluded upstream by capture.sh and never get here."""
        if not self.denylist:
            return
        fresh = [e for e in self.entries if e.key not in self._known_keys]
        if not fresh:
            return
        cls = _active_window_class()
        if not cls or not _class_denied(cls, self.denylist):
            return
        keys = {e.key for e in fresh}
        self.entries = [e for e in self.entries if e.key not in keys]
        self._remove_keys_from_store(keys)
        print(f"sill: denylist: dropped {len(keys)} entr"
              f"{'y' if len(keys) == 1 else 'ies'} captured while "
              f"{cls!r} was focused", file=sys.stderr)

    def _remove_keys_from_store(self, keys):
        """Read-modify-replace Omarchy's store, dropping `keys`; delete image
        files that no surviving entry references."""
        try:
            with open(STORE, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(raw, list):
            return
        kept, kept_entries, dropped_paths = [], [], []
        for item in raw:
            e = normalize(item)
            if e is not None and e.key in keys:
                if e.kind == "image":
                    dropped_paths.append(e.payload)
                continue
            kept.append(item)
            if e is not None:
                kept_entries.append(e)
        _write_store_raw(kept)
        surviving = {e.payload for e in kept_entries if e.kind == "image"}
        for p in dropped_paths:
            if p not in surviving and os.path.dirname(p) == IMAGE_DIR:
                try:
                    os.remove(p)
                except OSError:
                    pass

    # ------------------------------------------------ TTL + orphan prune
    def ttl_prune(self, max_age_days):
        """Drop entries older than the TTL; delete image files referenced by
        no surviving entry AND older than the grace window AND older than
        the TTL (7-day fallback when TTL=0 — an orphan is unreachable by
        any consumer regardless of the keep-forever setting)."""
        days = max(0, int(max_age_days))
        now = time.time()
        if days > 0 and self.state == "ok":
            cutoff = now - days * 86400
            stale = {e.key for e in self.entries if e.when < cutoff}
            if stale:
                self.entries = [e for e in self.entries if e.key not in stale]
                self._remove_keys_from_store(stale)
        # Orphans: capture.sh content-hashes images into IMAGE_DIR but
        # nothing upstream ever deletes them once their entry is evicted.
        referenced = {e.payload for e in self.entries if e.kind == "image"}
        orphan_age = max(GRACE_S, (days or ORPHAN_FALLBACK_DAYS) * 86400)
        try:
            names = os.listdir(IMAGE_DIR)
        except OSError:
            return
        for name in names:
            path = os.path.join(IMAGE_DIR, name)
            if path in referenced:
                continue
            try:
                if now - os.path.getmtime(path) > orphan_age:
                    os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------ watch (GTK side)
    def watch(self):
        from gi.repository import Gio
        gfile = Gio.File.new_for_path(STORE)
        self._monitor = gfile.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES,
                                           None)
        self._monitor.set_rate_limit(200)
        self._monitor.connect("changed", self._on_changed)

    def _on_changed(self, *_a):
        from gi.repository import GLib
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(250, self._reload)

    def _reload(self):
        from gi.repository import GLib
        self._debounce = 0
        want_retry = self.load()
        if want_retry:
            # Torn mid-write read: retry exactly once after 250 ms.
            self._retry_pending = True
            GLib.timeout_add(250, self._retry)
            return False
        self._retry_pending = False
        if self.on_change:
            self.on_change()
        return False

    def _retry(self):
        self.load()
        self._retry_pending = False
        if self.on_change:
            self.on_change()
        return False


# ---------------------------------------------------------------- helpers

def _active_window_class() -> str:
    """~7 ms hyprctl call, made only when a new clipboard entry lands —
    never polled (plan §0/#6 bans hyprctl polling, not one-shot queries)."""
    try:
        out = subprocess.run(["hyprctl", "activewindow", "-j"],
                             capture_output=True, text=True, timeout=1)
        return str(json.loads(out.stdout).get("class") or "")
    except Exception:
        return ""


def _class_denied(cls: str, denylist) -> bool:
    """Each denylist entry is a case-insensitive regex FULL-matched against
    the window class; an entry that fails to compile is compared literally."""
    for pat in denylist:
        try:
            if re.fullmatch(pat, cls, re.IGNORECASE):
                return True
        except re.error:
            if pat.lower() == cls.lower():
                return True
    return False
