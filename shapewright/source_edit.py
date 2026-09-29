"""`sw set ASSET name=value`: keep parameter values in the source without hand-editing YAML (Phase 15).

Sources are hand-authored and commented, so the edit is textual: only the value of each named
parameter changes, and every other byte stays. Three layouts are handled:
- `name: 0.4` (scalar);
- `name: {value: 0.4, min: ...}` (flow mapping);
- a block mapping with a `value:` line.

The result is re-read and checked. If the file does not say what was asked, it is restored and the
command fails, instead of guessing. This is the CLI capability the workbench's "apply" uses; the GUI has no
write path of its own.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    s = str(v)
    return f'"{s}"' if any(c in s for c in ",:#{}[]") else s


def _params_block(lines: list[str]) -> tuple[int, int] | None:
    """Line range (start, end) of the block-style `params:` section's children."""
    for i, ln in enumerate(lines):
        if re.match(r"^params:\s*(#.*)?$", ln):
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].startswith((" ", "\t")) or lines[j].lstrip().startswith("#")):
                j += 1
            return i + 1, j
    return None


def _set_one(lines: list[str], name: str, value: str) -> bool:
    blk = _params_block(lines)
    if blk is None:  # flow style on one line: params: {w: 0.4, h: 0.45}
        for i, ln in enumerate(lines):
            if re.match(r"^params:\s*\{", ln):
                new, n = re.subn(rf"(\b{re.escape(name)}:\s*)(\{{[^}}]*?\bvalue:\s*)?([^,}}\s][^,}}]*)",
                                 lambda m: m.group(1) + (m.group(2) or "") + value, ln, count=1)
                if n:
                    lines[i] = new
                    return True
        return False
    start, end = blk
    indent = None
    for i in range(start, end):
        m = re.match(r"^(\s+)([A-Za-z_]\w*):(.*)$", lines[i])
        if not m:
            continue
        if indent is None:
            indent = m.group(1)
        if m.group(1) != indent or m.group(2) != name:
            continue
        rest = m.group(3)
        body, comment = (rest.split(" #", 1) + [None])[:2] if " #" in rest else (rest, None)
        tail = f" #{comment}" if comment is not None else ""
        if body.strip().startswith("{"):
            new, n = re.subn(r"(\bvalue:\s*)([^,}]+?)(\s*[,}])", lambda mm: mm.group(1) + value + mm.group(3), body, count=1)
            if not n:
                return False
            lines[i] = f"{indent}{name}:{new}{tail}"
            return True
        if body.strip():
            lead = re.match(r"^\s*", body).group(0) or " "
            trail = re.search(r"\s*$", body).group(0) if comment is not None else ""
            lines[i] = f"{indent}{name}:{lead}{value}{trail}{tail}"
            return True
        for j in range(i + 1, end):  # block mapping: find its value: line
            mm = re.match(r"^(\s+)value:(\s*)([^#]*?)(\s*#.*)?$", lines[j])
            if mm and len(mm.group(1)) > len(indent):
                lines[j] = f"{mm.group(1)}value:{mm.group(2) or ' '}{value}{mm.group(4) or ''}"
                return True
            if re.match(rf"^{indent}\S", lines[j]):
                break
        return False
    return False


def set_params(path: Path, overrides: dict) -> list[str]:
    """Write param values into the source file; returns 'name: old -> new' lines. Raises ValueError."""
    from .registry import suggest

    text = path.read_text()
    data = yaml.safe_load(text) or {}
    params = data.get("params") or {}
    lines = text.split("\n")
    changes = []
    for k, v in overrides.items():
        if k not in params:
            raise ValueError(f"'{k}' is not a param of this source file.{suggest(k, params)}"
                             " (params inherited from a base or pack are set in that file, or add them under params:)")
        old = params[k].get("value") if isinstance(params[k], dict) else params[k]
        if isinstance(params[k], dict) and isinstance(v, (int, float)) and not isinstance(v, bool):
            lo, hi = params[k].get("min"), params[k].get("max")
            if (isinstance(lo, (int, float)) and v < lo) or (isinstance(hi, (int, float)) and v > hi):
                raise ValueError(f"{k}={v} is outside its declared range [{lo}, {hi}]; change min/max in the source if the "
                                 "design intent changed")
        if not _set_one(lines, k, _fmt(v)):
            raise ValueError(f"could not locate the value of '{k}' in {path.name}; edit it by hand")
        changes.append(f"{k}: {old} -> {v}")
    new_text = "\n".join(lines)
    got = (yaml.safe_load(new_text) or {}).get("params") or {}
    for k, v in overrides.items():
        cur = got.get(k)
        cur = cur.get("value") if isinstance(cur, dict) else cur
        if cur != v:
            raise ValueError(f"editing '{k}' did not produce {v!r} (read back {cur!r}); the file was not changed")
    rest_before = {k: v for k, v in data.items() if k != "params"}
    rest_after = {k: v for k, v in (yaml.safe_load(new_text) or {}).items() if k != "params"}
    if rest_before != rest_after:
        raise ValueError("the edit touched more than params; the file was not changed")
    path.write_text(new_text)
    return changes
