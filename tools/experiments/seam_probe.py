"""Seam probe for modular assemblies (MODULAR_HOUSE_PACK_01): coplanar overlapping faces BETWEEN parts.

Usage: python tools/experiments/seam_probe.py ASSET [--tol 0.0005] [--min-area 1e-5] [--json]

This is an experiment instrument, not a validator. It finds pairs of triangles from different parts that
lie in the same plane (normals within 1 degree, plane offset within `tol`) and overlap in area:
  same-facing   -> both surfaces render in the same place: z-fighting (a real seam defect) ...
                   ... unless the shared region is buried inside a third part (e.g. two faces that both end
                   inside a plate): a point just in front of the region is tested against every other closed
                   part with a generalised winding number, and buried overlaps are reported as `hidden`
  back-to-back  -> the faces touch face to face (usually a hidden contact, e.g. a wall butting a post)
Overlap area is measured exactly by clipping the two triangles in their common plane.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _clip(poly, a, b):
    """Sutherland-Hodgman: keep the part of `poly` left of the directed edge a->b (2D)."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        sp = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        sq = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _area(poly):
    if len(poly) < 3:
        return 0.0
    x = np.array([p[0] for p in poly])
    y = np.array([p[1] for p in poly])
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _ccw(t):
    (x1, y1), (x2, y2), (x3, y3) = t
    return t if (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) > 0 else [t[0], t[2], t[1]]


def _clip_poly(t1, t2):
    poly = _ccw(t1)
    t2 = _ccw(t2)
    for i in range(3):
        poly = _clip(poly, t2[i], t2[(i + 1) % 3])
        if not poly:
            return []
    return poly


def winding(points, V, F):
    """Generalised winding number of each point w.r.t. a closed triangle mesh (~1 inside, ~0 outside)."""
    a, b, c = V[F[:, 0]][None] - points[:, None], V[F[:, 1]][None] - points[:, None], V[F[:, 2]][None] - points[:, None]
    la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
    det = np.einsum("pij,pij->pi", a, np.cross(b, c))
    den = la * lb * lc + np.einsum("pij,pij->pi", a, b) * lc + np.einsum("pij,pij->pi", b, c) * la + np.einsum("pij,pij->pi", c, a) * lb
    return np.arctan2(det, den).sum(1) / (2 * np.pi)


def overlap_area(t1, t2):
    poly = _ccw(t1)
    t2 = _ccw(t2)
    for i in range(3):
        poly = _clip(poly, t2[i], t2[(i + 1) % 3])
        if not poly:
            return 0.0
    return _area(poly)


