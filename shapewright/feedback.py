"""Notes a person pins on a model (workbench: click a point, type what is wrong) for the agent to act on.

Stored per asset in `<out_dir>/.build/feedback.json` (paths.out_dir: the project, never the library):
    {"notes": [{"id", "note", "part", "at", "normal", "view", "image", "status": "open"|"resolved", "reply"}]}
`sw feedback ASSET` lists open notes, the MCP tool `feedback` returns them with their screenshots, and the agent
marks a note resolved (`sw feedback ASSET resolve ID --reply "..."`) after changing the source.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import paths

MAX_NOTES = 200
MAX_TEXT = 2000


def path_for(asset_dir: Path) -> Path:
    return paths.out_dir(asset_dir) / ".build" / "feedback.json"


def load(asset_dir: Path) -> list[dict]:
    p = path_for(asset_dir)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text()).get("notes") or [])
    except (json.JSONDecodeError, AttributeError):
        return []


def _save(asset_dir: Path, notes: list[dict]):
    p = path_for(asset_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"notes": notes}, indent=1) + "\n")


def _vec(v) -> list[float] | None:
    if v is None:
        return None
    vals = [float(x) for x in (v.split(",") if isinstance(v, str) else v)]
    if len(vals) != 3:
        raise ValueError("a point is three numbers x,y,z")
    return [round(x, 4) for x in vals]


def add(asset_dir: Path, note: str, part: str | None = None, at=None, normal=None, view: str | None = None,
        image: str | None = None) -> dict:
    note = (note or "").strip()
    if not note:
        raise ValueError("a note needs text: what is wrong or what should change")
    notes = load(asset_dir)
    if len(notes) >= MAX_NOTES:
        raise ValueError(f"{MAX_NOTES} notes already; resolve some first")
    entry = {"id": max([n.get("id", 0) for n in notes] + [0]) + 1, "note": note[:MAX_TEXT], "part": part or None,
             "at": _vec(at), "normal": _vec(normal), "view": view or None, "image": image or None, "status": "open", "reply": None}
    notes.append(entry)
    _save(asset_dir, notes)
    return entry


def resolve(asset_dir: Path, note_id: int, reply: str = "") -> dict:
    notes = load(asset_dir)
    hit = [n for n in notes if n.get("id") == note_id]
    if not hit:
        raise ValueError(f"no note #{note_id} (open: {', '.join(str(n['id']) for n in notes if n.get('status') == 'open') or 'none'})")
    hit[0]["status"], hit[0]["reply"] = "resolved", (reply or "").strip()[:MAX_TEXT] or None
    _save(asset_dir, notes)
    return hit[0]


def format_notes(notes: list[dict], show_resolved: bool = False) -> str:
    rows = [n for n in notes if show_resolved or n.get("status") == "open"]
    done = sum(1 for n in notes if n.get("status") == "resolved")
    if not rows:
        return f"no open notes ({done} resolved)"
    out = [f"{len(rows)} open note(s), {done} resolved:"] if not show_resolved else [f"{len(notes)} note(s):"]
    for n in rows:
        where = []
        if n.get("part"):
            where.append(f"part {n['part']}")
        if n.get("at"):
            where.append("at (" + ", ".join(f"{v:g}" for v in n["at"]) + ")")
        if n.get("view"):
            where.append(f"seen from {n['view']}")
        out.append(f"#{n['id']} [{n['status']}] {n['note']}" + (f"  -- {'; '.join(where)}" if where else "")
                   + (f"  (image {n['image']})" if n.get("image") else "") + (f"  reply: {n['reply']}" if n.get("reply") else ""))
    return "\n".join(out)
