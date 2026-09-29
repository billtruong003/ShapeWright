"""Modifiers: mesh -> mesh operations applied in expression-local space.

Local space: a geometry expression is centred on its bounding box before its
first op, so deformers can use normalized coordinates (0 at the bbox minimum,
1 at the maximum along an axis) that do not depend on where the part ends up.

Every op declares a ``topology`` class, which is its attribute contract
(docs/MESH_MODEL.md):

    preserve  vertices move, topology and all attributes are kept
    refine    faces split; face attributes inherited, vertex/corner interpolated
    rebuild   new topology with provenance; faces inherit, corners invalidated
    resample  new topology without provenance; attributes transferred by nearest
"""

from __future__ import annotations

import numpy as np

from .. import backend
from ..limits import LIMITS
from ..mesh import Mesh, concat, rotation_matrix, scale_matrix, translation_matrix
from ..registry import Param, op

AX = {"x": 0, "y": 1, "z": 2}


def _t(mesh: Mesh, axis: str) -> tuple[np.ndarray, float, float]:
    i = AX[axis]
    lo, hi = mesh.V[:, i].min(), mesh.V[:, i].max()
    span = max(hi - lo, 1e-12)
    return (mesh.V[:, i] - lo) / span, lo, span


# ------------------------------------------------------------------ transforms (preserve)


@op("scale", "Scale in local space.", [Param("factor", "num|vec3", doc="uniform number or [x, y, z]")], "preserve",
    category="transform", example="{type: scale, factor: [1, 1.2, 1]}")
def scale(m, a, b):
    return m.transformed(scale_matrix(a["factor"]))


@op("rotate", "Rotate in local space (degrees, X then Y then Z).", [Param("angles", "vec3", doc="[rx, ry, rz] degrees")], "preserve",
    category="transform", example="{type: rotate, angles: [0, 45, 0]}")
def rotate(m, a, b):
    return m.transformed(rotation_matrix(a["angles"]))


@op("translate", "Move in local space (mostly useful inside nested expressions).", [Param("offset", "vec3", doc="[x, y, z]")], "preserve",
    category="transform", example="{type: translate, offset: [0, 0.1, 0]}")
def translate(m, a, b):
    return m.transformed(translation_matrix(a["offset"]))


# ------------------------------------------------------------------ deformers (preserve)


@op("taper", "Scale the cross-section linearly along an axis (1 at the min end, `scale` at the max end).",
    [Param("axis", "axis", "y", "taper axis"), Param("scale", "num|vec3", 0.8, "end scale; number or per-axis [x, y, z]")], "preserve",
    category="deform", example="{type: taper, axis: y, scale: 0.8}")
def taper(m, a, b):
    t, _, _ = _t(m, a["axis"])
    s = np.broadcast_to(np.asarray(a["scale"], dtype=np.float64), (3,)).copy()
    s[AX[a["axis"]]] = 1.0
    c = m.center()
    k = 1 + (s[None, :] - 1) * t[:, None]
    return m.with_positions(c + (m.V - c) * k)


