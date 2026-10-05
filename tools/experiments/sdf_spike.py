"""G0 spike (track G): a chibi fox in a hoodie as SDF primitives, smooth union, meshed natively.

    python tools/experiments/sdf_spike.py OUT_DIR [--voxel 0.008] [--budget 6000]

No Blender, no scikit-image: the field is sampled on a grid and meshed by marching tetrahedra (each cube split into
6 tetrahedra around its main diagonal, the Kuhn split, so neighbouring cubes agree and the surface is watertight
without case tables). Then quadric decimation to a triangle budget (fast-simplification, as `decimate`) and xatlas
UVs (as `uv: atlas`). Faces get the region of the nearest primitive (hoodie, fur, white, black) and are written as
one OBJ per region plus an asset.yaml, so the normal `sw render` / `sw validate` review the result.

It measures what G0 asks: time to mesh, watertight, triangle count, number of params the model needed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shapewright import backend  # noqa: E402
from shapewright.mesh import Mesh  # noqa: E402

# ---------------------------------------------------------------- primitives (signed distance, metres, y up)


def ellipsoid(c, r):
    c, r = np.asarray(c, float), np.asarray(r, float)

    def f(P):
        q = (P - c) / r
        k0 = np.linalg.norm(q, axis=-1)
        k1 = np.linalg.norm(q / r, axis=-1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
    return f


def cone(a, b, ra, rb):
    """Capsule with a radius that changes from ra at a to rb at b (rounded cone; ra == rb is a capsule)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = b - a
    L2 = float(ab @ ab)

    def f(P):
        t = np.clip(((P - a) @ ab) / L2, 0.0, 1.0)
        return np.linalg.norm(P - (a + t[..., None] * ab), axis=-1) - (ra + (rb - ra) * t)
    return f


def mirror_x(f):
    def g(P):
        Q = P.copy()
        Q[..., 0] = np.abs(Q[..., 0])
        return f(Q)
    return g


def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smooth_subtract(f, g, k):
    """f minus g with a rounded rim (smooth max of f and -g)."""
    def h(P):
        return -smin(-f(P), g(P), k)
    return h


# ---------------------------------------------------------------- the fox: 11 primitives, 4 regions

PARAMS = {  # everything the model needed; mirrored primitives are written once (x >= 0)
    "body":    ("hoodie", "ellipsoid", [0, 0.36, 0], [0.165, 0.2, 0.145]),
    "hood":    ("hoodie", "ellipsoid", [0, 0.745, -0.035], [0.215, 0.2, 0.19]),
    "arm":     ("hoodie", "cone", [0.14, 0.47, 0.0], [0.22, 0.3, 0.05], 0.052, 0.045),
    "head":    ("fur", "ellipsoid", [0, 0.72, 0.02], [0.195, 0.17, 0.17]),
    "ear":     ("fur", "cone", [0.1, 0.86, -0.01], [0.15, 1.0, -0.03], 0.06, 0.012),
    "leg":     ("fur", "cone", [0.075, 0.2, 0.0], [0.085, 0.035, 0.03], 0.062, 0.055),
    "tail":    ("fur", "cone", [0, 0.24, -0.12], [0, 0.42, -0.33], 0.055, 0.1),
    "muzzle":  ("white", "ellipsoid", [0, 0.665, 0.15], [0.085, 0.06, 0.075]),
    "cheek":   ("white", "ellipsoid", [0.115, 0.655, 0.1], [0.07, 0.06, 0.06]),
    "tail_tip": ("white", "ellipsoid", [0, 0.46, -0.37], [0.075, 0.08, 0.075]),
    "nose":    ("black", "ellipsoid", [0, 0.685, 0.225], [0.026, 0.02, 0.02]),
}
MIRRORED = {"arm", "ear", "leg", "cheek"}
HOOD_OPENING = ([0, 0.7, 0.16], [0.16, 0.15, 0.16])  # carved out of the hood (smooth subtraction) to show the face
BLEND = 0.035  # smooth-union radius (metres)
COLORS = {"hoodie": "#4d7a5c", "fur": "#d9772e", "white": "#f2ece1", "black": "#2a2420"}


