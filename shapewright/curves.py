"""Point-list generators: arcs, spirals, helices and lines inside any list of points.

Anywhere a shape takes points (`extrude.polygon`/`holes`, `lathe.profile`, `revolve.polygon`,
`tube.path`), an item may be a generator instead of a point. Generators expand in place, so
literal points and generators mix freely:

    polygon: [[-0.5, 0], [0.5, 0], {arc: {center: [0, 0], radius: 0.5, from: 0, to: 180}}]
    path: [[0, 0, 0], [0, 0.4, 0], {arc: {center: [0.2, 0.4, 0], radius: 0.2, from: 180, to: 90, plane: xy}}]
    path: [{helix: {radius: 0.03, pitch: 0.012, turns: 4, axis: y}}]

Evidence: FRESH_AGENT_05, where 6 of 17 assets hand-computed arcs/helices with cos/sin.
"""

from __future__ import annotations

import math
from typing import Any

from .limits import LIMITS
from .registry import suggest

PLANES = {"xy": (0, 1, 2), "xz": (0, 2, 1), "yz": (1, 2, 0), "zy": (2, 1, 0), "yx": (1, 0, 2), "zx": (2, 0, 1)}
GENERATORS = {
    "arc": "points on a circular arc: {center, radius, from, to (degrees, counter-clockwise from the first plane axis), "
           "segments, radius_end (spiral), rise (height gained along the plane normal), plane: xy|xz|yz (3D only)}",
    "helix": "a helix around an axis: {center, radius, pitch (rise per turn), turns, segments_per_turn, axis: x|y|z, start (degrees), radius_end}",
    "line": "evenly spaced points from `from` to `to`: {from, to, segments}",
}
ARC_KEYS = {"center", "radius", "from", "to", "segments", "radius_end", "rise", "plane"}
HELIX_KEYS = {"center", "radius", "pitch", "turns", "segments_per_turn", "axis", "start", "radius_end"}
LINE_KEYS = {"from", "to", "segments"}


def _arc(g: dict, n: int, S, env, where, ctx) -> list | None:
    S.check_keys(g, ARC_KEYS, where, ctx)
    center = S.vec(g.get("center", [0] * n), n, env, f"{where}.center", ctx)
    r0 = S.num(g.get("radius"), env, f"{where}.radius", ctx)
    a0 = S.num(g.get("from", 0), env, f"{where}.from", ctx)
    a1 = S.num(g.get("to", 360), env, f"{where}.to", ctx)
    if center is None or r0 is None or a0 is None or a1 is None:
        return None
    r1 = S.num(g.get("radius_end", r0), env, f"{where}.radius_end", ctx, r0)
    rise = S.num(g.get("rise", 0), env, f"{where}.rise", ctx, 0.0)
    seg = int(S.num(g.get("segments", max(2, math.ceil(abs(a1 - a0) / 15))), env, f"{where}.segments", ctx, 8))
    plane = g.get("plane", "xy")
    if n == 3 and plane not in PLANES:
        ctx.error("SRC_SCHEMA", f"{where}.plane", "plane must be xy, xz or yz", suggest(str(plane), PLANES).strip())
        return None
    if n == 2 and rise:
        ctx.error("SRC_SCHEMA", f"{where}.rise", "rise needs 3D points (tube paths)")
        return None
    if seg < 1 or seg + 1 > LIMITS.max_points:
        ctx.error("SRC_LIMIT", f"{where}.segments", f"{seg} segments: must be 1..{LIMITS.max_points - 1} points per list")
        return None
    u, v, w = PLANES[plane] if n == 3 else (0, 1, None)
    out = []
    for k in range(seg + 1):
        t = k / seg
        ang = math.radians(a0 + (a1 - a0) * t)
        r = r0 + (r1 - r0) * t
        p = list(center)
        p[u] += r * math.cos(ang)
        p[v] += r * math.sin(ang)
        if w is not None:
            p[w] += rise * t
        out.append(p)
    return out


