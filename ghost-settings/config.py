"""ghost-settings config — load / clamp / diff / atomic save / TOML emitter.

The file is ~/.config/ghost/settings.toml. Reading uses stdlib tomllib;
writing regenerates the whole file from schema.SPEC (comments included),
preserving unknown keys verbatim in a trailing block. load() never raises:
parse failure -> .bak -> schema defaults, with warnings.

The one hazard of the file-watch live-apply — partial reads mid-write — is
eliminated here, by the writer: save() writes a temp file in the same
directory and os.replace()s it, so watchers see one event and a complete file.
"""

import os
import shutil
import tempfile
import tomllib
from pathlib import Path

from schema import (SPEC, Choice, NinePoint, Number, StrList, Text, Toggle,
                    NINE_POINTS, known_keys)

CONFIG = Path(os.path.expanduser("~/.config/ghost/settings.toml"))


# ---------------------------------------------------------------- clamping

def clamp_field(fld, v):
    """Coerce v to the field's type and range; fall back to the default."""
    if isinstance(fld, Toggle):
        return v if isinstance(v, bool) else fld.default
    if isinstance(fld, Number):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return fld.default
        return max(fld.min, min(fld.max, int(v)))
    if isinstance(fld, NinePoint):
        return v if v in NINE_POINTS else fld.default
    if isinstance(fld, Choice):
        return v if v in fld.options else fld.default
    if isinstance(fld, Text):
        return v if isinstance(v, str) else fld.default
    if isinstance(fld, StrList):
        if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
            return tuple(v)
        return fld.default
    return fld.default


def defaults() -> dict:
    return {f"{sec.key}.{fld.key}": fld.default
            for sec in SPEC for fld in sec.fields}


# ---------------------------------------------------------------- loading

def _dig(raw: dict, sec_key: str, fld_key: str, default):
    node = raw
    for part in sec_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    if not isinstance(node, dict):
        return default
    return node.get(fld_key, default)


def _collect_unknown(raw: dict) -> dict:
    """Flatten raw to {dotted: value}; keep every leaf SPEC doesn't know.
    A dict leaf that matches no SPEC section prefix is flattened too."""
    known = known_keys()
    out = {}

    def walk(node, prefix):
        for k, v in node.items():
            dotted = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                walk(v, dotted)
            elif dotted not in known:
                out[dotted] = v

    walk(raw, "")
    return out


def load(path: Path = CONFIG) -> tuple[dict, list[str]]:
    """Returns flat {dotted_key: value} plus warnings. Never raises."""
    warnings: list[str] = []
    raw = {}
    for candidate in (path, path.with_suffix(".toml.bak")):
        try:
            with open(candidate, "rb") as f:
                raw = tomllib.load(f)
            break
        except FileNotFoundError:
            raw = {}
            if candidate == path:
                break  # absent file = defaults, not an error
        except (OSError, tomllib.TOMLDecodeError) as e:
            warnings.append(f"{candidate.name}: {e}")
            raw = {}
    vals = {}
    for sec in SPEC:
        for fld in sec.fields:
            v = _dig(raw, sec.key, fld.key, fld.default)
            clamped = clamp_field(fld, v)
            # TOML lists load as list, clamp normalises to tuple — not a change.
            comparable = tuple(v) if isinstance(v, list) else v
            if clamped != comparable and f"{sec.key}.{fld.key}" in _present(raw, sec.key, fld.key):
                warnings.append(f"{sec.key}.{fld.key}: {v!r} clamped to {clamped!r}")
            vals[f"{sec.key}.{fld.key}"] = clamped
    vals["_unknown"] = _collect_unknown(raw)
    return vals, warnings


def _present(raw, sec_key, fld_key):
    sentinel = object()
    return ({f"{sec_key}.{fld_key}"}
            if _dig(raw, sec_key, fld_key, sentinel) is not sentinel else set())


def diff(old: dict, new: dict) -> list[str]:
    """Dotted keys whose values differ (ignoring the _unknown blob)."""
    return sorted(k for k in new
                  if k != "_unknown" and new[k] != old.get(k))


# ---------------------------------------------------------------- emitting

def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        if not v:
            return "[]"
        inner = "\n".join(f"  {_toml_value(x)}," for x in v)
        return "[\n" + inner + "\n]"
    raise TypeError(f"cannot emit {type(v)} as TOML")


def _range_note(fld) -> str:
    if isinstance(fld, Number):
        unit = f" {fld.unit}" if fld.unit else ""
        zero = f" · 0 = {fld.zero_means}" if fld.zero_means else ""
        return f"({fld.min}-{fld.max}){unit}{zero}"
    if isinstance(fld, Choice):
        return "|".join(fld.options)
    if isinstance(fld, NinePoint):
        return "|".join(NINE_POINTS)
    return ""


def emit_toml(vals: dict) -> str:
    lines = [
        "# ghost desktop — one config for sill and the bar widgets.",
        "# Written by ghost-settings; hand-editing is fine — every running",
        "# component watches this file and applies changes on save.",
        "# Out-of-range values are clamped on load; unknown keys are kept",
        "# (verbatim, in the trailing block) but ignored.",
    ]
    for sec in SPEC:
        lines.append("")
        lines.append(f"[{sec.key}]")
        for fld in sec.fields:
            v = vals.get(f"{sec.key}.{fld.key}", fld.default)
            note = _range_note(fld)
            docline = fld.doc.split("\n")[0] if fld.doc else ""
            comment = " · ".join(x for x in (docline, note) if x)
            entry = f"{fld.key} = {_toml_value(v)}"
            if comment and "\n" not in entry:
                entry = f"{entry:<34}# {comment}"
            lines.append(entry)
    unknown = vals.get("_unknown") or {}
    if unknown:
        lines.append("")
        lines.append("# --- unrecognised keys, preserved verbatim ---")
        by_table: dict[str, dict] = {}
        for dotted, v in unknown.items():
            table, _, key = dotted.rpartition(".")
            by_table.setdefault(table, {})[key] = v
        for table in sorted(by_table):
            if table:
                lines.append(f"[{table}]")
            for key, v in by_table[table].items():
                lines.append(f"{key} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def _parses_ok(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            tomllib.load(f)
        return True
    except Exception:
        return False


def save(path: Path, vals: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and _parses_ok(path):
        shutil.copy2(path, path.with_suffix(".toml.bak"))
    text = emit_toml(vals)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-")
    try:
        os.write(fd, text.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)  # atomic -> one inotify event, always complete
