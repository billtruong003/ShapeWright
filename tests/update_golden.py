"""Regenerate tests/golden.json after an intentional geometry change: python tests/update_golden.py

Records this platform's hash and the geometry signature (tests/golden.py). Geometry that is unchanged up to float
noise only gains this platform's hash; a real change keeps just this platform's hash and a new signature, so the
other platforms fall back to the signature check until someone runs this script there.

  python tests/update_golden.py --merge golden-*.json   take other platforms' hashes (CI artifacts `golden-<os>`)
                                                        where their signatures agree; nothing is rebuilt
  python tests/update_golden.py --changed a,b          these assets changed on purpose: drop the other platforms'
                                                        hashes even when the signature does not notice (a 3 mm
                                                        edit inside the bounds) - otherwise they stay stale
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden import load, merge, platform_key, record, save  # noqa: E402

from shapewright.assemble import ROOT, build  # noqa: E402
from shapewright.mesh import concat, geometry_hash, geometry_signature  # noqa: E402

if sys.argv[1:2] == ["--merge"]:
    golden = load()
    for f in sys.argv[2:]:
        gained = merge(golden, load(Path(f)))
        print(f"{f}: {len(gained)} assets gained a platform hash")
    save(golden)
    sys.exit(0)

changed = set(sys.argv[sys.argv.index("--changed") + 1].split(",")) if "--changed" in sys.argv else set()
old, plat, new, counts = load(), platform_key(), {}, {}
for p in sorted((ROOT / "assets").glob("*/asset.yaml")):
    mesh = concat([q.mesh for q in build(p).parts])
    prev = None if p.parent.name in changed else old.get(p.parent.name)
    new[p.parent.name], what = record(prev, geometry_hash(mesh), geometry_signature(mesh), plat)
    what = "changed" if p.parent.name in changed else what
    counts.setdefault(what, []).append(p.parent.name)
save(new)
print(f"platform {plat}")
for what, names in sorted(counts.items()):
    print(f"{what:15s} {len(names):3d}  {', '.join(names) if what != 'unchanged' else ''}")
