"""Architecture boundaries and backend topology contracts."""

import re
from pathlib import Path

import pytest

from shapewright.assemble import build_geometry
from shapewright.source import Ctx

PKG = Path(__file__).resolve().parent.parent / "shapewright"
BACKEND_LIBS = re.compile(r"^\s*(import|from)\s+(trimesh|manifold3d|xatlas|fast_simplification|scipy)\b", re.M)


def test_only_backend_imports_geometry_libraries():
    offenders = [str(p.relative_to(PKG)) for p in PKG.rglob("*.py")
                 if p.name != "backend.py" and BACKEND_LIBS.search(p.read_text())]
    assert not offenders, f"import geometry libraries only in shapewright/backend.py: {offenders}"


# Triangle counts are part of the *source-level* contract: budgets are written
# against them. A backend change that alters them must be deliberate.
@pytest.mark.parametrize("expr,tris", [
    ({"type": "box", "size": [1, 1, 1]}, 12),
    ({"type": "chamfer_box", "size": [1, 1, 1], "chamfer": 0.1}, 44),
    ({"type": "cylinder", "radius": 1, "height": 1, "segments": 8}, 4 * 8 - 4),
    ({"type": "cylinder", "radius": 1, "height": 1, "segments": 8, "chamfer": 0.1}, 8 * 8 - 4),
    ({"type": "sphere", "radius": 1, "segments": 8, "rings": 4}, 2 * 8 * 4 - 2 * 8),
    ({"type": "torus", "radius": 1, "tube": 0.2, "segments": 8, "sides": 4}, 2 * 8 * 4),
    ({"type": "ring", "radius": 1, "thickness": 0.1, "height": 0.1, "segments": 8}, 8 * 8),
    ({"type": "tube", "path": [[0, 0, 0], [0, 1, 0], [1, 1, 0]], "radius": 0.1, "sides": 6}, 2 * 6 * 2 + 2 * 4),
])
def test_generator_topology_contract(expr, tris):
    ctx = Ctx()
    m = build_geometry(expr, {}, ctx, "t")
    assert not ctx.issues
    assert m.n_tris == tris
