"""Sill drag providers — the ONLY place Gdk.ContentProviders are built.

THE TWO ZERO-MIME TRAPS (measured on this machine, 2026-08-25):

  new_for_value(Gio.File)     -> ON THE WIRE: []   (GValue carries GLocalFile,
                                 serialisers registered against GFile iface)
  new_for_value(Gdk.Texture)  -> ON THE WIRE: []   (same class of failure)

The working forms:

  new_for_value(Gdk.FileList.new_from_list([gfile]))
      -> text/uri-list + application/vnd.portal.filetransfer + ...
  new_for_value(GObject.Value(Gdk.Texture, tex))
      -> ~16 image/* mimes
  new_for_value("text")
      -> text/plain;charset=utf-8, text/plain
  new_union([file, texture, text])
      -> ~21 mimes: the "drag out offers all formats, target chooses" form.

A drag built on a trap form looks completely correct and silently fails on
every drop — which is why self_test() exists and is wired into
`sill doctor --self-test`: a provider refactor cannot silently ship an
empty drag.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GObject  # noqa: E402


def for_text(text: str) -> Gdk.ContentProvider:
    return Gdk.ContentProvider.new_for_value(text)


def for_texture(texture: Gdk.Texture) -> Gdk.ContentProvider:
    # GObject.Value(Gdk.Texture, ...) forces the GValue's declared type to
    # the class GDK registered serialisers for. Passing the texture bare
    # advertises ZERO mimes. Do not "simplify" this.
    return Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.Texture, texture))


def for_files(paths) -> Gdk.ContentProvider:
    gfiles = [Gio.File.new_for_path(p) for p in paths]
    # Gdk.FileList, NOT Gio.File — see the module docstring.
    return Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list(gfiles))


def for_file(path) -> Gdk.ContentProvider:
    return for_files([path])


def union(providers) -> Gdk.ContentProvider:
    return Gdk.ContentProvider.new_union(list(providers))


def for_image_file(path: str) -> Gdk.ContentProvider:
    """Union: uri-list + portal file transfer + image/* + path as text.
    The drop target picks whichever format it prefers."""
    parts = [for_file(path)]
    try:
        parts.append(for_texture(Gdk.Texture.new_from_filename(path)))
    except Exception:
        pass  # unreadable image: still draggable as a file
    parts.append(for_text(path))
    return union(parts)


def mimes_of(provider: Gdk.ContentProvider) -> list[str]:
    return list(provider.ref_formats().union_serialize_mime_types().get_mime_types())


def self_test(sample_image: str | None = None) -> list[str]:
    """Assert the on-wire mime lists for every provider kind.
    Returns a list of failures (empty = pass)."""
    failures = []

    t = mimes_of(for_text("probe"))
    if "text/plain;charset=utf-8" not in t:
        failures.append(f"text provider mimes: {t}")

    f = mimes_of(for_file(os.path.expanduser("~/.bashrc")))
    if "text/uri-list" not in f:
        failures.append(f"file provider mimes: {f}")

    if sample_image and os.path.exists(sample_image):
        try:
            tex = Gdk.Texture.new_from_filename(sample_image)
        except Exception as e:
            failures.append(f"sample image unreadable: {e}")
        else:
            i = mimes_of(for_texture(tex))
            if not any(m.startswith("image/") for m in i):
                failures.append(f"texture provider mimes: {i}")
            u = mimes_of(union([for_file(sample_image), for_texture(tex),
                                for_text(sample_image)]))
            if not ("text/uri-list" in u
                    and any(m.startswith("image/") for m in u)
                    and "text/plain;charset=utf-8" in u):
                failures.append(f"union provider mimes: {u}")
    return failures
