#!/usr/bin/env python3
"""ghost-settings — one config for sill and the bar widgets.

Usage:
  ghost-settings                   the curses TUI
  ghost-settings get KEY           print one value (dotted key)
  ghost-settings set KEY VALUE...  set one value (validated + clamped)
  ghost-settings dump --json       full config as JSON (QML consumes this)
  ghost-settings check             validate the file; exit 1 if broken
  ghost-settings keys              list every dotted key

Config: ~/.config/ghost/settings.toml. Writes are atomic (os.replace), so
every watching component sees one event and always a complete file.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as gs_config          # noqa: E402
import schema                       # noqa: E402
from schema import (Choice, NinePoint, Number, StrList, Text,  # noqa: E402
                    Toggle, NINE_POINTS, SPEC)

TRUE = {"true", "on", "yes", "1"}
FALSE = {"false", "off", "no", "0"}


def _fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "\n".join(v)
    return str(v)


def cmd_get(key: str) -> int:
    _sec, fld = schema.field_for(key)
    if fld is None:
        print(f"unknown key: {key}", file=sys.stderr)
        return 2
    vals, _w = gs_config.load(gs_config.CONFIG)
    print(_fmt(vals[key]))
    return 0


def cmd_set(key: str, words: list[str]) -> int:
    _sec, fld = schema.field_for(key)
    if fld is None:
        print(f"unknown key: {key}", file=sys.stderr)
        print("run `ghost-settings keys` for the list", file=sys.stderr)
        return 2
    raw = " ".join(words)
    if isinstance(fld, Toggle):
        low = raw.strip().lower()
        if low in TRUE:
            value = True
        elif low in FALSE:
            value = False
        else:
            print(f"{key}: expected on/off, got {raw!r}", file=sys.stderr)
            return 2
    elif isinstance(fld, Number):
        try:
            value = int(raw)
        except ValueError:
            print(f"{key}: expected an integer, got {raw!r}", file=sys.stderr)
            return 2
        clamped = max(fld.min, min(fld.max, value))
        if clamped != value:
            print(f"{key}: {value} clamped to {clamped} "
                  f"(range {fld.min}-{fld.max})", file=sys.stderr)
        value = clamped
    elif isinstance(fld, (Choice, NinePoint)):
        opts = fld.options if isinstance(fld, Choice) else NINE_POINTS
        if raw not in opts:
            print(f"{key}: must be one of {'|'.join(opts)}", file=sys.stderr)
            return 2
        value = raw
    elif isinstance(fld, StrList):
        items = words if len(words) > 1 else \
            [x.strip() for x in raw.split(",") if x.strip()]
        value = tuple(items)
    elif isinstance(fld, Text):
        value = raw
    else:
        return 2
    vals, _w = gs_config.load(gs_config.CONFIG)
    vals[key] = gs_config.clamp_field(fld, value)
    gs_config.save(gs_config.CONFIG, vals)
    print(f"{key} = {_fmt(vals[key])}")
    return 0


def cmd_dump() -> int:
    vals, _w = gs_config.load(gs_config.CONFIG)
    nested: dict = {}
    for sec in SPEC:
        for fld in sec.fields:
            node = nested
            for part in sec.key.split("."):
                node = node.setdefault(part, {})
            v = vals[f"{sec.key}.{fld.key}"]
            node[fld.key] = list(v) if isinstance(v, tuple) else v
    print(json.dumps(nested, indent=2))
    return 0


def cmd_check() -> int:
    import tomllib
    path = gs_config.CONFIG
    try:
        with open(path, "rb") as f:
            tomllib.load(f)
    except FileNotFoundError:
        print(f"{path}: missing (defaults active)")
        return 0
    except tomllib.TOMLDecodeError as e:
        print(f"{path}: {e}", file=sys.stderr)
        return 1
    _vals, warnings = gs_config.load(path)
    nkeys = sum(len(sec.fields) for sec in SPEC)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"{path}: ok · {nkeys} keys · {len(warnings)} warning(s)")
    return 0


def cmd_keys() -> int:
    for sec in SPEC:
        for fld in sec.fields:
            print(f"{sec.key}.{fld.key}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="ghost-settings",
                                description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("get", help="print one value")
    g.add_argument("key")
    s = sub.add_parser("set", help="set one value (validated + clamped)")
    s.add_argument("key")
    s.add_argument("value", nargs="+")
    d = sub.add_parser("dump", help="full config as JSON")
    d.add_argument("--json", action="store_true", default=True,
                   help="JSON output (the only format)")
    sub.add_parser("check", help="validate the config file")
    sub.add_parser("keys", help="list every dotted key")
    args = p.parse_args()
    if args.cmd == "get":
        return cmd_get(args.key)
    if args.cmd == "set":
        return cmd_set(args.key, args.value)
    if args.cmd == "dump":
        return cmd_dump()
    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "keys":
        return cmd_keys()
    from tui.app import run_tui
    return run_tui()


if __name__ == "__main__":
    sys.exit(main())
