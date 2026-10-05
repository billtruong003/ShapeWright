"""Organic shapes (Phase 22): `blend`, SDF primitives blended into one closed mesh (kernel: shapewright/organic.py)."""

from __future__ import annotations

import numpy as np

from .. import organic
from ..registry import Param, shape, suggest
from ..source import num, vec

ITEM_PARAMS = {  # sdf kind -> {param: kind}
    "sphere": {"center": "vec3", "radius": "num"},
    "ellipsoid": {"center": "vec3", "radii": "vec3"},
    "capsule": {"a": "vec3", "b": "vec3", "radius": "num"},
    "cone": {"a": "vec3", "b": "vec3", "radius_a": "num", "radius_b": "num"},
    "box": {"center": "vec3", "size": "vec3", "round": "num?"},
    "torus": {"center": "vec3", "radius": "num", "thickness": "num"},
}
COMMON = {"sdf", "op", "blend", "mirror", "shell", "rotate", "material", "doc"}


def parse_items(raw_items, env, ctx, where: str, materials: dict) -> list[organic.Item]:
    """Validate and evaluate the items of a blend (expressions allowed in every number)."""
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("items: expected a non-empty list of {sdf: KIND, ...}")
    items = []
    for i, r in enumerate(raw_items):
        w = f"{where}.items[{i}]"
        if not isinstance(r, dict) or "sdf" not in r:
            raise ValueError(f"items[{i}]: expected {{sdf: {' | '.join(organic.SDF_KINDS)}, ...}}")
        kind = r["sdf"]
        if kind not in ITEM_PARAMS:
            raise ValueError(f"items[{i}].sdf: unknown '{kind}'.{suggest(kind, ITEM_PARAMS)} Kinds: {', '.join(organic.SDF_KINDS)}")
        spec = ITEM_PARAMS[kind]
        unknown = set(r) - set(spec) - COMMON
        if unknown:
            k = sorted(unknown)[0]
            raise ValueError(f"items[{i}]: '{kind}' has no '{k}'.{suggest(k, set(spec) | COMMON)} Keys: {', '.join(sorted(spec))}")
        args = {}
        for key, kk in spec.items():
            if key not in r:
                if kk.endswith("?"):
                    continue
                if key == "center":
                    args[key] = [0.0, 0.0, 0.0]
                    continue
                raise ValueError(f"items[{i}]: '{kind}' needs '{key}'")
            v = vec(r[key], 3, env, f"{w}.{key}", ctx) if kk == "vec3" else num(r[key], env, f"{w}.{key}", ctx)
            if v is None:
                raise ValueError(f"items[{i}].{key}: invalid value (see the source error)")
            if kk.startswith("num") and v < 0:
                raise ValueError(f"items[{i}].{key}: must be >= 0")
            args[key] = v
        if kind in ("capsule", "cone"):
            args["center"] = [(x + y) / 2 for x, y in zip(args["a"], args["b"])]
        op = r.get("op", "union")
        if op not in organic.OPS:
            raise ValueError(f"items[{i}].op: must be {' | '.join(organic.OPS)}")
        mirror = r.get("mirror")
        if mirror is True:
            mirror = "x"
        if mirror not in (None, False, "x", "y", "z"):
            raise ValueError(f"items[{i}].mirror: x | y | z (true = x)")
        blend = num(r["blend"], env, f"{w}.blend", ctx) if "blend" in r else None
        shell = num(r.get("shell", 0.0), env, f"{w}.shell", ctx)
        rot = vec(r["rotate"], 3, env, f"{w}.rotate", ctx) if "rotate" in r else None
        mat = r.get("material")
        if mat is not None and materials and mat not in materials:
            raise ValueError(f"items[{i}].material: unknown material '{mat}'.{suggest(mat, materials)}")
        items.append(organic.Item(kind, args, op, blend, mirror or None, shell or 0.0, rot, mat, w))
    if not any(it.op == "union" for it in items) or items[0].op != "union":
        raise ValueError("the first item must be a union item (subtract/intersect act on what comes before them)")
    return items


@shape("blend", "Organic form: SDF primitives (sphere, ellipsoid, capsule, cone, box, torus) blended into ONE closed "
       "mesh, in order: union items melt together with a rounded seam of `radius`; `op: subtract` carves (a hood "
       "opening, a mouth), `op: intersect` trims. Per item: `mirror: x` (a pair), `shell: t` (hollow), `rotate`, "
       "`material` (faces nearest that item). Meshed on a grid of `voxel` size, then decimated to `triangles`. "
       "Coordinates are in the part's frame; use origin: keep to place it by them. For characters, creatures, "
       "slimes, mushrooms, rocks with soft forms.",
       [Param("items", "sdf_list", doc="ordered list of {sdf: KIND, ...}: sphere {center, radius} | ellipsoid {center, radii} | "
              "capsule {a, b, radius} | cone {a, b, radius_a, radius_b} (rounded ends) | box {center, size, round} | "
              "torus {center, radius, thickness} (around Y); plus op (union | subtract | intersect), blend (this item's "
              "radius), mirror (x | y | z), shell (hollow, thickness), rotate [x, y, z] degrees, material, doc"),
        Param("radius", "num", 0.03, "smooth-union radius in metres (0 = hard union); an item's `blend` overrides it", min=0),
        Param("voxel", "num", 0.0, "grid step in metres (0 = automatic: the size / 120, at least 4 mm); smaller = finer, slower", min=0),
        Param("triangles", "int", 4000, "triangle budget after decimation", min=100, max=100_000),
        Param("smooth", "int", 0, "Taubin smoothing passes before decimation (0..10)", min=0, max=10),
        Param("ground", "bool", False, "cut the form flat at y = 0 (a creature standing on the floor; smooth unions "
              "otherwise bulge a little below their items)")],
       category="organic", topology="generate",
       example="{type: blend, radius: 0.03, triangles: 3000, items: [{sdf: ellipsoid, center: [0, 0.3, 0], radii: [0.2, 0.25, 0.18]}, "
               "{sdf: sphere, center: [0, 0.62, 0.02], radius: 0.17}, {sdf: cone, a: [0.1, 0.75, 0], b: [0.14, 0.9, 0], radius_a: 0.05, "
               "radius_b: 0.01, mirror: x}]}")
def blend(a, b):
    items = parse_items(a["items"], b.env, b.ctx, b.where, b.materials)
    voxel = a["voxel"]
    if not voxel:
        bb = np.stack([it.bounds() for it in items if it.op == "union"])
        voxel = max(0.004, float(np.linalg.norm(bb[:, 1].max(0) - bb[:, 0].min(0))) / 120)
    m, stats = organic.mesh_blend(items, a["radius"], voxel, a["triangles"], a["smooth"], a["ground"])
    if stats["defects"]:
        at = "; ".join(f"({x:g}, {y:g}, {z:g})" for x, y, z in stats["pinch_at"][:4])
        b.warn("GEO_BLEND_PINCHED", f"{stats['triangles']} triangles (edges about {stats['edge_m'] * 1000:.0f} mm) cannot hold a gap "
               f"narrower than that: the surface was pinched near {at}",
               "widen the gap (a socket, the space under a cap), fill it (a larger `blend`), or raise `triangles`")
    return m
