"""Shape generators. Every generator returns a closed, outward-wound mesh.

Conventions (see docs/ASSET_FORMAT.md): metres, Y up, the front of an asset
faces +Z. Generators may build around any origin; the assembler recentres each
part on its bounding-box centre before ops and placement.
"""

from __future__ import annotations

import math

import numpy as np

from ..curves import expand_points
from ..limits import LIMITS, check
from .. import backend
from ..mesh import Mesh
from ..registry import Param, shape

SEG = dict(min=3, max=LIMITS.max_segments)


def _finish(mesh: Mesh) -> Mesh:
    return mesh.merged().oriented_outward()


def lathe_mesh(profile: list[tuple[float, float]], segments: int) -> Mesh:
    """Revolve (radius, y) profile points around the Y axis.

    Points with radius 0 become poles; open ends with radius > 0 are capped.
    """
    check(segments, LIMITS.max_segments, "segments")
    ang = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    V: list = []
    rings: list = []  # each: ("pole", idx) or ("ring", start)
    for r, y in profile:
        if abs(r) < 1e-9:
            rings.append(("pole", len(V)))
            V.append((0.0, y, 0.0))
        else:
            rings.append(("ring", len(V)))
            V.extend((r * math.cos(a), y, -r * math.sin(a)) for a in ang)
    F: list = []
    n = segments
    for (ka, a), (kb, b) in zip(rings[:-1], rings[1:]):
        for k in range(n):
            k1 = (k + 1) % n
            if ka == "ring" and kb == "ring":
                F.append((a + k, a + k1, b + k1))
                F.append((a + k, b + k1, b + k))
            elif ka == "pole" and kb == "ring":
                F.append((a, b + k1, b + k))
            elif ka == "ring" and kb == "pole":
                F.append((a + k, a + k1, b))
    if rings[0][0] == "ring":
        a = rings[0][1]
        F.extend((a, a + k + 1, a + k) for k in range(1, n - 1))
    if rings[-1][0] == "ring":
        a = rings[-1][1]
        F.extend((a, a + k, a + k + 1) for k in range(1, n - 1))
    return _finish(Mesh(np.array(V), np.array(F)))


@shape("box", "Axis-aligned box.", [Param("size", "vec3", doc="[width x, height y, depth z] in metres")],
       example="{type: box, size: [0.4, 0.05, 0.4]}")
def box(a, b):
    return _finish(backend.box(a["size"]))


@shape("chamfer_box", "Box with every edge chamfered (44 triangles). The workhorse of stylized low-poly props.",
       [Param("size", "vec3", doc="[x, y, z] outer size"),
        Param("chamfer", "num", 0.01, "chamfer width in metres (clamped to 45% of the smallest side)", min=0)],
       example="{type: chamfer_box, size: [0.46, 0.06, 0.44], chamfer: 0.012}")
def chamfer_box(a, b):
    s = np.maximum(np.asarray(a["size"]), 1e-6)
    c = min(a["chamfer"], 0.45 * s.min())
    if c <= 1e-6:
        return box({"size": s}, b)
    pts = []
    for shrink in np.eye(3):
        h = s / 2 - (1 - shrink) * c  # full along one axis, inset along the other two
        pts.extend(np.array(list(np.ndindex(2, 2, 2))) * 2 * h - h)
    return _finish(backend.convex_hull(np.array(pts)))


@shape("cylinder", "Cylinder / frustum / cone along Y, optionally with chamfered rims.",
       [Param("radius", "num", doc="bottom radius", min=0),
        Param("height", "num", doc="height along Y", min=0),
        Param("radius_top", "num", None, "top radius (default = radius; 0 makes a cone)", min=0),
        Param("segments", "int", 12, "sides around the axis", **SEG),
        Param("chamfer", "num", 0.0, "rim chamfer in metres", min=0)],
       example="{type: cylinder, radius: 0.03, height: 0.4, segments: 8}")
