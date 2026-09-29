"""Modifiers: mesh -> mesh operations applied in part-local space.

Local space: the part mesh is centred on its bounding box before the first op,
so deformers can use normalized coordinates (0 at the bbox minimum, 1 at the
maximum along an axis) that do not depend on where the part ends up.
"""

from __future__ import annotations

import numpy as np

from ..limits import LIMITS
from ..mesh import Mesh, from_manifold, rotation_matrix, scale_matrix, to_manifold, translation_matrix
from ..registry import Param, op

AX = {"x": 0, "y": 1, "z": 2}


def _t(mesh: Mesh, axis: str) -> tuple[np.ndarray, float, float]:
    i = AX[axis]
    lo, hi = mesh.V[:, i].min(), mesh.V[:, i].max()
    span = max(hi - lo, 1e-12)
    return (mesh.V[:, i] - lo) / span, lo, span


# ------------------------------------------------------------------ transforms


@op("scale", "Scale in local space.", [Param("factor", "num|vec3", doc="uniform number or [x, y, z]")], category="transform", example="{type: scale, factor: [1, 1.2, 1]}")
def scale(m, a, b):
    return m.transformed(scale_matrix(a["factor"]))


@op("rotate", "Rotate in local space (degrees, X then Y then Z).", [Param("angles", "vec3", doc="[rx, ry, rz] degrees")], category="transform", example="{type: rotate, angles: [0, 45, 0]}")
def rotate(m, a, b):
    return m.transformed(rotation_matrix(a["angles"]))


@op("translate", "Move in local space (mostly useful before booleans).", [Param("offset", "vec3", doc="[x, y, z]")], category="transform", example="{type: translate, offset: [0, 0.1, 0]}")
def translate(m, a, b):
    return m.transformed(translation_matrix(a["offset"]))


# ------------------------------------------------------------------ deformers


@op("taper", "Scale the cross-section linearly along an axis (1 at the min end, `scale` at the max end).",
    [Param("axis", "axis", "y", "taper axis"), Param("scale", "num|vec3", 0.8, "end scale; number or per-axis [x, y, z]")],
    category="deform", example="{type: taper, axis: y, scale: 0.8}")
def taper(m, a, b):
    t, _, _ = _t(m, a["axis"])
    s = np.broadcast_to(np.asarray(a["scale"], dtype=np.float64), (3,)).copy()
    s[AX[a["axis"]]] = 1.0
    c = m.center()
    k = 1 + (s[None, :] - 1) * t[:, None]
    return Mesh(c + (m.V - c) * k, m.F)


@op("bend", "Bend along `axis` toward `toward` by `angle` degrees (circular arc).",
    [Param("axis", "axis", "y", "axis along which the part is bent"), Param("toward", "axis", "z", "direction the tip moves"),
     Param("angle", "num", 20.0, "total bend angle in degrees (negative bends the other way)")],
    category="deform", example="{type: bend, axis: y, toward: z, angle: -12}")
def bend(m, a, b):
    ang = np.radians(a["angle"])
    if abs(ang) < 1e-9:
        return m.copy()
    i, j = AX[a["axis"]], AX[a["toward"]]
    if i == j:
        raise ValueError("bend axis and toward must differ")
    t, lo, span = _t(m, a["axis"])
    R = span / ang
    theta = t * ang
    V = m.V.copy()
    d = R - m.V[:, j]
    V[:, j] = R - d * np.cos(theta)
    V[:, i] = lo + d * np.sin(theta)
    return Mesh(V, m.F)


@op("twist", "Rotate cross-sections progressively around an axis.",
    [Param("axis", "axis", "y", "twist axis"), Param("angle", "num", 30.0, "total twist in degrees")], category="deform", example="{type: twist, axis: y, angle: 20}")
def twist(m, a, b):
    t, _, _ = _t(m, a["axis"])
    i = AX[a["axis"]]
    p, q = [k for k in range(3) if k != i]
    th = np.radians(a["angle"]) * t
    c = m.center()
    V = m.V.copy()
    x, y = m.V[:, p] - c[p], m.V[:, q] - c[q]
    V[:, p] = c[p] + x * np.cos(th) - y * np.sin(th)
    V[:, q] = c[q] + x * np.sin(th) + y * np.cos(th)
    return Mesh(V, m.F)


@op("shear", "Offset along `toward` proportionally to position along `axis` (lean).",
    [Param("axis", "axis", "y", "reference axis"), Param("toward", "axis", "z", "offset direction"), Param("amount", "num", doc="offset at the max end in metres")],
    category="deform", example="{type: shear, axis: y, toward: z, amount: -0.04}")
def shear(m, a, b):
    t, _, _ = _t(m, a["axis"])
    V = m.V.copy()
    V[:, AX[a["toward"]]] += t * a["amount"]
    return Mesh(V, m.F)


def _vertex_normals(m: Mesh) -> np.ndarray:
    fn, area = m.face_normals()
    N = np.zeros_like(m.V)
    for k in range(3):
        np.add.at(N, m.F[:, k], fn * area[:, None])
    length = np.linalg.norm(N, axis=1)
    return N / np.where(length > 0, length, 1)[:, None]


@op("jitter", "Seeded random vertex offsets: hand-crafted asymmetry for stylized props. Keeps shared vertices welded.",
    [Param("amount", "num|vec3", doc="max offset in metres (number or per-axis)"), Param("seed", "int", 0, "random seed")],
    category="stylize", example="{type: jitter, amount: 0.004, seed: 7}")