def probe(asset, tol=5e-4, min_area=1e-5):
    tris = []  # (part, v0, v1, v2, n, d)
    for p in asset.parts:
        V, F = p.mesh.V, p.mesh.F
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n, axis=1)
        ok = ln > 1e-12
        n = n[ok] / ln[ok, None]
        for k, (ta, tb, tc, nn) in enumerate(zip(a[ok], b[ok], c[ok], n)):
            tris.append((p.name, ta, tb, tc, nn, float(nn @ ta)))
    # bucket by quantised (|normal|, plane distance along that normal)
    buckets = defaultdict(list)
    for i, (_, ta, _, _, nn, d) in enumerate(tris):
        s = 1 if (nn[np.argmax(np.abs(nn))] > 0) else -1
        key = tuple(np.round(nn * s, 2)) + (round(d * s / (tol * 4)),)
        buckets[key].append(i)
    found = defaultdict(lambda: {"same": 0.0, "opposite": 0.0})
    for idx in buckets.values():
        if len(idx) < 2:
            continue
        parts = {tris[i][0] for i in idx}
        if len(parts) < 2:
            continue
        for x in range(len(idx)):
            i = idx[x]
            pi, ai, bi, ci, ni, di = tris[i]
            ax = np.argmax(np.abs(ni))
            keep = [k for k in range(3) if k != ax]
            for y in range(x + 1, len(idx)):
                j = idx[y]
                pj, aj, bj, cj, nj, dj = tris[j]
                if pj == pi:
                    continue
                dot = float(ni @ nj)
                if abs(dot) < 0.9998 or abs(dj - di * np.sign(dot)) > tol:
                    continue
                poly = _clip_poly([tuple(v[keep]) for v in (ai, bi, ci)], [tuple(v[keep]) for v in (aj, bj, cj)])
                area = _area(poly) / max(abs(ni[ax]), 1e-9)
                if area >= min_area:
                    # the planes must actually meet where the triangles overlap: offsets measured from the world
                    # origin agree spuriously for near-parallel planes (a 0.003 tilt over 1.4 m)
                    cx = np.mean([p[0] for p in poly]), np.mean([p[1] for p in poly])
                    q = np.zeros(3)
                    q[keep[0]], q[keep[1]] = cx
                    q[ax] = (di - ni[keep[0]] * cx[0] - ni[keep[1]] * cx[1]) / ni[ax]
                    if abs(float(nj @ q) - dj) > tol:
                        continue
                    key = tuple(sorted((pi, pj)))
                    found[key]["same" if dot > 0 else "opposite"] += area
                    if dot > 0:
                        cx = np.mean([p[0] for p in poly]), np.mean([p[1] for p in poly])
                        pt = np.zeros(3)
                        pt[keep[0]], pt[keep[1]] = cx
                        pt[ax] = (di - ni[keep[0]] * cx[0] - ni[keep[1]] * cx[1]) / ni[ax]
                        found[key].setdefault("samples", []).append((pt + ni * 0.002, area))
    closed = {p.name: p.mesh for p in asset.parts}
    rows = []
    for k, v in found.items():
        hidden = 0.0
        for pt, ar in v.get("samples", []):
            others = [m for n, m in closed.items() if n not in k]
            lo = np.array([m.bounds()[0] for m in others])
            hi = np.array([m.bounds()[1] for m in others])
            near = [m for m, bl, bh in zip(others, lo, hi) if np.all(pt >= bl - 1e-6) and np.all(pt <= bh + 1e-6)]
            if any(winding(pt[None], m.V, m.F)[0] > 0.5 for m in near):
                hidden += ar
        rows.append({"parts": list(k), "same_facing_m2": round(v["same"] - hidden, 6), "same_facing_hidden_m2": round(hidden, 6),
                     "back_to_back_m2": round(v["opposite"], 6)})
    rows.sort(key=lambda r: -(r["same_facing_m2"] * 1000 + r["back_to_back_m2"]))
    return rows


def main(argv):
    # Phase 20: the same algorithm now runs as the `seams` validator (shapewright/validate/seams.py);
    # this probe stays as the experiment instrument with its own tolerance switch and full pair listing.
    from shapewright.assemble import build, resolve_asset_path

    tol, min_area = 5e-4, 1e-5
    if "--tol" in argv:
        tol = float(argv[argv.index("--tol") + 1])
    if "--min-area" in argv:
        min_area = float(argv[argv.index("--min-area") + 1])
    a = build(resolve_asset_path(argv[0]))
    rows = probe(a, tol, min_area)
    if "--json" in argv:
        print(json.dumps(rows, indent=1))
        return 0
    same = [r for r in rows if r["same_facing_m2"] > 0]
    buried = [r for r in rows if r["same_facing_hidden_m2"] > 0 and r["same_facing_m2"] <= 0]
    print(f"{argv[0]}: {len(same)} part pairs with VISIBLE same-facing coplanar overlap (z-fighting), "
          f"{len(buried)} pairs whose same-facing overlap is buried inside another part, "
          f"{len(rows) - len(same) - len(buried)} pairs only back-to-back (hidden contact)")
    for r in same[:40]:
        print(f"  Z-FIGHT {r['same_facing_m2'] * 1e4:9.2f} cm2  {r['parts'][0]}  <->  {r['parts'][1]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:  # piped into head
        sys.exit(0)