def cylinder(a, b):
    r0, h = a["radius"], a["height"]
    r1 = r0 if a["radius_top"] is None else a["radius_top"]
    c = min(a["chamfer"], h * 0.45, *(r for r in (r0, r1) if r > 0))
    y0, y1 = -h / 2, h / 2
    if c > 1e-6:
        prof = [(max(r0 - c, 0), y0), (r0, y0 + c), (r1, y1 - c), (max(r1 - c, 0), y1)] if r1 > 0 else [(max(r0 - c, 0), y0), (r0, y0 + c), (0, y1)]
    else:
        prof = [(r0, y0), (r1, y1)]
    return lathe_mesh(prof, a["segments"])


@shape("sphere", "UV sphere (low-poly friendly: few rings).",
       [Param("radius", "num", doc="radius", min=0),
        Param("segments", "int", 12, "divisions around Y", **SEG),
        Param("rings", "int", 6, "divisions pole to pole", min=2, max=LIMITS.max_segments)],
       example="{type: sphere, radius: 0.1, segments: 10, rings: 6}")
def sphere(a, b):
    r, n = a["radius"], a["rings"]
    prof = [(r * math.sin(math.pi * i / n), -r * math.cos(math.pi * i / n)) for i in range(n + 1)]
    return lathe_mesh(prof, a["segments"])


@shape("icosphere", "Geodesic sphere: evenly distributed triangles, ideal base for organic deformation.",
       [Param("radius", "num", doc="radius", min=0), Param("subdivisions", "int", 1, "0..4", min=0, max=4)],
       example="{type: icosphere, radius: 0.2, subdivisions: 1}")
def icosphere(a, b):
    return _finish(backend.icosphere(a["subdivisions"], a["radius"]))


@shape("capsule", "Capsule along Y (cylinder with hemispherical ends).",
       [Param("radius", "num", doc="radius", min=0), Param("height", "num", doc="total height including caps", min=0),
        Param("segments", "int", 12, "divisions around Y", **SEG), Param("cap_rings", "int", 3, "rings per hemisphere", min=1, max=64)],
       example="{type: capsule, radius: 0.05, height: 0.4, segments: 8}")
def capsule(a, b):
    r, n = a["radius"], a["cap_rings"]
    half = max(a["height"] / 2 - r, 0)
    bottom = [(r * math.sin(math.pi / 2 * i / n), -half - r * math.cos(math.pi / 2 * i / n)) for i in range(n + 1)]
    top = [(r * math.cos(math.pi / 2 * i / n), half + r * math.sin(math.pi / 2 * i / n)) for i in range(n + 1)]
    return lathe_mesh(bottom + top, a["segments"])


@shape("torus", "Torus around Y (rings, hoops, handles).",
       [Param("radius", "num", doc="ring radius to tube centre", min=0), Param("tube", "num", doc="tube radius", min=0),
        Param("segments", "int", 16, "divisions around the ring", **SEG), Param("sides", "int", 6, "divisions around the tube", **SEG)],
       example="{type: torus, radius: 0.25, tube: 0.012, segments: 16, sides: 4}")
def torus(a, b):
    R, r, n, m = a["radius"], a["tube"], a["segments"], a["sides"]
    u = np.linspace(0, 2 * np.pi, n, endpoint=False)
    v = np.linspace(0, 2 * np.pi, m, endpoint=False)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    V = np.stack([(R + r * np.cos(vv)) * np.cos(uu), r * np.sin(vv), -(R + r * np.cos(vv)) * np.sin(uu)], -1).reshape(-1, 3)
    F = []
    for i in range(n):
        for j in range(m):
            a0, a1 = i * m + j, i * m + (j + 1) % m
            b0, b1 = ((i + 1) % n) * m + j, ((i + 1) % n) * m + (j + 1) % m
            F += [(a0, b0, b1), (a0, b1, a1)]
    return _finish(Mesh(V, np.array(F)))