def primitives():
    out = []
    for name, (region, kind, *args) in PARAMS.items():
        f = ellipsoid(*args) if kind == "ellipsoid" else cone(*args)
        if name == "hood":
            f = smooth_subtract(f, ellipsoid(*HOOD_OPENING), 0.03)
        out.append((name, region, mirror_x(f) if name in MIRRORED else f))
    return out


def field(P, prims):
    d = None
    for _, _, f in prims:
        v = f(P)
        d = v if d is None else smin(d, v, BLEND)
    return d


# ---------------------------------------------------------------- marching tetrahedra

CORNERS = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
TETS = np.array([[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]])


def marching_tets(F: np.ndarray, lo: np.ndarray, h: float, fn) -> Mesh:
    """Zero level set of the grid F (nx, ny, nz; negative inside, sampled from `fn`) as a closed triangle mesh."""
    nx, ny, nz = F.shape
    flat = F.reshape(-1)
    gid = np.arange(F.size).reshape(F.shape)
    base = gid[:-1, :-1, :-1].reshape(-1)
    stride = np.array([ny * nz, nz, 1])
    corner_off = CORNERS @ stride
    vals = flat[base[:, None] + corner_off[None, :]]
    mixed = (vals < 0).any(1) & (vals >= 0).any(1)  # only cells the surface passes through
    base = base[mixed]
    tris = []
    for tet in TETS:
        ids = base[:, None] + corner_off[tet][None, :]  # (c,4) grid ids
        v = flat[ids]
        inside = v < 0
        n_in = inside.sum(1)
        for count in (1, 2, 3):
            sel = n_in == count
            if not sel.any():
                continue
            order = np.argsort(~inside[sel], axis=1, kind="stable")  # inside corners first
            ids_s = np.take_along_axis(ids[sel], order, 1)
            if count == 1:      # one inside: triangle on its 3 edges
                edges = [[(0, 1), (0, 2), (0, 3)]]
            elif count == 3:    # one outside (corner 3): triangle on its 3 edges
                edges = [[(0, 3), (1, 3), (2, 3)]]
            else:               # two inside (0,1): quad on 4 edges, split in two
                edges = [[(0, 2), (0, 3), (1, 3)], [(0, 2), (1, 3), (1, 2)]]
            for tri in edges:
                tris.append(np.stack([np.stack([ids_s[:, a], ids_s[:, b]], 1) for a, b in tri], 1))  # (k,3,2) edge ends
    E = np.concatenate(tris)  # (m,3,2)
    E.sort(axis=2)
    keys = E[..., 0] * F.size + E[..., 1]
    uniq, inv = np.unique(keys.reshape(-1), return_inverse=True)
    a, b = uniq // F.size, uniq % F.size
    fa, fb = flat[a], flat[b]
    t = fa / (fa - fb)
    pa = lo + np.stack(np.unravel_index(a, F.shape), 1) * h
    pb = lo + np.stack(np.unravel_index(b, F.shape), 1) * h
    V = pa + (pb - pa) * t[:, None]
    T = inv.reshape(-1, 3)
    # orient outward: along the field's gradient at the triangle centre (central differences of the grid's
    # trilinear field would do; the exact field is cheaper to get right). The inside-corner test misoriented 0.5 %.
    P = V[T]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    C = P.mean(1)
    e = h * 0.25
    g = np.stack([fn(C + e * np.eye(3)[k]) - fn(C - e * np.eye(3)[k]) for k in range(3)], 1)
    flip = np.einsum("ij,ij->i", n, g) < 0
    T[flip] = T[flip][:, ::-1]
    area = np.linalg.norm(n, axis=1)
    T = T[area > 1e-14]  # an edge crossing exactly at a corner gives zero-area triangles
    used, T = np.unique(T, return_inverse=True)
    return Mesh(V[used], T.reshape(-1, 3))


