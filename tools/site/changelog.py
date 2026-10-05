"""The changelog, generated from the phase records (docs/PHASE_PLAN_16.md status table + docs/phases/PHASE_*.md).

  python tools/site/changelog.py        -> CHANGELOG.md (repository root; tests check it is current)
  build_site.py                         -> website/changelog.md (the same text, links to GitHub)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOB = "https://github.com/billtruong003/ShapeWright/blob/main/"

EARLIER = """## Before Phase 16 (stages 0 to 15)

The framework itself: research and architecture, the vertical slice, hardening, the spatial modelling language,
components and families, the surface system (UVs, baked textures), modelling breadth, 50k-triangle performance,
import and repair, game-ready production for Godot / Unity / Unreal, cross-agent validation, agent cost and the
human workbench. Each stage is recorded in [ROADMAP.md]({roadmap}) and the experiments in [docs/experiments]({experiments}).
"""


def rows() -> list[dict]:
    text = (ROOT / "docs" / "PHASE_PLAN_16.md").read_text()
    table = text.split("## Status", 1)[1].split("\n\n", 2)[1]
    out = []
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("phase", "---") or set(cells[0]) <= {"-"}:
            continue
        out.append({"phase": cells[0], "branch": cells[1].strip("`"), "verdict": cells[2], "record": cells[3]})
    return out


def _summary(record: Path) -> tuple[str, str]:
    lines = record.read_text().splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), record.stem)
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("**Verdict")), None)
    if start is None:
        return title, ""
    para = []
    for ln in lines[start:]:
        if not ln.strip() or ln.startswith("#"):
            break
        para.append(ln.strip())
    text = re.sub(r"\s+", " ", " ".join(para))
    return title, re.sub(r"^\*\*Verdict:[^*]*\*\*\s*", "", text)  # the verdict itself is in the table row


def changelog_markdown(site: bool = False) -> str:
    link = (lambda p: BLOB + p) if site else (lambda p: p)
    out = ["# Changelog", "",
           "Newest first. Generated from the phase records by `tools/site/changelog.py`; each entry links to its record "
           "(what shipped, evidence, the gate table and what is not done).", ""]
    for r in reversed(rows()):
        rec = ROOT / r["record"]
        title, verdict = _summary(rec) if rec.exists() else (r["phase"], "")
        out += [f"## {title}", "", f"- **Verdict:** {r['verdict']}", f"- **Branch:** `{r['branch']}`",
                f"- **Record:** [{r['record']}]({link(r['record'])})"]
        if verdict:
            out.append(f"- {verdict}")
        out.append("")
    out.append(EARLIER.format(roadmap=link("docs/ROADMAP.md"), experiments=link("docs/experiments")))
    return "\n".join(out)


if __name__ == "__main__":
    (ROOT / "CHANGELOG.md").write_text(changelog_markdown())
    print("wrote CHANGELOG.md", file=sys.stderr)
