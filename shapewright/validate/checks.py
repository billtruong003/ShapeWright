"""Built-in validators. Each returns issues and may record metrics.

Every issue carries a stable code (documented in docs/VALIDATION.md), the
semantic part or source path it concerns, and a hint naming what to change.
"""

from __future__ import annotations

import numpy as np

from .. import expr
from ..assemble import Asset
from .. import backend
from ..report import Issue
from ..render.raster import coverage
from ..surface import Surface
from . import validator

TOL = 1e-3  # 1 mm contact / grounding tolerance


def _issue(code, sev, layer, msg, where="", hint="", **data):
    return Issue(code, sev, msg, where, layer, hint, {k: v for k, v in data.items() if v is not None})


# ---------------------------------------------------------------- geometry


def _components(F: np.ndarray, n: int) -> int:
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in F:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    return len({find(v) for v in np.unique(F)})


@validator("mesh_integrity", "geometry", "Per-part closed-manifold checks: open/non-manifold edges, winding, inverted, degenerate, duplicate faces, fragments.",
           ("GEO_NONFINITE", "GEO_DEGENERATE_FACES", "GEO_DUPLICATE_FACES", "GEO_OPEN_EDGES", "GEO_NONMANIFOLD_EDGES",
            "GEO_WINDING_INCONSISTENT", "GEO_INVERTED", "GEO_PART_FRAGMENTED", "GEO_SLIVER_TRIS"))
def mesh_integrity(asset: Asset, surface: Surface, metrics: dict):
    out = []
    slivers_total = 0
    for p in asset.parts:
        m, w = p.mesh, p.name
        if not np.all(np.isfinite(m.V)):
            out.append(_issue("GEO_NONFINITE", "error", "geometry", "non-finite vertex positions", w))
            continue
        _, area = m.face_normals()
        size = max(float(np.linalg.norm(m.size())), 1e-9)
        degenerate = int((area < (size * 1e-5) ** 2).sum())
        if degenerate:
            out.append(_issue("GEO_DEGENERATE_FACES", "error", "geometry", f"{degenerate} zero-area faces", w,
                              "usually a zero-sized dimension or repeated profile point", count=degenerate))
        sf = np.sort(m.F, axis=1)
        dup = len(sf) - len(np.unique(sf, axis=0))
        if dup:
            out.append(_issue("GEO_DUPLICATE_FACES", "error", "geometry", f"{dup} duplicate faces", w, count=dup))
        directed = np.concatenate([m.F[:, [0, 1]], m.F[:, [1, 2]], m.F[:, [2, 0]]])
        und = np.sort(directed, axis=1)
        _, counts = np.unique(und, axis=0, return_counts=True)
        open_e, nonman = int((counts == 1).sum()), int((counts > 2).sum())
        if open_e:
            ok = "open_ok" in p.tags
            out.append(_issue("GEO_OPEN_EDGES", "warning" if ok else "error", "geometry", f"{open_e} boundary edges (surface has holes)", w,
                              "intentional (tag open_ok)" if ok else
                              "shapes should be closed; for imported/baked open surfaces tag the part open_ok", count=open_e))
        if nonman:
            out.append(_issue("GEO_NONMANIFOLD_EDGES", "error", "geometry", f"{nonman} edges shared by more than two faces", w, count=nonman))
        _, dcounts = np.unique(directed, axis=0, return_counts=True)
        bad = int((dcounts > 1).sum())
        if bad:
            out.append(_issue("GEO_WINDING_INCONSISTENT", "error", "geometry", f"{bad} edges with inconsistent winding", w, count=bad))
        elif not open_e and m.volume() < 0:
            out.append(_issue("GEO_INVERTED", "error", "geometry", "normals point inward (negative volume)", w))
        comps = _components(m.F, len(m.V))
        if comps > 1:
            out.append(_issue("GEO_PART_FRAGMENTED", "warning", "geometry", f"part consists of {comps} disconnected pieces", w,
                              "a boolean may have split the part; split it into separate named parts or adjust the cut", pieces=comps))
        t = m.triangles()
        e2 = sum(np.einsum("ij,ij->i", t[:, i] - t[:, (i + 1) % 3], t[:, i] - t[:, (i + 1) % 3]) for i in range(3))
        q = 4 * np.sqrt(3) * area / np.maximum(e2, 1e-18)
        slivers = int((q < 0.05).sum())
        slivers_total += slivers
        if slivers and slivers > 0.25 * m.n_tris:
            out.append(_issue("GEO_SLIVER_TRIS", "info", "geometry", f"{slivers}/{m.n_tris} very thin triangles", w,
                              "fewer segments or chamfer-sized details avoid shading artefacts", count=slivers))
    metrics["sliver_triangles"] = slivers_total
    return out