@shape("lathe", "Revolve a profile of [radius, y] points around Y (barrels, bottles, lamp posts, mugs). "
       "Radius 0 closes the end at a pole; otherwise ends are capped.",
       [Param("profile", "points2", doc="[[radius, y], ...] from bottom to top"),
        Param("segments", "int", 12, "divisions around Y", **SEG)],
       example="{type: lathe, profile: [[0.2, 0], [0.24, 0.3], [0.2, 0.6]], segments: 12}")
def lathe(a, b):
    check(2 * len(a["profile"]) * a["segments"], LIMITS.max_triangles_per_part, "triangles of this lathe")
    return lathe_mesh([tuple(p) for p in a["profile"]], a["segments"])


@shape("extrude", "Extrude a 2D polygon (XY plane) along Z; supports holes and tapering. Robust via Manifold.",
       [Param("polygon", "points2", doc="outer contour [[x, y], ...]"),
        Param("depth", "num", doc="extrusion depth along Z", min=0),
        Param("holes", "list", [], "list of inner contours"),
        Param("scale_top", "vec2", [1.0, 1.0], "XY scale of the far face (taper), about the polygon's own origin (0, 0), not its centre"),
        Param("chamfer", "num", 0.0, "bevel both caps' edges by this many metres (convex outlines without holes)", min=0)],
       example="{type: extrude, polygon: [[-0.2,0],[0.2,0],[0.15,0.3],[-0.15,0.3]], depth: 0.04, chamfer: 0.005}")
def extrude(a, b):
    outer = np.array(a["polygon"], dtype=np.float64)
    if len(outer) > 3 and np.allclose(outer[0], outer[-1]):
        outer = outer[:-1]  # generators (full arcs) may close the loop explicitly
    if a["chamfer"] > 0:
        return _finish(_chamfered_extrude(outer, a["depth"], a["chamfer"], a["holes"], a["scale_top"]))
    contours = [outer]
    for i, hole in enumerate(a["holes"] or []):
        pts = expand_points(hole, 2, b.env, f"{b.where}.holes[{i}]", b.ctx)
        if pts is None:
            raise ValueError(f"invalid hole {i}")
        contours.append(np.array(pts, dtype=np.float64))
    fixed = []
    for c in contours:
        area = 0.5 * np.sum(c[:, 0] * np.roll(c[:, 1], -1) - np.roll(c[:, 0], -1) * c[:, 1])
        fixed.append(c if (area > 0) == (len(fixed) == 0) else c[::-1])
    return _finish(backend.extrude_polygon(fixed, a["depth"], a["scale_top"]))


@shape("strut", "A beam, brace, rod or post running from one point to another (braces, rafters, rungs, axles, legs). "
       "Box section with `size`, or round with `radius`. A part whose shape is a strut keeps its asset coordinates "
       "(origin: keep), so `from`/`to` are where the ends go; they may use params and `measure` results.",
       [Param("from", "vec3", doc="start point [x, y, z] (asset coordinates)"),
        Param("to", "vec3", doc="end point [x, y, z]"),
        Param("size", "vec2", None, "[width, depth] of a box section; depth lies along the horizontal normal of the strut's vertical plane"),
        Param("radius", "num", None, "round section radius (instead of size)", min=0),
        Param("sides", "int", 8, "sides of a round section", **SEG),
        Param("chamfer", "num", 0.0, "edge chamfer in metres", min=0),
        Param("extend", "num", 0.0, "extra length past each end (to bury ends in what they join)", min=0),
        Param("roll", "num", 0.0, "rotation about the strut's own axis, degrees"),
        Param("depth_axis", "str", "auto", "which asset axis the section's depth faces: auto (normal of the strut's vertical "
              "plane) | x | y | z; set it so a row of leaning legs keeps one orientation", choices=("auto", "x", "y", "z"))],
       example="{type: strut, from: [-0.4, 0.1, 0], to: [0.4, 0.9, 0], size: [0.08, 0.06], chamfer: 0.008}")
