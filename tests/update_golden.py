"""Regenerate tests/golden.json after an intentional geometry change: python tests/update_golden.py"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapewright.assemble import ROOT, build  # noqa: E402
from shapewright.mesh import concat, geometry_hash  # noqa: E402

out = {}
for p in sorted((ROOT / "assets").glob("*/asset.yaml")):
    a = build(p)
    out[p.parent.name] = geometry_hash(concat([q.mesh for q in a.parts]))
(Path(__file__).parent / "golden.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
