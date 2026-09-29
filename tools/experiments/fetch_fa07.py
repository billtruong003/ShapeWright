"""Rebuild the FRESH_AGENT_07 artifacts (docs/experiments/fa07/): download the two CC0 1.0 Khronos
sample models, re-import their texture sets with `sw import` (same file names as in the run), and
place them next to the agent's sources. The binaries (~50 MB) are not committed.

Usage: python tools/experiments/fetch_fa07.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shapewright.importer import import_file  # noqa: E402

BASE = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/{0}/glTF-Binary/{0}.glb"
FILES = {"loveseat": "SheenChair", "lantern": "Lantern"}  # both CC0 1.0 (Wayfair; Microsoft)


def main() -> int:
    out = ROOT / "docs" / "experiments" / "fa07"
    for asset, model in FILES.items():
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / f"{model}.glb"
            urllib.request.urlretrieve(BASE.format(model), src)
            import_file(src, Path(d) / "imp", asset)
            dest = out / asset / "source"
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(Path(d) / "imp" / "source", dest)
        print(f"{asset}: {dest}")
    print("now: ./sw validate docs/experiments/fa07/loveseat (and loveseat_teal, lantern)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