def strut(a, b):
    p0, p1 = np.asarray(a["from"], dtype=np.float64), np.asarray(a["to"], dtype=np.float64)
    d = p1 - p0
    length = float(np.linalg.norm(d))
    if length < 1e-6:
        raise ValueError("strut `from` and `to` are the same point")
    y = d / length
    if a["depth_axis"] != "auto":  # the chosen axis, made perpendicular to the strut (FRESH_AGENT_08)
        want = np.eye(3)["xyz".index(a["depth_axis"])]
        z = want - y * (want @ y)
        if np.linalg.norm(z) < 1e-6:
            raise ValueError(f"depth_axis {a['depth_axis']} is parallel to the strut")
    else:
        up = np.array([0.0, 1.0, 0.0]) if abs(y[1]) < 0.99 else np.array([0.0, 0.0, 1.0])
        z = np.cross(y, up)  # depth axis: horizontal, normal to the vertical plane holding the strut
        if abs(y[1]) >= 0.99:
            z = np.array([0.0, 0.0, 1.0])
    z /= np.linalg.norm(z)
    x = np.cross(y, z)
    L = length + 2 * a["extend"]
    if a["size"] is not None:
        mesh = chamfer_box({"size": [a["size"][0], L, a["size"][1]], "chamfer": a["chamfer"]}, b)
    elif a["radius"] is not None:
        mesh = cylinder({"radius": a["radius"], "height": L, "radius_top": None, "segments": a["sides"], "chamfer": a["chamfer"]}, b)
    else:
        raise ValueError("strut needs `size: [width, depth]` or `radius`")
    mesh = mesh.recentered()
    R = np.eye(4)
    roll = np.radians(a["roll"])
    xr, zr = x * np.cos(roll) + z * np.sin(roll), -x * np.sin(roll) + z * np.cos(roll)
    R[:3, :3] = np.stack([xr, y, zr], axis=1)
    R[:3, 3] = (p0 + p1) / 2
    return mesh.transformed(R)


def _turns(P: np.ndarray) -> np.ndarray:
    """z of the cross product of consecutive edges (> 0: left turn) for a 2D polygon."""
    a, b = np.roll(P, -1, 0) - P, np.roll(P, -2, 0) - np.roll(P, -1, 0)
    return a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]


