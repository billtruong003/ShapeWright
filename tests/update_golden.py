"""Regenerate tests/golden.json after an intentional geometry change: python tests/update_golden.py

Records this platform's hash and the geometry signature (tests/golden.py). Geometry that is unchanged up to float
noise only gains this platform's hash; a real change keeps just this platform's hash and a new signature, so the
other platforms fall back to the signature check until someone runs this script there.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden import load, platform_key, record, save  # noqa: E402

from shapewright.assemble import ROOT, build  # noqa: E402
from shapewright.mesh import concat, geometry_hash, geometry_signature  # noqa: E402

old, plat, new, counts = load(), platform_key(), {}, {}
for p in sorted((ROOT / "assets").glob("*/asset.yaml")):
    mesh = concat([q.mesh for q in build(p).parts])
    new[p.parent.name], what = record(old.get(p.parent.name), geometry_hash(mesh), geometry_signature(mesh), plat)
    counts.setdefault(what, []).append(p.parent.name)
save(new)
print(f"platform {plat}")
for what, names in sorted(counts.items()):
    print(f"{what:15s} {len(names):3d}  {', '.join(names) if what != 'unchanged' else ''}")
