"""Seams between parts: coplanar overlapping faces (z-fighting) that every other layer passes.

Promoted from `tools/experiments/seam_probe.py` (MODULAR_HOUSE_PACK_01 found 26 such pairs in the first
cottage, all PASS in the other layers). For every pair of triangles from different parts that lie in the
same plane (normals within ~1 degree, plane offsets within `TOL_PLANE`), the overlap is clipped exactly in
that plane. Same-facing overlap renders twice in the same place: z-fighting. It is reported only where it is
visible: a point just in front of the overlap that lies inside a third closed part (generalised winding
number) is buried, e.g. two plank ends that both stop inside a beam; so is a downward face lying on the ground
plane (y = 0), which the floor covers. Back-to-back overlap is ordinary hidden
contact (a wall butting a post) and is not reported.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from ..report import Issue

TOL_PLANE = 1e-3  # plane offset tolerance (m): closer than this, depth buffers cannot separate the faces
MIN_TRI_AREA = 1e-6  # m^2 of overlap per triangle pair worth measuring
MIN_PAIR_AREA = 5e-5  # m^2 (0.5 cm^2) of visible overlap per part pair worth reporting
MAX_TRIS = 400_000


def _clip(poly, a, b):
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


def _ccw(t):
    (x1, y1), (x2, y2), (x3, y3) = t
    return t if (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) > 0 else [t[0], t[2], t[1]]


def _overlap(t1, t2):
    poly = _ccw(t1)
    t2 = _ccw(t2)
    for i in range(3):
        poly = _clip(poly, t2[i], t2[(i + 1) % 3])
        if not poly:
            return []
    return poly


def _area(poly) -> float:
    if len(poly) < 3:
        return 0.0
    x = np.array([p[0] for p in poly])
    y = np.array([p[1] for p in poly])
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def winding(points: np.ndarray, V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Generalised winding number of each point w.r.t. a closed triangle mesh (~1 inside, ~0 outside)."""
    a, b, c = V[F[:, 0]][None] - points[:, None], V[F[:, 1]][None] - points[:, None], V[F[:, 2]][None] - points[:, None]
    la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
    det = np.einsum("pij,pij->pi", a, np.cross(b, c))
    den = la * lb * lc + np.einsum("pij,pij->pi", a, b) * lc + np.einsum("pij,pij->pi", b, c) * la + np.einsum("pij,pij->pi", c, a) * lb
    return np.arctan2(det, den).sum(1) / (2 * np.pi)


