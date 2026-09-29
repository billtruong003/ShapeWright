"""Spatial queries: measure already-built parts instead of re-deriving geometry.

A part may declare ``measure:``: named queries evaluated against parts that
were built before it. Results are read-only namespaces usable in any of the
part's expressions (shape sizes, positions, rotations, ops):

    measure:
      post: {section: rear_leg_right, axis: y, at: rail_y}          # real cross-section of the post at that height
      span: {gap: [front_leg_left, front_leg_right], axis: x,        # free interval between the legs' inner surfaces
             section: {axis: y, at: stretcher_y}}
    shape: {type: chamfer_box, size: [span.length + 0.02, s, s]}
    position: [span.center, stretcher_y, post.center.z]

Queries look at the actual surface (not only bounding boxes), so a sheared,
bent, splayed or tapered neighbour is handled without the author reproducing
its math. They are deterministic, need no solver, and fail loudly (with the
part and query named) when a query has no answer (e.g. a section plane misses
the part).
"""

from __future__ import annotations

import numpy as np

from . import backend
from .expr import Namespace
from .mesh import Mesh

AX = {"x": 0, "y": 1, "z": 2}
QUERY_KINDS = {
    "section": "cross-section of a part's surface with a plane: {section: part, axis: y, at: h} -> min/max/center/size (x,y,z)",
    "gap": "free interval between two parts along an axis, optionally measured in a section plane: "
           "{gap: [a, b], axis: x, section: {axis: y, at: h}} -> start, end, length, center",
    "bounds": "bounding box of a part: {bounds: part} -> min/max/center/size, width/height/depth",
    "anchor": "anchor point of a part: {anchor: part, at: top_front} -> x, y, z",
    "ray": "first hit of a ray on a part: {ray: part, from: [x,y,z], dir: [dx,dy,dz]} -> x, y, z, distance",
}


class QueryError(ValueError):
    pass


def vec_ns(v, label: str) -> Namespace:
    return Namespace({"x": float(v[0]), "y": float(v[1]), "z": float(v[2])}, label)


def box_ns(bounds: np.ndarray, label: str) -> Namespace:
    size = bounds[1] - bounds[0]
    return Namespace({
        "min": vec_ns(bounds[0], label + ".min"), "max": vec_ns(bounds[1], label + ".max"),
        "center": vec_ns((bounds[0] + bounds[1]) / 2, label + ".center"), "size": vec_ns(size, label + ".size"),
        "width": float(size[0]), "height": float(size[1]), "depth": float(size[2]),
    }, label)


def _section(mesh: Mesh, axis: str, at: float, who: str) -> np.ndarray:
    pts = backend.section_points(mesh, AX[axis], at)
    if len(pts) == 0:
        lo, hi = mesh.bounds()[:, AX[axis]]
        raise QueryError(f"section plane {axis}={at:.4f} misses '{who}' (it spans {axis} {lo:.4f}..{hi:.4f})")
    return np.stack([pts.min(0), pts.max(0)])


def section(mesh: Mesh, axis: str, at: float, who: str) -> Namespace:
    return box_ns(_section(mesh, axis, at, who), f"section({who})")


def gap(a: Mesh, b: Mesh, axis: str, names: tuple[str, str], sec: tuple[str, float] | None = None) -> Namespace:
    i = AX[axis]
    ba = _section(a, *sec, names[0]) if sec else a.bounds()
    bb = _section(b, *sec, names[1]) if sec else b.bounds()
    if (ba[0][i] + ba[1][i]) > (bb[0][i] + bb[1][i]):
        ba, bb = bb, ba
        names = names[::-1]
    start, end = float(ba[1][i]), float(bb[0][i])
    if end < start:
        raise QueryError(f"'{names[0]}' and '{names[1]}' overlap along {axis} (no gap: {start:.4f} > {end:.4f})")
    return Namespace({"start": start, "end": end, "length": end - start, "center": (start + end) / 2}, f"gap({names[0]},{names[1]})")


def ray(mesh: Mesh, origin, direction, who: str) -> Namespace:
    t, f = backend.raycast(mesh, [origin], [direction])
    if f[0] < 0:
        raise QueryError(f"ray from {list(np.round(origin, 4))} along {list(np.round(direction, 3))} misses '{who}'")
    d = np.asarray(direction, dtype=np.float64)
    p = np.asarray(origin, dtype=np.float64) + d / np.linalg.norm(d) * t[0]
    return Namespace({"x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "distance": float(t[0])}, f"ray({who})")