def jitter(m, a, b):
    rng = np.random.default_rng(a["seed"])
    amt = np.broadcast_to(np.asarray(a["amount"], dtype=np.float64), (3,))
    return Mesh(m.V + rng.uniform(-1, 1, size=m.V.shape) * amt, m.F)


@op("noise", "Smooth seeded displacement along vertex normals (organic lumps, rock surfaces).",
    [Param("amount", "num", doc="max displacement in metres"), Param("frequency", "num", 4.0, "features per metre"),
     Param("seed", "int", 0, "random seed"), Param("octaves", "int", 3, "detail layers", min=1, max=6)],
    category="organic", example="{type: noise, amount: 0.03, frequency: 5, seed: 2}")
def noise(m, a, b):
    rng = np.random.default_rng(a["seed"])
    field = np.zeros(len(m.V))
    total = 0.0
    for o in range(a["octaves"]):
        f, w = a["frequency"] * (2 ** o), 0.5 ** o
        for _ in range(4):
            d = rng.normal(size=3)
            d /= np.linalg.norm(d)
            field += w / 4 * np.sin(m.V @ d * f * 2 * np.pi + rng.uniform(0, 2 * np.pi))
            total += w / 4
    field /= total
    return Mesh(m.V + _vertex_normals(m) * (field * a["amount"])[:, None], m.F)


@op("inflate", "Push vertices along their normals (positive grows, negative shrinks).",
    [Param("amount", "num", doc="offset in metres")], category="organic", example="{type: inflate, amount: 0.005}")
def inflate(m, a, b):
    return Mesh(m.V + _vertex_normals(m) * a["amount"], m.F)


@op("subdivide", "Split every triangle into four (midpoint; shape unchanged). Use before smooth/noise.",
    [Param("iterations", "int", 1, "1..3", min=1, max=LIMITS.max_subdivide_iterations)], category="topology", example="{type: subdivide, iterations: 1}")
def subdivide(m, a, b):
    import trimesh

    V, F = m.V, m.F
    for _ in range(a["iterations"]):
        V, F = trimesh.remesh.subdivide(V, F)
    return Mesh(V, F)


@op("smooth", "Taubin smoothing (rounds forms without shrinking much).",
    [Param("iterations", "int", 5, "passes", min=1, max=100), Param("strength", "num", 0.5, "0..1", min=0, max=1)], category="organic", example="{type: smooth, iterations: 5, strength: 0.5}")
def smooth(m, a, b):
    import trimesh

    t = m.to_trimesh()
    trimesh.smoothing.filter_taubin(t, lamb=a["strength"], iterations=a["iterations"])
    return Mesh(t.vertices, t.faces)


@op("decimate", "Reduce triangles with quadric simplification (fast-simplification).",
    [Param("ratio", "num", 0.5, "fraction of triangles to keep", min=0.01, max=1)], category="topology", example="{type: decimate, ratio: 0.5}")
def decimate(m, a, b):
    import fast_simplification

    V, F = fast_simplification.simplify(m.V.astype(np.float32), m.F.astype(np.int32), target_reduction=1 - a["ratio"])
    return Mesh(V, F).merged()


@op("flat_bottom", "Cut everything below a height (fraction of local height from the bottom) to create a flat base.",
    [Param("fraction", "num", 0.15, "0..0.9 of the height removed from the bottom", min=0, max=0.9)], category="boolean",
    example="{type: flat_bottom, fraction: 0.2}")
def flat_bottom(m, a, b):
    lo, hi = m.V[:, 1].min(), m.V[:, 1].max()
    cut = lo + (hi - lo) * a["fraction"]
    return from_manifold(to_manifold(m).trim_by_plane([0, 1, 0], cut)).merged()


def _cutter(a, b) -> Mesh:
    tool = b.build_shape(a["shape"], "shape")
    if a["rotate"] is not None:
        tool = tool.transformed(rotation_matrix(a["rotate"]))
    return tool.translated(a["position"])


_BOOL_PARAMS = [
    Param("shape", "shape", doc="nested shape definition, e.g. {type: cylinder, ...}"),
    Param("position", "vec3", [0.0, 0.0, 0.0], "centre of the tool shape in part-local space"),
    Param("rotate", "vec3", None, "tool rotation [rx, ry, rz] degrees"),
]


@op("subtract", "Boolean difference with a tool shape (holes, notches, cut-outs). Uses Manifold.", _BOOL_PARAMS, category="boolean",
    example="{type: subtract, shape: {type: box, size: [0.1, 0.1, 0.2]}, position: [0, 0.1, 0]}")
def subtract(m, a, b):
    return from_manifold(to_manifold(m) - to_manifold(_cutter(a, b))).merged()


@op("union", "Boolean union with an extra shape (fuses into one closed surface).", _BOOL_PARAMS, category="boolean", example="{type: union, shape: {type: cylinder, radius: 0.05, height: 0.8}, position: [0, 0, 0]}")
def union(m, a, b):
    return from_manifold(to_manifold(m) + to_manifold(_cutter(a, b))).merged()


@op("intersect", "Boolean intersection with a tool shape.", _BOOL_PARAMS, category="boolean", example="{type: intersect, shape: {type: sphere, radius: 0.3}}")
def intersect(m, a, b):
    return from_manifold(to_manifold(m) ^ to_manifold(_cutter(a, b))).merged()