def coplanar_pairs(parts, tol: float = TOL_PLANE, min_area: float = MIN_TRI_AREA) -> list[dict]:
    """Per part pair: visible same-facing overlap, buried same-facing overlap and back-to-back contact (m^2)."""
    owner, A, Bv, C, N, D = [], [], [], [], [], []
    for k, p in enumerate(parts):
        V, F = p.mesh.V, p.mesh.F
        if len(F) == 0:
            continue
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n, axis=1)
        ok = ln > 1e-12
        n = n[ok] / ln[ok, None]
        owner.append(np.full(int(ok.sum()), k))
        A.append(a[ok])
        Bv.append(b[ok])
        C.append(c[ok])
        N.append(n)
        D.append(np.einsum("ij,ij->i", n, a[ok]))
    if not owner:
        return []
    owner, A, Bv, C, N, D = (np.concatenate(x) for x in (owner, A, Bv, C, N, D))
    # canonical orientation (largest component positive) so opposite normals share a bucket
    ax = np.argmax(np.abs(N), axis=1)
    sgn = np.where(N[np.arange(len(N)), ax] > 0, 1.0, -1.0)
    Nc, Dc = N * sgn[:, None], D * sgn
    keys = np.concatenate([np.round(Nc * 100).astype(np.int64), np.round(Dc / (tol * 4)).astype(np.int64)[:, None]], axis=1)
    order = np.lexsort(keys.T[::-1])
    ks = keys[order]
    breaks = np.flatnonzero(np.any(ks[1:] != ks[:-1], axis=1)) + 1
    found = defaultdict(lambda: {"same": 0.0, "opposite": 0.0, "samples": [], "at": None})
    for grp in np.split(order, breaks):
        if len(grp) < 2 or len(np.unique(owner[grp])) < 2:
            continue
        g = grp.tolist()
        lo = np.minimum(np.minimum(A[grp], Bv[grp]), C[grp])
        hi = np.maximum(np.maximum(A[grp], Bv[grp]), C[grp])
        for x in range(len(g)):
            i = g[x]
            ni, di, pi = N[i], D[i], owner[i]
            axi = int(np.argmax(np.abs(ni)))
            keep = [k for k in range(3) if k != axi]
            # candidates: other parts, overlapping bounding boxes
            rest = np.arange(x + 1, len(g))
            if not len(rest):
                continue
            cand = rest[(owner[grp[rest]] != pi) & np.all(lo[rest] <= hi[x] + tol, axis=1) & np.all(hi[rest] >= lo[x] - tol, axis=1)]
            ti = [tuple(v[keep]) for v in (A[i], Bv[i], C[i])]
            for y in cand.tolist():
                j = g[y]
                dot = float(ni @ N[j])
                if abs(dot) < 0.9998 or abs(D[j] - di * np.sign(dot)) > tol:
                    continue
                poly = _overlap(ti, [tuple(v[keep]) for v in (A[j], Bv[j], C[j])])
                area = _area(poly) / max(abs(float(ni[axi])), 1e-9)
                if area < min_area:
                    continue
                cx = np.mean([p[0] for p in poly]), np.mean([p[1] for p in poly])
                q = np.zeros(3)
                q[keep[0]], q[keep[1]] = cx
                q[axi] = (di - ni[keep[0]] * cx[0] - ni[keep[1]] * cx[1]) / ni[axi]
                if abs(float(N[j] @ q) - D[j]) > tol:  # the planes must meet where the triangles overlap
                    continue
                key = tuple(sorted((int(pi), int(owner[j]))))
                found[key]["same" if dot > 0 else "opposite"] += area
                if dot > 0:
                    found[key]["samples"].append((q + ni * 0.002, area))
                    if found[key]["at"] is None:
                        found[key]["at"] = (q, ni)
    rows = []
    bounds = [p.mesh.bounds() for p in parts]
    for (a_, b_), v in found.items():
        hidden = 0.0
        for pt, ar in v["samples"]:
            if abs(pt[1] + 0.002) <= TOL_PLANE and pt[1] < 0:  # a face lying on the ground plane, facing down: the floor hides it
                hidden += ar
                continue
            for k, p in enumerate(parts):
                if k in (a_, b_) or not (np.all(pt >= bounds[k][0] - 1e-6) and np.all(pt <= bounds[k][1] + 1e-6)):
                    continue
                if winding(pt[None], p.mesh.V, p.mesh.F)[0] > 0.5:
                    hidden += ar
                    break
        row = {"parts": [parts[a_].name, parts[b_].name], "same_facing_m2": round(v["same"] - hidden, 6),
               "same_facing_hidden_m2": round(hidden, 6), "back_to_back_m2": round(v["opposite"], 6)}
        if v["at"] is not None:  # one point of the shared surface and its facing, to find it in a render
            row["at"] = [round(float(x), 4) for x in v["at"][0]]
            row["normal"] = [round(float(x), 3) + 0.0 for x in v["at"][1]]
        rows.append(row)
    rows.sort(key=lambda r: -(r["same_facing_m2"] * 1000 + r["back_to_back_m2"]))
    return rows


def _where(r) -> str:
    if not r.get("at"):
        return ""
    names = {(1, 0, 0): "+x", (-1, 0, 0): "-x", (0, 1, 0): "top", (0, -1, 0): "bottom", (0, 0, 1): "front", (0, 0, -1): "back"}
    facing = names.get(tuple(int(round(c)) for c in r["normal"]) if max(abs(c) for c in r["normal"]) > 0.999 else None, "slanted")
    return f" (near {tuple(r['at'])}, facing {facing})"


def seam_issues(asset, metrics: dict) -> list[Issue]:
    if asset.n_tris > MAX_TRIS:
        return [Issue("SEAM_SKIPPED", "info", f"{asset.n_tris} triangles: seam check skipped above {MAX_TRIS}", "", "assembly")]
    rows = coplanar_pairs(asset.parts)
    bad = [r for r in rows if r["same_facing_m2"] >= MIN_PAIR_AREA]
    metrics["seam_zfight_pairs"] = len(bad)
    out = []
    for r in bad[:12]:
        a, b = r["parts"]
        out.append(Issue("SEAM_COPLANAR_OVERLAP", "warning",
                         f"{a} and {b} share {r['same_facing_m2'] * 1e4:.2f} cm² of the same surface facing the same way"
                         f"{_where(r)}: it will z-fight",
                         a, "assembly",
                         "offset one face by a few mm (depth ranks), end one part inside the other (embed past the jitter), "
                         "or cut one; `sw render ASSET --part NAME` to find the spot", {"parts": [a, b], "area_m2": r["same_facing_m2"], "at": r.get("at"), "normal": r.get("normal")}))
    if len(bad) > 12:
        out.append(Issue("SEAM_COPLANAR_OVERLAP", "warning", f"... and {len(bad) - 12} more part pairs z-fight", "", "assembly"))
    return out


_REGISTERED = False


def register():
    """Called by validate.load_builtin after the core checks, so the validator order never depends on import order."""
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True
    from ..assemble import Asset
    from ..surface import Surface
    from . import validator

    @validator("seams", "assembly", "Coplanar overlapping faces between parts that face the same way and are visible (z-fighting).",
               ("SEAM_COPLANAR_OVERLAP", "SEAM_SKIPPED"))
    def seams(asset: Asset, surface: Surface, metrics: dict):
        return seam_issues(asset, metrics)