@op("bend", "Bend along `axis` toward `toward` by `angle` degrees (circular arc). Needs vertices along the axis (subdivide first).",
    [Param("axis", "axis", "y", "axis along which the part is bent"), Param("toward", "axis", "z", "direction the tip moves"),
     Param("angle", "num", 20.0, "total bend angle in degrees (negative bends the other way)")], "preserve",
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
    return m.with_positions(V)


@op("twist", "Rotate cross-sections progressively around an axis.",
    [Param("axis", "axis", "y", "twist axis"), Param("angle", "num", 30.0, "total twist in degrees")], "preserve",
    category="deform", example="{type: twist, axis: y, angle: 20}")
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
    return m.with_positions(V)


@op("shear", "Offset along `toward` proportionally to position along `axis` (lean).",
    [Param("axis", "axis", "y", "reference axis"), Param("toward", "axis", "z", "offset direction"), Param("amount", "num", doc="offset at the max end in metres")],
    "preserve", category="deform", example="{type: shear, axis: y, toward: z, amount: -0.04}")
def shear(m, a, b):
    t, _, _ = _t(m, a["axis"])
    V = m.V.copy()
    V[:, AX[a["toward"]]] += t * a["amount"]
    return m.with_positions(V)


def _vertex_normals(m: Mesh) -> np.ndarray:
    fn, area = m.face_normals()
    N = np.zeros_like(m.V)
    for k in range(3):
        np.add.at(N, m.F[:, k], fn * area[:, None])
    length = np.linalg.norm(N, axis=1)
    return N / np.where(length > 0, length, 1)[:, None]


@op("jitter", "Seeded random vertex offsets: hand-crafted asymmetry for stylized props. Keeps shared vertices welded.",
    [Param("amount", "num|vec3", doc="max offset in metres (number or per-axis)"), Param("seed", "int", 0, "random seed")], "preserve",
    category="stylize", example="{type: jitter, amount: 0.004, seed: 7}")
def jitter(m, a, b):
    rng = np.random.default_rng(a["seed"])
    amt = np.broadcast_to(np.asarray(a["amount"], dtype=np.float64), (3,))
    return m.with_positions(m.V + rng.uniform(-1, 1, size=m.V.shape) * amt)


@op("noise", "Smooth seeded displacement along vertex normals (organic lumps, rock surfaces).",
    [Param("amount", "num", doc="max displacement in metres"), Param("frequency", "num", 4.0, "features per metre"),
     Param("seed", "int", 0, "random seed"), Param("octaves", "int", 3, "detail layers", min=1, max=6)], "preserve",
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
    return m.with_positions(m.V + _vertex_normals(m) * (field * a["amount"])[:, None])


@op("inflate", "Push vertices along their normals (positive grows, negative shrinks).",
    [Param("amount", "num", doc="offset in metres")], "preserve", category="organic", example="{type: inflate, amount: 0.005}")
def inflate(m, a, b):
    return m.with_positions(m.V + _vertex_normals(m) * a["amount"])


@op("smooth", "Taubin smoothing (rounds forms without shrinking much).",
    [Param("iterations", "int", 5, "passes", min=1, max=100), Param("strength", "num", 0.5, "0..1", min=0, max=1)], "preserve",
    category="organic", example="{type: smooth, iterations: 5, strength: 0.5}")
def smooth(m, a, b):
    return backend.smooth_taubin(m, a["iterations"], a["strength"])


# ------------------------------------------------------------------ topology


@op("subdivide", "Split every triangle into four (midpoint; shape unchanged). Use before smooth/noise/bend.",
    [Param("iterations", "int", 1, "1..3", min=1, max=LIMITS.max_subdivide_iterations)], "refine",
    category="topology", example="{type: subdivide, iterations: 1}")
def subdivide(m, a, b):
    for _ in range(a["iterations"]):
        m = backend.subdivide_midpoint(m)
    return m


@op("decimate", "Reduce triangles with quadric simplification.",
    [Param("ratio", "num", 0.5, "fraction of triangles to keep", min=0.01, max=1)], "resample",
    category="topology", example="{type: decimate, ratio: 0.5}")
def decimate(m, a, b):
    return backend.simplify(m, a["ratio"]).merged()


# ------------------------------------------------------------------ booleans (rebuild)


def _tool(a, b) -> Mesh:
    tool = b.build_geometry(a["shape"], "shape")
    if a["rotate"] is not None:
        tool = tool.transformed(rotation_matrix(a["rotate"]))
    return tool.translated(a["position"])


_BOOL_PARAMS = [
    Param("shape", "geometry", doc="tool geometry expression (may have its own ops, material, rotate, translate)"),
    Param("position", "vec3", [0.0, 0.0, 0.0], "centre of the tool in local space"),
    Param("rotate", "vec3", None, "tool rotation [rx, ry, rz] degrees"),
]


@op("subtract", "Boolean difference with a tool geometry (holes, notches, cut-outs). Cut faces keep the tool's provenance/material.",
    _BOOL_PARAMS, "rebuild", category="boolean",
    example="{type: subtract, shape: {type: box, size: [0.1, 0.1, 0.2], ops: [{type: taper, scale: 0.5}]}, position: [0, 0.1, 0]}")
def subtract(m, a, b):
    return backend.boolean(m, _tool(a, b), "difference").merged()


@op("union", "Boolean union with extra geometry (fuses into one closed surface).", _BOOL_PARAMS, "rebuild", category="boolean",
    example="{type: union, shape: {type: cylinder, radius: 0.05, height: 0.8}, position: [0, 0, 0]}")
def union(m, a, b):
    return backend.boolean(m, _tool(a, b), "union").merged()


@op("intersect", "Boolean intersection with a tool geometry.", _BOOL_PARAMS, "rebuild", category="boolean",
    example="{type: intersect, shape: {type: sphere, radius: 0.3}}")
def intersect(m, a, b):
    return backend.boolean(m, _tool(a, b), "intersection").merged()


@op("flat_bottom", "Cut everything below a height (fraction of local height from the bottom) to create a flat base.",
    [Param("fraction", "num", 0.15, "0..0.9 of the height removed from the bottom", min=0, max=0.9)], "rebuild", category="boolean",
    example="{type: flat_bottom, fraction: 0.2}")
def flat_bottom(m, a, b):
    lo, hi = m.V[:, 1].min(), m.V[:, 1].max()
    cut = lo + (hi - lo) * a["fraction"]
    out = backend.trim(m, [0, 1, 0], cut).merged()
    new = out.fattr["origin"] < 0 if "origin" in out.fattr else np.zeros(out.n_tris, bool)
    if new.any():
        out.set_label("region", "cut", new)
        out.set_label("origin", b.where, new)
    return out


# ------------------------------------------------------------------ geometry-level repetition


@op("mirror", "Mirror the geometry across a local plane and keep both halves in this part "
    "(`merge: union` fuses overlapping halves; `combine` keeps two shells). For separate named twins use part-level `mirror:`.",
    [Param("axis", "axis", "x", "mirror axis"), Param("at", "num", 0.0, "plane position along the axis (local space)"),
     Param("merge", "str", "combine", "combine | union", choices=("combine", "union"))], "rebuild",
    category="repeat", example="{type: mirror, axis: x, at: 0.3, merge: combine}")
def mirror(m, a, b):
    i = AX[a["axis"]]
    M = np.eye(4)
    M[i, i] = -1
    M[i, 3] = 2 * a["at"]
    twin = m.transformed(M)
    if a["merge"] == "union":
        return backend.boolean(m, twin, "union").merged()
    return concat([m, twin])


@op("repeat", "Repeat the geometry inside this part (linear offset or radial around a local axis); copies stay one part.",
    [Param("count", "int", doc="number of copies", min=1, max=LIMITS.max_array_count),
     Param("offset", "vec3", [0.0, 0.0, 0.0], "linear step"), Param("radial", "str", "", "axis for radial repetition: x | y | z", choices=("", "x", "y", "z")),
     Param("angle", "num", 360.0, "radial sweep in degrees")], "rebuild",
    category="repeat", example="{type: repeat, count: 3, offset: [0.3, 0, 0]}")
def repeat(m, a, b):
    copies = []
    n = a["count"]
    for i in range(n):
        if a["radial"]:
            step = a["angle"] / n if abs(a["angle"] - 360) < 1e-9 else a["angle"] / max(n - 1, 1)
            rot = [0.0, 0.0, 0.0]
            rot[AX[a["radial"]]] = step * i
            copies.append(m.transformed(rotation_matrix(rot)))
        else:
            copies.append(m.translated(np.asarray(a["offset"]) * i))
    return concat(copies)