def _inset_convex(P: np.ndarray, d: float) -> np.ndarray:
    """Offset a convex counter-clockwise polygon inward by d (mitred corners)."""
    n = len(P)
    E = np.roll(P, -1, 0) - P
    N = np.stack([-E[:, 1], E[:, 0]], 1) / np.linalg.norm(E, axis=1)[:, None]  # inward for CCW
    out = []
    for i in range(n):
        j = (i - 1) % n
        p1, d1 = P[j] + N[j] * d, E[j]
        p2, d2 = P[i] + N[i] * d, E[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append(p1 + d1 * t)
    Q = np.array(out)
    area = 0.5 * np.sum(Q[:, 0] * np.roll(Q[:, 1], -1) - np.roll(Q[:, 0], -1) * Q[:, 1])
    if area <= 0 or np.any(_turns(Q) < -1e-12):
        raise ValueError(f"chamfer {d:g} is too large for this outline")
    return Q


def _chamfered_extrude(P: np.ndarray, depth: float, c: float, holes, scale_top) -> Mesh:
    if holes:
        raise ValueError("chamfer works on outlines without holes; subtract the hole with an op instead")
    if list(scale_top) != [1.0, 1.0]:
        raise ValueError("chamfer and scale_top cannot be combined; use a taper op after the chamfered extrude")
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    if area < 0:
        P = P[::-1]
    if np.any(_turns(P) < -1e-12):
        raise ValueError("chamfer needs a convex outline; split the shape into convex pieces or bevel with a subtract op")
    if 2 * c >= depth:
        raise ValueError(f"chamfer {c:g} must be less than half the depth {depth:g}")
    Q = _inset_convex(P, c)
    pts = [np.c_[Q, np.zeros(len(Q))], np.c_[P, np.full(len(P), c)], np.c_[P, np.full(len(P), depth - c)], np.c_[Q, np.full(len(Q), depth)]]
    return backend.convex_hull(np.concatenate(pts))


def _round_corners(P: np.ndarray, r: float, k: int) -> np.ndarray:
    """Replace each interior corner of a polyline by a circular arc of radius r (shrunk to fit short segments)."""
    out = [P[0]]
    for i in range(1, len(P) - 1):
        prev, cur, nxt = out[-1], P[i], P[i + 1]
        a, c = prev - cur, nxt - cur
        la, lc = np.linalg.norm(a), np.linalg.norm(c)
        if la < 1e-9 or lc < 1e-9:
            continue
        a, c = a / la, c / lc
        cosang = float(np.clip(a @ c, -1, 1))
        if cosang < -0.9999:  # straight through
            out.append(cur)
            continue
        half = np.arccos(cosang) / 2
        t = min(r / np.tan(half), la * 0.5 if i > 1 else la, lc * 0.5 if i < len(P) - 2 else lc)
        rr = t * np.tan(half)
        bis = (a + c) / np.linalg.norm(a + c)
        C = cur + bis * (rr / np.sin(half))
        u, v = cur + a * t - C, cur + c * t - C
        phi = np.arccos(np.clip(u @ v / max(np.linalg.norm(u) * np.linalg.norm(v), 1e-12), -1, 1))
        for s_ in np.linspace(0, 1, k + 1):
            out.append(C + (np.sin((1 - s_) * phi) * u + np.sin(s_ * phi) * v) / max(np.sin(phi), 1e-12))
    out.append(P[-1])
    Q = [out[0]]
    for q in out[1:]:
        if np.linalg.norm(q - Q[-1]) > 1e-7:
            Q.append(q)
    return np.array(Q)


@shape("tube", "Sweep a regular polygon along a 3D path (pipes, cables, arms, branches, handles).",
       [Param("path", "points3", doc="[[x, y, z], ...] path points"),
        Param("radius", "num", doc="tube radius at the start", min=0),
        Param("radius_end", "num", None, "radius at the end (default = radius)", min=0),
        Param("sides", "int", 6, "sides of the cross-section", **SEG),
        Param("corner_radius", "num", 0.0, "round every interior corner of the path with this bend radius (pipe elbows, bent handles)", min=0),
        Param("corner_segments", "int", 4, "points per rounded corner", min=1, max=32)],
       example="{type: tube, path: [[0,0,0],[0,0.5,0],[0.4,0.5,0]], radius: 0.03, corner_radius: 0.12, sides: 8}")
def tube(a, b):
    P = np.array(a["path"], dtype=np.float64)
    if a["corner_radius"] > 0 and len(P) > 2:
        P = _round_corners(P, a["corner_radius"], a["corner_segments"])
    check(2 * len(P) * a["sides"], LIMITS.max_triangles_per_part, "triangles of this tube")
    n, s = len(P), a["sides"]
    r0 = a["radius"]
    r1 = r0 if a["radius_end"] is None else a["radius_end"]
    seg = np.diff(P, axis=0)
    seglen = np.linalg.norm(seg, axis=1)
    if np.any(seglen < 1e-9):
        raise ValueError("tube path has repeated points")
    seg /= seglen[:, None]
    T = np.zeros_like(P)
    T[0], T[-1] = seg[0], seg[-1]
    T[1:-1] = seg[:-1] + seg[1:]
    T /= np.linalg.norm(T, axis=1)[:, None]
    ref = np.array([0.0, 0.0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    N = np.cross(T[0], ref)
    N /= np.linalg.norm(N)
    V = []
    t_along = np.concatenate([[0], np.cumsum(seglen)]) / seglen.sum()
    ang = np.linspace(0, 2 * np.pi, s, endpoint=False)
    for i in range(n):
        if i > 0:  # parallel transport of the frame
            N = N - T[i] * np.dot(N, T[i])
            N /= np.linalg.norm(N)
        B = np.cross(T[i], N)
        # keep wall thickness at bends: scale by 1/cos(half bend angle)
        k = 1.0
        if 0 < i < n - 1:
            k = 1.0 / max(np.dot(seg[i - 1], T[i]), 0.3)
        r = (r0 + (r1 - r0) * t_along[i]) * k
        V.extend(P[i] + r * (np.cos(t) * N + np.sin(t) * B) for t in ang)
    F = []
    for i in range(n - 1):
        for j in range(s):
            a0, a1 = i * s + j, i * s + (j + 1) % s
            b0, b1 = a0 + s, a1 + s
            F += [(a0, a1, b1), (a0, b1, b0)]
    F += [(0, k + 1, k) for k in range(1, s - 1)]
    last = (n - 1) * s
    F += [(last, last + k, last + k + 1) for k in range(1, s - 1)]
    return _finish(Mesh(np.array(V), np.array(F)))


@shape("random_hull", "Convex hull of seeded random points on an ellipsoid: the classic low-poly rock/boulder/crystal base.",
       [Param("size", "vec3", doc="ellipsoid extents [x, y, z]"),
        Param("points", "int", 24, "number of random points (more = rounder)", min=6, max=2000),
        Param("seed", "int", 0, "random seed (same seed = same shape)")],
       category="procedural", example="{type: random_hull, size: [0.6, 0.4, 0.5], points: 20, seed: 3}")
def random_hull(a, b):
    rng = np.random.default_rng(a["seed"])
    d = rng.normal(size=(a["points"], 3))
    d /= np.linalg.norm(d, axis=1)[:, None]
    return _finish(backend.convex_hull(d * np.asarray(a["size"]) / 2))


def _revolve(polygon, segments: int) -> Mesh:
    c = np.array(polygon, dtype=np.float64)
    area = 0.5 * np.sum(c[:, 0] * np.roll(c[:, 1], -1) - np.roll(c[:, 0], -1) * c[:, 1])
    if area < 0:
        c = c[::-1]
    return _finish(backend.revolve_polygon(c, segments))


@shape("revolve", "Revolve a closed 2D polygon of [radius, y] points around Y (rings, flanges, rims, hollow forms). "
       "Unlike `lathe`, the profile is a closed outline and may stay away from the axis.",
       [Param("polygon", "points2", doc="closed outline [[radius, y], ...], radius >= 0"),
        Param("segments", "int", 12, "divisions around Y", **SEG)],
       example="{type: revolve, polygon: [[0.2, 0], [0.25, 0], [0.25, 0.05], [0.2, 0.05]], segments: 12}")
def revolve(a, b):
    check(2 * len(a["polygon"]) * a["segments"], LIMITS.max_triangles_per_part, "triangles of this revolve")
    if min(p[0] for p in a["polygon"]) < 0:
        raise ValueError("revolve radii must be >= 0")
    return _revolve(a["polygon"], a["segments"])


@shape("ring", "Flat ring / band / washer around Y with a rectangular cross-section (hoops, collars, rims).",
       [Param("radius", "num", doc="outer radius", min=0), Param("thickness", "num", doc="radial thickness", min=0),
        Param("height", "num", doc="band height along Y", min=0), Param("segments", "int", 12, "divisions around Y", **SEG)],
       example="{type: ring, radius: 0.33, thickness: 0.02, height: 0.05, segments: 12}")
def ring(a, b):
    r1, t, h = a["radius"], a["thickness"], a["height"]
    r0 = max(r1 - t, 1e-4)
    return _revolve([[r0, -h / 2], [r1, -h / 2], [r1, h / 2], [r0, h / 2]], a["segments"])
