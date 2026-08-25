"""Sill pinned store — ~/.local/share/sill/pins/pins.json + blobs/.

Pinning TEXT or an IMAGE copies the content into blobs/ (content-hash
filename, so duplicates dedupe) — a pin must survive clipboard eviction and
purges. Pinning a FILE records the path only (a stash must not duplicate a
2 GB file); a dead path renders greyed with the path still draggable as text.

pins.json is written atomically (temp + os.replace), same discipline as the
config. Eviction: never — manual unpin only. Unpinning drops the blob if no
other pin references it.
"""

import hashlib
import json
import os
import tempfile
import time

# SILL_PIN_DIR is a test seam only — production always uses the default.
PIN_DIR = (os.environ.get("SILL_PIN_DIR")
           or os.path.expanduser("~/.local/share/sill/pins"))
PIN_INDEX = os.path.join(PIN_DIR, "pins.json")
BLOB_DIR = os.path.join(PIN_DIR, "blobs")


class Pin(dict):
    """{id, kind: text|image|file, title, when, payload}
    payload: blob path for text/image pins, original path for file pins."""

    @property
    def kind(self):
        return self["kind"]

    @property
    def payload(self):
        return self["payload"]

    @property
    def title(self):
        return self["title"]

    def text_content(self):
        if self["kind"] != "text":
            return None
        try:
            with open(self["payload"], encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def alive(self):
        return os.path.exists(self["payload"])


class PinStore:
    def __init__(self):
        self.pins: list[Pin] = []
        self.load()

    # ---------------- persistence ----------------
    def load(self):
        try:
            with open(PIN_INDEX, encoding="utf-8") as f:
                raw = json.load(f)
            self.pins = [Pin(p) for p in raw
                         if isinstance(p, dict)
                         and p.get("kind") in ("text", "image", "file")
                         and isinstance(p.get("payload"), str)]
        except (OSError, ValueError):
            self.pins = []

    def save(self):
        os.makedirs(PIN_DIR, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=PIN_DIR, prefix=".pins-")
        try:
            os.write(fd, json.dumps(self.pins, indent=1).encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, PIN_INDEX)

    # ---------------- blobs ----------------
    @staticmethod
    def _blob_path(data: bytes, ext: str) -> str:
        h = hashlib.sha256(data).hexdigest()[:24]
        return os.path.join(BLOB_DIR, f"{h}{ext}")

    def _write_blob(self, data: bytes, ext: str) -> str:
        os.makedirs(BLOB_DIR, mode=0o700, exist_ok=True)
        path = self._blob_path(data, ext)
        if not os.path.exists(path):  # content-hash name -> dedupe for free
            fd, tmp = tempfile.mkstemp(dir=BLOB_DIR, prefix=".blob-")
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, path)
            os.chmod(path, 0o600)
        return path

    # ---------------- adding ----------------
    def _add(self, kind, title, payload) -> Pin | None:
        for p in self.pins:
            if p["kind"] == kind and p["payload"] == payload:
                return None  # already pinned; keep original position
        pin = Pin(id=f"{time.time():.6f}", kind=kind, title=title,
                  when=time.time(), payload=payload)
        self.pins.insert(0, pin)
        self.save()
        return pin

    def add_text(self, text: str) -> Pin | None:
        text = text if isinstance(text, str) else str(text)
        if not text.strip():
            return None
        blob = self._write_blob(text.encode("utf-8"), ".txt")
        title = text.strip().splitlines()[0][:60]
        return self._add("text", title, blob)

    def add_image_bytes(self, png_bytes: bytes) -> Pin | None:
        blob = self._write_blob(png_bytes, ".png")
        title = f"image {len(png_bytes) // 1024} KB"
        return self._add("image", title, blob)

    def add_file(self, path: str) -> Pin | None:
        return self._add("file", os.path.basename(path.rstrip("/")) or path,
                         path)

    # ---------------- removing ----------------
    def remove(self, pin: Pin):
        if pin not in self.pins:
            return
        self.pins.remove(pin)
        self.save()
        payload = pin["payload"]
        if (pin["kind"] in ("text", "image")
                and payload.startswith(BLOB_DIR)
                and not any(p["payload"] == payload for p in self.pins)):
            try:
                os.remove(payload)
            except OSError:
                pass
