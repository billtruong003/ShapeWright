import sys, hashlib
sys.path.insert(0, ".")
import numpy as np
from shapewright.ops import shapes
from shapewright.mesh import geometry_hash
from shapewright.assemble import build
class B:  # minimal build context for shape functions
    env = {}
m = shapes.chamfer_box({"size": [0.07, 0.40, 0.07], "chamfer": 0.01}, B())
print("chamfer_box", len(m.V), len(m.F), geometry_hash(m))
# which vertex pairs are joined by a diagonal inside each flat face: set of sorted vertex-position pairs
fn, _ = m.face_normals()
edges = set()
for f in m.F:
    for i in range(3):
        a, b = sorted((tuple(np.round(m.V[f[i]], 6)), tuple(np.round(m.V[f[(i + 1) % 3]], 6))))
        edges.add((a, b))
print("edge set hash", hashlib.sha256(repr(sorted(edges)).encode()).hexdigest()[:16])
for name in ("tavern_chair",):
    for p in build(f"assets/{name}").parts[:3]:
        print(p.name, geometry_hash(p.mesh), round(p.mesh.volume(), 9))
