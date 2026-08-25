#!/usr/bin/env python3
"""Headless tests for store_clipboard — the normaliser, schema guard, TTL /
orphan prune, purge and denylist matcher. No GTK, no pointer, no pytest
dependency: plain asserts, run with `python3 test_store_clipboard.py`.

Uses the SILL_CLIP_STATE_DIR / SILL_SEEN_FILE test seams; never touches the
real Omarchy store.
"""

import json
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="sill-test-")
os.environ["SILL_CLIP_STATE_DIR"] = TMP
os.environ["SILL_SEEN_FILE"] = os.path.join(TMP, "seen.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store_clipboard as sc  # noqa: E402

IMG_DIR = os.path.join(TMP, "clipboard-images")
os.makedirs(IMG_DIR)
PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1


def write_store(obj):
    with open(sc.STORE, "w") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


def img(name, age_s=0, data=b"png"):
    path = os.path.join(IMG_DIR, name)
    with open(path, "wb") as f:
        f.write(data)
    t = time.time() - age_s
    os.utime(path, (t, t))
    return path


# ---------------- normaliser (port of normalizeEntry) ----------------
ok(sc.normalize("hello").kind == "text", "bare string -> text")
ok(sc.normalize("   ") is None, "blank string skipped")
ok(sc.normalize({"type": "text", "text": "x"}).payload == "x", "text dict")
ok(sc.normalize({"type": "text", "text": ""}) is None, "empty text skipped")
e = sc.normalize({"type": "image", "path": "/p.png",
                  "capturedAt": "Tuesday 03:45"})
ok(e.kind == "image" and e["mime"] == "image/png"
   and e["display_at"] == "Tuesday 03:45", "image dict + display stamp")
ok(sc.normalize({"type": "image"}) is None, "image without path skipped")
ok(sc.normalize({"type": "wat"}) is None, "unknown type skipped")
ok(sc.normalize(42) is None, "non-dict skipped")
ok(sc.normalize({"kind": "text", "text": "k"}) is not None, "kind alias")

# ---------------- schema guard state machine ----------------
s = sc.ClipStore()
s.load(initial=True)
ok(s.state == "missing" and s.entries == [], "missing file -> missing")

p = img("ref.png")
write_store([{"type": "text", "text": "keepme"},
             {"type": "image", "path": p, "mime": "image/png",
              "capturedAt": "Tuesday 01:00"}])
s.load(initial=True)
ok(s.state == "ok" and len(s.entries) == 2, "good store -> ok")
ok(s.entries[0].when > 0, "text stamped via sidecar")
ok(abs(s.entries[1].when - os.path.getmtime(p)) < 1, "image stamped by mtime")
ok(oct(os.stat(sc.STORE).st_mode & 0o777) == "0o600", "store chmod 600")
ok(oct(os.stat(IMG_DIR).st_mode & 0o777) == "0o700", "images dir chmod 700")

write_store('[{"type": "text", "te')       # torn mid-write
want_retry = s.load()
ok(want_retry and s.state == "ok" and len(s.entries) == 2,
   "torn read -> retry requested, last-good kept")
s._retry_pending = True
s.load()
ok(s.state == "unreadable" and len(s.entries) == 2,
   "still torn after retry -> unreadable, last-good kept")

write_store([{"type": "martian", "blob": 1}])
s._retry_pending = False
s.load()
ok(s.state == "drift" and len(s.entries) == 2,
   "recognises 0 of >0 raw -> drift, last-good kept")

write_store({"not": "a list"})
s.load()
ok(s.state == "drift", "non-list JSON -> drift")

# ---------------- sidecar continuity ----------------
write_store([{"type": "text", "text": "keepme"}])
first = json.load(open(sc.SEEN))
s.load(initial=True)
second = json.load(open(sc.SEEN))
ok(first and list(first.values())[0] == list(second.values())[0]
   and len(second) == 1,
   "first-seen stable across reloads; departed keys pruned")

# ---------------- TTL + orphan prune ----------------
old_img = img("old.png", age_s=10 * 86400, data=b"old")
new_img = img("new.png", age_s=3600, data=b"new")
orphan_old = img("orphan-old.png", age_s=10 * 86400, data=b"o1")
orphan_new = img("orphan-new.png", age_s=3600, data=b"o2")
write_store([
    {"type": "text", "text": "fresh"},
    {"type": "image", "path": old_img, "mime": "image/png"},
    {"type": "image", "path": new_img, "mime": "image/png"},
])
s = sc.ClipStore()
s.load(initial=True)
# Backdate the text entry's first-seen to 10 days ago.
seen = json.load(open(sc.SEEN))
for k in seen:
    seen[k] = time.time() - 10 * 86400
json.dump(seen, open(sc.SEEN, "w"))
s._seen = {k: float(v) for k, v in seen.items()}
s.load(initial=True)
s.ttl_prune(7)
raw = json.load(open(sc.STORE))
ok(len(raw) == 1 and raw[0]["path"] == new_img,
   "TTL pruned old text + old image, kept fresh image")
ok(not os.path.exists(old_img), "pruned entry's image file deleted")
ok(not os.path.exists(orphan_old), "old orphan image deleted")
ok(os.path.exists(orphan_new), "young orphan survives 24h grace")
ok(os.path.exists(new_img), "referenced image survives")

# TTL=0 keeps entries but still clears unreachable old orphans.
orphan_old2 = img("orphan-old2.png", age_s=10 * 86400, data=b"o3")
s.ttl_prune(0)
ok(len(json.load(open(sc.STORE))) == 1, "TTL=0: entries kept forever")
ok(not os.path.exists(orphan_old2), "TTL=0: old orphan still pruned")

# ---------------- targeted removal ----------------
p2 = img("deny.png", data=b"deny")
write_store([{"type": "text", "text": "secret"},
             {"type": "image", "path": p2, "mime": "image/png"},
             {"type": "text", "text": "innocent"}])
s = sc.ClipStore()
s.load(initial=True)
s._remove_keys_from_store({"text:secret", "image:" + p2})
raw = json.load(open(sc.STORE))
ok(len(raw) == 1 and raw[0]["text"] == "innocent",
   "targeted removal keeps the rest")
ok(not os.path.exists(p2), "removed image entry's file deleted")

# ---------------- purge ----------------
img("leftover.png")
sc.purge()
ok(json.load(open(sc.STORE)) == [], "purge -> empty store")
ok(os.listdir(IMG_DIR) == [], "purge -> images dir emptied")
ok(json.load(open(sc.SEEN)) == {}, "purge -> sidecar cleared")

# ---------------- denylist matcher ----------------
deny = ("org.keepassxc.KeePassXC", "1Password.*", "Alacritty", "kitty",
        "foot", "org.codeberg.dnkl.foot", "com.mitchellh.ghostty",
        "wezterm", "org.omarchy.terminal", "TUI[.].*", "Bitwarden")
ok(sc._class_denied("org.keepassxc.KeePassXC", deny), "keepassxc denied")
ok(sc._class_denied("1Password-BrowserSupport", deny), "1password glob")
ok(sc._class_denied("alacritty", deny), "case-insensitive")
ok(sc._class_denied("TUI.float", deny), "TUI pattern")
ok(not sc._class_denied("org.omarchy.agent", deny),
   "agent terminal NOT denied by default (documented choice)")
ok(not sc._class_denied("firefox", deny), "browser not denied")
ok(not sc._class_denied("", deny), "no active window -> not denied")
ok(sc._class_denied("x", ("x", "[bad(regex",)), "literal + bad regex safe")
ok(not sc._class_denied("kittycat", deny), "full match, not substring")

print(f"all {PASS} assertions passed")
import shutil  # noqa: E402
shutil.rmtree(TMP)