def _helix(g: dict, n: int, S, env, where, ctx) -> list | None:
    S.check_keys(g, HELIX_KEYS, where, ctx)
    if n != 3:
        ctx.error("SRC_SCHEMA", where, "helix produces 3D points; use it in tube paths")
        return None
    axis = g.get("axis", "y")
    if axis not in ("x", "y", "z"):
        ctx.error("SRC_SCHEMA", f"{where}.axis", "axis must be x, y or z")
        return None
    turns = S.num(g.get("turns", 1), env, f"{where}.turns", ctx)
    pitch = S.num(g.get("pitch"), env, f"{where}.pitch", ctx)
    r = S.num(g.get("radius"), env, f"{where}.radius", ctx)
    if turns is None or pitch is None or r is None:
        return None
    spt = int(S.num(g.get("segments_per_turn", 12), env, f"{where}.segments_per_turn", ctx, 12))
    if turns <= 0 or spt < 3 or spt * turns + 1 > LIMITS.max_points:
        ctx.error("SRC_LIMIT", where, f"helix of {turns:g} turns x {spt} segments: needs turns > 0, segments_per_turn >= 3 and "
                  f"at most {LIMITS.max_points} points")
        return None
    start = S.num(g.get("start", 0), env, f"{where}.start", ctx, 0.0)
    plane = {"y": "zx", "z": "xy", "x": "yz"}[axis]  # right-handed around the axis
    return _arc({"center": g.get("center", [0, 0, 0]), "radius": r, "radius_end": g.get("radius_end", r), "from": start,
                 "to": start + 360 * turns, "segments": max(2, int(math.ceil(spt * turns))), "rise": pitch * turns, "plane": plane},
                3, S, env, where, ctx)


def _line(g: dict, n: int, S, env, where, ctx) -> list | None:
    S.check_keys(g, LINE_KEYS, where, ctx)
    a = S.vec(g.get("from"), n, env, f"{where}.from", ctx)
    b = S.vec(g.get("to"), n, env, f"{where}.to", ctx)
    seg = int(S.num(g.get("segments", 1), env, f"{where}.segments", ctx, 1))
    if a is None or b is None:
        return None
    if seg < 1 or seg + 1 > LIMITS.max_points:
        ctx.error("SRC_LIMIT", f"{where}.segments", f"{seg} segments: must be 1..{LIMITS.max_points - 1}")
        return None
    return [[a[i] + (b[i] - a[i]) * k / max(seg, 1) for i in range(n)] for k in range(seg + 1)]


_FNS = {"arc": _arc, "helix": _helix, "line": _line}


def expand_points(value: Any, n: int, env: dict, where: str, ctx) -> list | None:
    """Evaluate a list of points in which items may be generators; returns evaluated points."""
    from . import source as S

    if not isinstance(value, list):
        ctx.error("SRC_SCHEMA", where, f"expected a list of points or generators ({', '.join(GENERATORS)})")
        return None
    out: list = []
    for i, item in enumerate(value):
        w = f"{where}[{i}]"
        if isinstance(item, dict):
            if len(item) != 1 or next(iter(item)) not in _FNS:
                key = next(iter(item), "")
                ctx.error("SRC_SCHEMA", w, f"a point generator is a one-key mapping: {', '.join(_FNS)}",
                          suggest(str(key), _FNS).strip() or "e.g. {arc: {center: [0, 0], radius: 0.5, from: 0, to: 180}}")
                return None
            kind, g = next(iter(item.items()))
            if not isinstance(g, dict):
                ctx.error("SRC_SCHEMA", f"{w}.{kind}", f"{kind} needs a mapping: {GENERATORS[kind]}")
                return None
            pts = _FNS[kind](g, n, S, env, f"{w}.{kind}", ctx)
            if pts is None:
                return None
            if out and pts and max(abs(a - b) for a, b in zip(out[-1], pts[0])) < 1e-9:
                pts = pts[1:]  # a generator starting where the previous point ended does not repeat it
            out.extend(pts)
        else:
            p = S.vec(item, n, env, w, ctx)
            if p is None:
                return None
            out.append(p)
        if len(out) > LIMITS.max_points:
            ctx.error("SRC_LIMIT", where, f"more than {LIMITS.max_points} points")
            return None
    return out