# ---------------------------------------------------------------- assembly


def _bbox_gap(a: np.ndarray, b: np.ndarray) -> float:
    d = np.maximum(0, np.maximum(a[0] - b[1], b[0] - a[1]))
    return float(np.linalg.norm(d))


@validator("assembly", "assembly", "Connectivity of parts (nothing floats), grounding, origin placement, parts hidden inside others, unit sanity.",
           ("ASM_FLOATING_PARTS", "ASM_BELOW_GROUND", "ASM_NOT_GROUNDED", "ASM_ORIGIN_OFFSET", "ASM_HIDDEN_PART", "ASM_SCALE_SUSPICIOUS"))
def assembly(asset: Asset, surface: Surface, metrics: dict):
    out = []
    placement = (asset.meta or {}).get("placement", "floor")
    b = asset.bounds()
    size = b[1] - b[0]
    metrics["size_m"] = [round(float(v), 4) for v in size]
    if size.max() < 0.01 or size.max() > 200:
        out.append(_issue("ASM_SCALE_SUSPICIOUS", "warning", "assembly", f"largest dimension {size.max():.4g} m looks like a units mistake", "",
                          "all lengths are metres (a chair is ~0.9 m tall)"))
    if placement == "floor":
        if b[0][1] < -TOL:
            out.append(_issue("ASM_BELOW_GROUND", "warning", "assembly", f"asset extends {-b[0][1]:.3f} m below the ground plane y=0", "",
                              "raise the lowest part so it rests on y=0"))
        elif b[0][1] > TOL:
            out.append(_issue("ASM_NOT_GROUNDED", "warning", "assembly", f"lowest point is {b[0][1]:.3f} m above the ground plane", "",
                              "floor props should rest on y=0 (or set asset.placement: wall | ceiling | free)"))
        ground = [p.bounds for p in asset.parts if p.bounds[0][1] <= b[0][1] + TOL]
        if ground:
            gb = np.stack([np.min([g[0] for g in ground], 0), np.max([g[1] for g in ground], 0)])
            if not (gb[0][0] - TOL <= 0 <= gb[1][0] + TOL and gb[0][2] - TOL <= 0 <= gb[1][2] + TOL):
                out.append(_issue("ASM_ORIGIN_OFFSET", "warning", "assembly",
                                  f"origin (0,0,0) lies outside the ground footprint x[{gb[0][0]:.3f},{gb[1][0]:.3f}] z[{gb[0][2]:.3f},{gb[1][2]:.3f}]", "",
                                  "move the asset so its origin sits under the part that rests on the ground"))

    parts = asset.parts
    n = len(parts)
    closed = {i: backend.is_closed_manifold(parts[i].mesh) for i in range(n)}

    adj = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if _bbox_gap(parts[i].bounds, parts[j].bounds) > TOL:
                continue
            # open (e.g. imported) meshes cannot be measured exactly; bbox contact is the fallback
            touching = True if not (closed[i] and closed[j]) else backend.min_gap(parts[i].mesh, parts[j].mesh, 2 * TOL) <= TOL
            if touching:
                adj[i].add(j)
                adj[j].add(i)
    if placement == "floor":  # everything must connect to the parts resting on the ground
        roots = [i for i in range(n) if parts[i].bounds[0][1] <= b[0][1] + TOL]
    else:  # otherwise to the largest part
        roots = [max(range(n), key=lambda i: float(np.prod(parts[i].mesh.size())))] if n else []
    seen, stack = set(roots), list(roots)
    while stack:
        i = stack.pop()
        for j in adj[i] - seen:
            seen.add(j)
            stack.append(j)
    floating = [parts[i].name for i in range(n) if i not in seen and "floating_ok" not in parts[i].tags]
    if floating:
        out.append(_issue("ASM_FLOATING_PARTS", "error", "assembly",
                          f"{len(floating)} part(s) do not touch the rest of the asset: {', '.join(floating[:8])}", floating[0],
                          "attach them to a neighbouring part (attach / measure) or check offsets; tag floating_ok if intended",
                          parts=floating))
    metrics["contacts"] = int(sum(len(v) for v in adj.values()) // 2)

    hidden = []
    for i in range(n):
        near = [j for j in adj[i] if closed[j]]
        if not near or not closed[i]:
            continue
        vol, uncovered = backend.uncovered_volume(parts[i].mesh, [parts[j].mesh for j in near])
        if vol > 0 and uncovered < 0.02 * vol:
            hidden.append(parts[i].name)
    for h in hidden:
        out.append(_issue("ASM_HIDDEN_PART", "warning", "assembly", "part is (almost) entirely inside other parts; its triangles are wasted", h,
                          "move it outward, enlarge it, or delete it"))
    return out


# ---------------------------------------------------------------- budget


@validator("budget", "budget", "Profile budgets: triangle count, material slots; unassigned/unused materials.",
           ("BUDGET_TRIANGLES", "BUDGET_MATERIALS", "MAT_UNASSIGNED", "MAT_UNUSED", "BUDGET_NEAR_LIMIT"))
def budget(asset: Asset, surface: Surface, metrics: dict):
    out = []
    tris = asset.n_tris
    limit = asset.budget.get("triangles")
    metrics["triangles"] = tris
    metrics["triangles_by_part"] = {p.base: 0 for p in asset.parts}
    for p in asset.parts:
        metrics["triangles_by_part"][p.base] += p.mesh.n_tris
    if limit:
        metrics["budget_triangles"] = limit
        top = sorted(metrics["triangles_by_part"].items(), key=lambda kv: -kv[1])[:3]
        heavy = ", ".join(f"{k}={v}" for k, v in top)
        if tris > limit:
            out.append(_issue("BUDGET_TRIANGLES", "error", "budget", f"{tris} triangles > budget {limit}", "",
                              f"reduce segments/ops on the heaviest parts ({heavy})", over=tris - limit))
        elif tris > 0.95 * limit:
            out.append(_issue("BUDGET_NEAR_LIMIT", "info", "budget", f"{tris}/{limit} triangles (within 5% of budget)", ""))
    used = sorted({p.material for p in asset.parts if p.material} |
                  {m for sp in surface.parts.values() for m in sp.face_material if m})
    metrics["materials"] = len(used)
    mlimit = asset.budget.get("materials")
    if mlimit and len(used) > mlimit:
        out.append(_issue("BUDGET_MATERIALS", "error", "budget", f"{len(used)} materials > budget {mlimit} ({', '.join(used)})", "",
                          "merge materials or use vertex colours/atlas; each material is a draw call"))
    for p in asset.parts:
        if not p.material:
            out.append(_issue("MAT_UNASSIGNED", "warning", "budget", "part has no material", p.name, "set material: <name>"))
    unused = sorted(set(asset.materials) - set(used))
    if unused:
        out.append(_issue("MAT_UNUSED", "info", "budget", f"materials declared but unused: {', '.join(unused)}", "materials"))
    return out


# ---------------------------------------------------------------- intent


def metric_namespace(asset: Asset) -> dict:
    def vec_ns(v, label):
        return expr.Namespace({"x": float(v[0]), "y": float(v[1]), "z": float(v[2])}, label)

    def box_ns(bounds, tris, label):
        return expr.Namespace({
            "min": vec_ns(bounds[0], label + ".min"), "max": vec_ns(bounds[1], label + ".max"),
            "size": vec_ns(bounds[1] - bounds[0], label + ".size"), "center": vec_ns((bounds[0] + bounds[1]) / 2, label + ".center"),
            "triangles": tris, "width": float(bounds[1][0] - bounds[0][0]), "height": float(bounds[1][1] - bounds[0][1]),
            "depth": float(bounds[1][2] - bounds[0][2]),
        }, label)

    env = dict(asset.env)
    env["asset"] = box_ns(asset.bounds(), asset.n_tris, "asset")
    groups: dict[str, list] = {}
    for p in asset.parts:
        groups.setdefault(p.base, []).append(p)
        env[p.name] = box_ns(p.bounds, p.mesh.n_tris, p.name)
    for p in asset.parts:  # component instances are addressable as a group
        if p.component:
            groups.setdefault(p.component, [])
            if p not in groups[p.component]:
                groups[p.component].append(p)
    for base, ps in groups.items():
        if base not in env or len(ps) > 1:
            bb = np.stack([np.min([q.bounds[0] for q in ps], 0), np.max([q.bounds[1] for q in ps], 0)])
            env[base] = box_ns(bb, sum(q.mesh.n_tris for q in ps), base)
    return env


@validator("design_checks", "intent", "Evaluate the asset's own `checks:` assertions (design intent as tests).", ("CHECK_FAILED", "CHECK_ERROR"))
def design_checks(asset: Asset, surface: Surface, metrics: dict):
    out = []
    env = metric_namespace(asset)
    results = {}
    for i, chk in enumerate(asset.checks):
        where = f"checks[{i}]"
        if not isinstance(chk, dict) or "expr" not in chk:
            out.append(_issue("CHECK_ERROR", "error", "intent", "check must be {expr, min?, max?, doc?}", where))
            continue
        label = chk.get("name") or chk["expr"]
        if "when" in chk:
            try:
                if not expr.evaluate(str(chk["when"]), env):
                    continue
            except expr.ExprError as e:
                out.append(_issue("CHECK_ERROR", "error", "intent", f"when: {e}", where))
                continue
        try:
            v = expr.evaluate(str(chk["expr"]), env)
        except expr.ExprError as e:
            out.append(_issue("CHECK_ERROR", "error", "intent", str(e), where))
            continue
        if isinstance(v, bool):
            ok = v
            results[label] = v
        else:
            v = float(v)
            results[label] = round(v, 4)
            try:
                lo, hi = (None if chk.get(k) is None else float(expr.evaluate(str(chk[k]), env)) for k in ("min", "max"))
            except expr.ExprError as e:
                out.append(_issue("CHECK_ERROR", "error", "intent", f"bound: {e}", where))
                continue
            ok = (lo is None or v >= lo) and (hi is None or v <= hi)
        if not ok:
            rng = f"[{chk.get('min', '-inf')}, {chk.get('max', 'inf')}]"
            out.append(_issue("CHECK_FAILED", chk.get("severity", "error"), "intent", f"{label} = {results[label]} not in {rng}", where,
                              chk.get("doc", ""), value=results[label]))
    if results:
        metrics["checks"] = results
    return out


# ---------------------------------------------------------------- surface


@validator("uv_layout", "surface", "UV0 presence, 0..1 bounds, overlap, texel-density consistency and atlas utilization; normal orientation.",
           ("UV_MISSING", "UV_OUT_OF_BOUNDS", "UV_OVERLAP", "UV_TEXEL_DENSITY", "NRM_FLIPPED", "UV_LOCK_STALE", "UV_REGION_REGENERATED",
            "UV_UNLOCKED", "ATTR_INVALIDATED"))
def uv_layout(asset: Asset, surface: Surface, metrics: dict):
    out = []
    for p in asset.parts:
        sp = surface.parts[p.name]
        fn, _ = p.mesh.face_normals()
        cn = sp.normals[sp.indices]
        flipped = int((np.einsum("ijk,ik->ij", cn, fn) < -1e-3).any(1).sum())
        if flipped:
            out.append(_issue("NRM_FLIPPED", "error", "surface", f"{flipped} faces with vertex normals opposite the face", p.name))
    if surface.uv_method == "none":
        out.append(_issue("UV_MISSING", "warning", "surface", "no UVs generated" + (f" ({surface.uv_error})" if surface.uv_error else ""), "uv",
                          "set uv.method: auto (requires the xatlas package)"))
        return out
    res = min(surface.uv_resolution, 1024)
    dens = {}
    oob = []
    groups: dict[str, list] = {}
    shared = {o for o in surface.owners.values() if o.endswith("*")}
    for p in asset.parts:
        sp = surface.parts[p.name]
        uv = sp.corner_uv
        if uv.min() < -1e-6 or uv.max() > 1 + 1e-6:
            oob.append(p.name)
        o = sp.uv_owner
        if o not in shared or o not in groups:  # shared owners: rasterize one representative
            groups.setdefault(o, []).append(np.stack([uv[..., 0] * res, (1 - uv[..., 1]) * res], -1))
        a2 = 0.5 * np.abs((uv[:, 1, 0] - uv[:, 0, 0]) * (uv[:, 2, 1] - uv[:, 0, 1]) - (uv[:, 2, 0] - uv[:, 0, 0]) * (uv[:, 1, 1] - uv[:, 0, 1]))
        _, a3 = p.mesh.face_normals()
        dens.setdefault(p.base, [0.0, 0.0])
        dens[p.base][0] += a2.sum()
        dens[p.base][1] += a3.sum()
    if oob:
        out.append(_issue("UV_OUT_OF_BOUNDS", "error", "surface", f"UVs outside 0..1 on: {', '.join(oob)}", oob[0]))
    total = np.zeros((res, res), dtype=np.int32)
    overlap = np.zeros((res, res), dtype=bool)
    masks = {}
    for o, tris in groups.items():
        count, _ = coverage(np.concatenate(tris), res, res)
        masks[o] = count > 0
        total += masks[o]
        overlap |= count > 1  # charts of one owner overlapping themselves
    overlap |= total > 1  # different owners overlapping (never intended)
    covered = int((total > 0).sum())
    ratio = int(overlap.sum()) / max(covered, 1)
    metrics["uv_utilization"] = round(covered / res / res, 3)
    metrics["uv_overlap"] = round(ratio, 4)
    metrics["uv_owners"] = len(groups)
    if ratio > 0.002:
        involved = sorted(o.rstrip("*") for o, m in masks.items() if (m & overlap).any())
        out.append(_issue("UV_OVERLAP", "error", "surface", f"{ratio:.1%} of used UV area overlaps", ",".join(involved[:6]),
                          "run `sw uv lock` after structural changes, or remove authored overlapping UVs", ratio=round(ratio, 4)))
    if surface.uv_method == "regions":
        if surface.lock == "stale":
            out.append(_issue("UV_LOCK_STALE", "warning", "surface", f"uv.lock.yaml does not match the parts ({', '.join(surface.lock_notes[:6])}); "
                              "regions were recomputed, so every chart may have moved", "uv", "run `sw uv lock ASSET` and commit uv.lock.yaml"))
        elif surface.lock == "used" and surface.lock_notes:
            out.append(_issue("UV_REGION_REGENERATED", "info", "surface", f"geometry changed since the lock; charts regenerated inside their fixed regions: "
                              f"{', '.join(surface.lock_notes[:8])}", "uv", "textures/bakes for these parts must be redone; other parts are unaffected"))
        elif surface.lock == "none":
            out.append(_issue("UV_UNLOCKED", "info", "surface", "no uv.lock.yaml: UV regions follow part areas and move when parts change", "uv",
                              "run `sw uv lock ASSET` before texturing or baking"))
    for p in asset.parts:
        if p.mesh.invalidated:
            sev = "warning" if p.source == "file" and "uv" in p.mesh.invalidated else "info"
            out.append(_issue("ATTR_INVALIDATED", sev, "surface", f"attributes dropped by a topology-changing op: {', '.join(sorted(p.mesh.invalidated))}", p.name,
                              "authored UVs/colours do not survive booleans/decimation (docs/MESH_MODEL.md); apply those ops before authoring"))
    texture = asset.budget.get("texture_size", surface.uv_resolution)
    px_per_m = {k: float(np.sqrt(v[0] / max(v[1], 1e-12)) * texture) for k, v in dens.items() if v[1] > 0}
    if px_per_m:
        vals = np.array(list(px_per_m.values()))
        metrics["texel_density_px_m"] = round(float(np.median(vals)), 1)
        spread = vals.max() / max(vals.min(), 1e-9)
        if spread > 1.5:
            lo = min(px_per_m, key=px_per_m.get)
            hi = max(px_per_m, key=px_per_m.get)
            out.append(_issue("UV_TEXEL_DENSITY", "warning", "surface", f"texel density varies {spread:.2f}x ({lo}: {px_per_m[lo]:.0f} px/m, {hi}: {px_per_m[hi]:.0f} px/m)", lo,
                              "regions follow surface area; after large size changes run `sw uv lock` again"))
        target = asset.budget.get("texel_density")
        if target:
            metrics["texel_density_target"] = target
    return out


# ---------------------------------------------------------------- style


@validator("style_heuristics", "style", "Style-profile heuristics (e.g. chunky styles forbid spindly parts). Warnings only.",
           ("STYLE_THIN_FEATURE", "STYLE_TOO_MANY_PARTS", "STYLE_MATERIALS"))
def style_heuristics(asset: Asset, surface: Surface, metrics: dict):
    out = []
    h = (asset.style or {}).get("heuristics") or {}
    min_feature = h.get("min_feature_m")
    if min_feature:
        thin = {}
        for p in asset.parts:
            t = float(np.sort(p.mesh.size())[0])
            if t < min_feature and "thin_ok" not in p.tags:
                thin[p.base] = min(t, thin.get(p.base, 1e9))
        for base, t in thin.items():
            out.append(_issue("STYLE_THIN_FEATURE", "warning", "style", f"thinnest dimension {t * 100:.1f} cm < style minimum {min_feature * 100:.1f} cm", base,
                              f"'{asset.style.get('name')}' wants chunky forms; thicken this part or tag it thin_ok"))
    max_parts = h.get("max_parts")
    if max_parts and len({p.base for p in asset.parts}) > max_parts:
        out.append(_issue("STYLE_TOO_MANY_PARTS", "warning", "style", f"{len({p.base for p in asset.parts})} distinct parts > style guide {max_parts}", "",
                          "favour fewer, larger primary forms"))
    max_mat = h.get("max_materials")
    if max_mat and len({p.material for p in asset.parts}) > max_mat:
        out.append(_issue("STYLE_MATERIALS", "warning", "style", f"more than {max_mat} materials", ""))
    return out