# ---------------------------------------------------------------- run


def main(out: Path, voxel: float = 0.008, budget: int = 6000) -> dict:
    import trimesh

    out.mkdir(parents=True, exist_ok=True)
    prims = primitives()
    t0 = time.perf_counter()
    lo = np.array([-0.36, -0.03, -0.52])
    hi = np.array([0.36, 1.08, 0.32])
    axes = [np.arange(lo[k], hi[k] + voxel, voxel) for k in range(3)]
    G = np.stack(np.meshgrid(*axes, indexing="ij"), -1)
    F = field(G.reshape(-1, 3), prims).reshape(G.shape[:3])
    t1 = time.perf_counter()
    raw = marching_tets(F, lo, voxel, lambda P: field(P, prims))
    t2 = time.perf_counter()
    ratio = min(1.0, budget / max(raw.n_tris, 1))
    m = backend.simplify(raw, ratio) if ratio < 1 else raw
    m = backend.collapse_needles(m)  # decimation leaves a few zero-area slivers
    m.V = m.V - np.array([0.0, m.V[:, 1].min(), 0.0])  # feet on y = 0
    t3 = time.perf_counter()
    tm = trimesh.Trimesh(m.V, m.F, process=False)
    uv = backend.unwrap_charts(m, 1024, 4)
    t4 = time.perf_counter()
    # regions: nearest primitive at each face centre
    C = m.V[m.F].mean(1)
    D = np.stack([f(C) for _, _, f in prims], 1)
    region = np.array([prims[i][1] for i in D.argmin(1)])
    parts = {}
    for r in COLORS:
        sel = np.flatnonzero(region == r)
        if not len(sel):
            continue
        sub = trimesh.Trimesh(m.V, m.F[sel], process=False)
        sub.remove_unreferenced_vertices()
        sub.export(out / f"fox_{r}.obj")
        parts[r] = int(len(sel))
    mats = "\n".join(f"  {r}: {{base_color: '{c}', roughness: 0.8}}" for r, c in COLORS.items() if r in parts)
    prts = "\n".join(f"  {r}: {{shape: {{type: mesh_file, path: fox_{r}.obj}}, material: {r}, origin: keep, tags: [open_ok], shading: smooth}}"
                     for r in parts)
    (out / "asset.yaml").write_text(f"shapewright: 0.1\nasset: {{name: fox_spike, placement: floor}}\n"
                                    f"budget: {{triangles: {budget + 500}}}\nmaterials:\n{mats}\nparts:\n{prts}\n")
    n_params = sum(len(np.ravel(np.concatenate([np.ravel(np.asarray(a, float)) for a in v[2:]]))) for v in PARAMS.values()) + 1
    res = {
        "grid": list(F.shape), "voxel_m": voxel, "primitives": len(PARAMS), "primitives_mirrored": len(MIRRORED),
        "numbers_in_model": n_params + 6, "raw_triangles": raw.n_tris, "triangles": m.n_tris,
        "watertight": bool(tm.is_watertight), "winding_consistent": bool(tm.is_winding_consistent),
        "volume_m3": round(float(tm.volume), 5), "uv_charts_ok": uv is not None,
        "region_faces": parts, "height_m": round(float(m.V[:, 1].max() - m.V[:, 1].min()), 3),
        "seconds": {"field": round(t1 - t0, 2), "mesh": round(t2 - t1, 2), "decimate": round(t3 - t2, 2),
                    "uv": round(t4 - t3, 2), "total": round(t4 - t0, 2)},
    }
    (out / "spike.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    args = sys.argv[1:]
    voxel = float(args[args.index("--voxel") + 1]) if "--voxel" in args else 0.008
    budget = int(args[args.index("--budget") + 1]) if "--budget" in args else 6000
    print(json.dumps(main(Path(args[0]), voxel, budget), indent=1))
