"""GLB (binary glTF 2.0) writer.

Hand-written instead of delegating to a library so that the output is
byte-deterministic and every piece of semantic metadata is under our control:

* one node per semantic part instance, named exactly like the part;
* semantic hierarchy from `parent:`; optional per-part pivots;
* sockets as empty nodes (``SOCKET_<name>``) with extras;
* optional collision proxies (``UCX_<asset>_<nn>`` convention by default);
* asset-level extras: parameters, source hash, units, axis convention.

glTF is Y-up, right-handed, metres, and assets face +Z: identical to the
modelling convention, so no axis conversion happens anywhere.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from .. import __version__
from ..assemble import Asset
from ..mesh import rotation_matrix
from ..surface import Surface
from .targets import export_settings, rigid_groups

FLOAT, UINT16, UINT32 = 5126, 5123, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


def matrix_to_quat(M) -> np.ndarray:
    """Rotation matrix -> glTF quaternion [x, y, z, w]."""
    R = np.asarray(M)[:3, :3]
    w = np.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = np.copysign(np.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = np.copysign(np.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = np.copysign(np.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    q = np.array([x, y, z, w])
    return q / np.linalg.norm(q)


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


class _Builder:
    def __init__(self):
        self.bin = bytearray()
        self.views, self.accessors = [], []

    def add(self, data: np.ndarray, component: int, type_: str, target: int | None, minmax: bool = False) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        raw = np.ascontiguousarray(data).tobytes()
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(raw)}
        if target:
            view["target"] = target
        self.bin.extend(raw)
        self.views.append(view)
        acc = {"bufferView": len(self.views) - 1, "componentType": component, "count": int(len(data)), "type": type_}
        if minmax:
            acc["min"] = [float(v) for v in data.min(0)]
            acc["max"] = [float(v) for v in data.max(0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def add_bytes(self, raw: bytes) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        self.views.append({"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(raw)})
        self.bin.extend(raw)
        return len(self.views) - 1

    def mesh_primitive(self, positions, indices, normals=None, uvs=None, material=None, colors=None, tangents: bool = False,
                       uvs1=None, skin=None) -> dict:
        attrs = {"POSITION": self.add(positions.astype(np.float32), FLOAT, "VEC3", ARRAY_BUFFER, minmax=True)}
        if normals is not None:
            attrs["NORMAL"] = self.add(normals.astype(np.float32), FLOAT, "VEC3", ARRAY_BUFFER)
        if uvs is not None:
            # internal UVs are v-up (v = 0 at the image bottom, as trimesh loads them); glTF's v runs
            # down from the image's top row. Without this flip every texture sampled mirrored in engines
            # (found in Phase 11; the Khronos validator and trimesh round-trips cannot see it).
            uv_file = np.stack([uvs[:, 0], 1.0 - uvs[:, 1]], 1)
            attrs["TEXCOORD_0"] = self.add(uv_file.astype(np.float32), FLOAT, "VEC2", ARRAY_BUFFER)
            if tangents and normals is not None:  # normal-mapped materials (Phase 12): tangent space from the file's UVs
                attrs["TANGENT"] = self.add(_tangents(positions, normals, uv_file, indices).astype(np.float32), FLOAT, "VEC4", ARRAY_BUFFER)
        if uvs1 is not None:  # lightmap UVs (Phase 21): same v flip as TEXCOORD_0
            attrs["TEXCOORD_1"] = self.add(np.stack([uvs1[:, 0], 1.0 - uvs1[:, 1]], 1).astype(np.float32), FLOAT, "VEC2", ARRAY_BUFFER)
        if skin is not None:  # Phase 24: (joint indices, weights) per vertex
            attrs["JOINTS_0"] = self.add(np.ascontiguousarray(skin[0], dtype=np.uint16), UINT16, "VEC4", ARRAY_BUFFER)
            attrs["WEIGHTS_0"] = self.add(np.ascontiguousarray(skin[1], dtype=np.float32), FLOAT, "VEC4", ARRAY_BUFFER)
        if colors is not None:
            attrs["COLOR_0"] = self.add(colors.astype(np.float32), FLOAT, "VEC4", ARRAY_BUFFER)
        flat = indices.reshape(-1)
        if len(positions) < 65536:
            idx = self.add(flat.astype(np.uint16), UINT16, "SCALAR", ELEMENT_ARRAY_BUFFER)
        else:
            idx = self.add(flat.astype(np.uint32), UINT32, "SCALAR", ELEMENT_ARRAY_BUFFER)
        prim = {"attributes": attrs, "indices": idx, "mode": 4}
        if material is not None:
            prim["material"] = material
        return prim


def _tangents(P: np.ndarray, N: np.ndarray, UV: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Per-vertex tangents with handedness (Lengyel), in the glTF UV convention."""
    P, N, UV = (np.asarray(x, dtype=np.float64) for x in (P, N, UV))
    F = np.asarray(F, dtype=np.int64).reshape(-1, 3)
    e1, e2 = P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]
    d1, d2 = UV[F[:, 1]] - UV[F[:, 0]], UV[F[:, 2]] - UV[F[:, 0]]
    den = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(den) < 1e-20, 0.0, 1.0 / np.where(np.abs(den) < 1e-20, 1.0, den))
    sdir = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r[:, None]
    tdir = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r[:, None]
    S, T = np.zeros_like(P), np.zeros_like(P)
    for k in range(3):
        np.add.at(S, F[:, k], sdir)
        np.add.at(T, F[:, k], tdir)
    t = S - N * (N * S).sum(1, keepdims=True)
    ln = np.linalg.norm(t, axis=1, keepdims=True)
    fallback = np.cross(N, np.where(np.abs(N[:, :1]) < 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]]))
    t = np.where(ln > 1e-12, t / np.maximum(ln, 1e-12), fallback / np.maximum(np.linalg.norm(fallback, axis=1, keepdims=True), 1e-12))
    w = np.where((np.cross(N, t) * T).sum(1) < 0, -1.0, 1.0)
    return np.c_[t, w]


def _collision_meshes(asset: Asset, groups: dict | None = None) -> list[tuple[str | None, np.ndarray, np.ndarray]]:
    """Convex collision proxies: none | single_box | single_hull | box | hull (per part) | hulls (a few merged hulls, `max`,
    `exclude`); `parts:` limits which parts.
    With rigid groups (merged export) the single modes give one proxy per group, so a hinged lid's collision
    moves with the lid (FRESH_AGENT_08); each proxy carries its group key."""
    cfg = asset.collision or {}
    mode = cfg.get("mode", "none")
    if mode == "none":
        return []
    from .. import backend

    only = set(cfg.get("parts") or [])
    chosen = {p.name for p in asset.parts if not only or p.base in only or p.name in only}
    buckets = {k: [p for p in ps if p.name in chosen] for k, ps in (groups or {None: asset.parts}).items()}
    out = []
    for k, parts in buckets.items():
        if not parts:
            continue
        if mode == "hulls":  # Phase 21: a few hulls that follow the shape (export/collision.py)
            from .collision import decompose

            for pts in decompose(parts, int(cfg.get("max", 24)), cfg.get("exclude")):
                t = backend.collision_hull(pts)
                out.append((k, t.V, t.F))
            continue
        if mode in ("single_box", "single_hull"):
            V = np.concatenate([p.mesh.V for p in parts])
            t = backend.box_bounds(np.stack([V.min(0), V.max(0)])) if mode == "single_box" else backend.collision_hull(V)
            out.append((k, t.V, t.F))
            continue
        for p in parts:
            V = p.mesh.V
            t = backend.box_bounds(np.stack([V.min(0), V.max(0)])) if mode == "box" else backend.collision_hull(V)
            out.append((k, t.V, t.F))
    return out


def collision_proxies(asset: Asset) -> list[tuple[str | None, np.ndarray, np.ndarray]]:
    """The collision proxies write_glb would make for this asset (LOD files reuse LOD0's, so collision is the same at
    every LOD and the multi-hull decomposition runs once)."""
    merged = export_settings(asset)["merge"] == "by_material"
    return _collision_meshes(asset, rigid_groups(asset) if merged else None)


COLLISION_MODES = ("none", "single_box", "single_hull", "box", "hull", "hulls")


def _recipe(m: dict) -> dict:
    def conv(v):
        if isinstance(v, (list, tuple)) and len(v) in (3, 4) and all(isinstance(x, float) for x in v):
            return "#" + "".join(f"{int(round(x * 255)):02x}" for x in v[:3])
        return v
    return {"archetype": m.get("archetype", "flat"), "params": {k: conv(v) for k, v in (m.get("args") or {}).items()},
            **({"instance_of": m["instance_of"]} if m.get("instance_of") else {})}


def _write_groups(b: _Builder, asset: Asset, surface, nodes: list, meshes: list, mat_index: dict, normal_mapped) -> dict:
    """Static parts -> `<asset>_static`; each moving group -> a node named after its head part, placed at
    the head's pivot and parented to the group that holds the head's parent."""
    from .targets import STATIC, rigid_groups

    groups = rigid_groups(asset)
    by_name = {p.name: p for p in asset.parts}
    by_base: dict = {}
    for p in asset.parts:
        by_base.setdefault(p.base, p)
    group_of = {p.name: k for k, ps in groups.items() for p in ps}
    node_of: dict = {}
    pivot_of = {k: (np.zeros(3) if k == STATIC else by_name[k].pivot if by_name[k].pivot is not None else np.zeros(3)) for k in groups}
    for k, ps in groups.items():
        name = merged_node_name(asset) if k == STATIC else k
        prims, ranges = _merged_primitives(b, surface, ps, mat_index, normal_mapped, pivot_of[k])
        meshes.append({"name": name, "primitives": prims})
        node_of[k] = len(nodes)
        nodes.append({"name": name, "mesh": len(meshes) - 1, "extras": {"merged_parts": ranges}})
    for k in groups:
        parent_group = STATIC
        if k != STATIC:
            head = by_name[k]
            par = (by_name.get(head.parent) or by_base.get(head.parent)) if head.parent else None
            parent_group = group_of.get(par.name) if par is not None else None
        parent_idx = 0 if k == STATIC or parent_group in (None, STATIC) else node_of[parent_group]
        rel = pivot_of[k] - (pivot_of[parent_group] if parent_idx else np.zeros(3))
        if np.any(np.abs(rel) > 0):
            nodes[node_of[k]]["translation"] = [float(v) for v in rel]
        nodes[parent_idx].setdefault("children", []).append(node_of[k])
    return {k: (node_of[k], nodes[node_of[k]]["name"], pivot_of[k]) for k in groups}


def merged_node_name(asset: Asset) -> str:
    return f"{asset.name}_static"


def _merged_primitives(b: _Builder, surface, parts, mat_index: dict, normal_mapped=frozenset(), pivot=None):
    """Concatenate static parts per effective material. Returns primitives and part ranges."""
    groups: dict = {}
    for p in parts:
        sp = surface.parts[p.name]
        eff = np.array([m if m else p.material for m in sp.face_material], dtype=object)
        for g in dict.fromkeys(eff):
            faces = sp.indices[eff == g]
            used = np.unique(faces.reshape(-1))
            remap = np.full(len(sp.positions), -1, dtype=np.int64)
            remap[used] = np.arange(len(used))
            groups.setdefault(g, []).append((p.name, sp, used, remap[faces]))
    prims, ranges = [], []
    for g, items in groups.items():
        P, N, U, U1, C, F = [], [], [], [], [], []
        base, first = 0, 0
        has_uv = all(sp.uvs is not None for _, sp, _, _ in items)
        has_uv1 = all(sp.uvs1 is not None for _, sp, _, _ in items)
        has_col = any(sp.colors is not None for _, sp, _, _ in items)
        for name, sp, used, faces in items:
            P.append(sp.positions[used] - (np.zeros(3, np.float32) if pivot is None else np.asarray(pivot, np.float32)))
            N.append(sp.normals[used])
            if has_uv:
                U.append(sp.uvs[used])
            if has_uv1:
                U1.append(sp.uvs1[used])
            if has_col:
                C.append(sp.colors[used] if sp.colors is not None else np.ones((len(used), 4), np.float32))
            F.append(faces + base)
            ranges.append({"part": name, "material": g, "first_index": first * 3, "index_count": int(len(faces)) * 3})
            base += len(used)
            first += len(faces)
        mi = mat_index.get(g)
        prims.append(b.mesh_primitive(np.concatenate(P), np.concatenate(F).astype(np.uint32), np.concatenate(N),
                                      np.concatenate(U) if has_uv else None, mi, np.concatenate(C) if has_col else None,
                                      tangents=mi in normal_mapped, uvs1=np.concatenate(U1) if has_uv1 else None))
    return prims, ranges


def _primitives(b: _Builder, sp, part, pivot, mat_index: dict, normal_mapped=frozenset(), skin=None) -> list[dict]:
    """One primitive per effective material (face `material` attribute, else the part's). skin: (joints, weights)
    per surface vertex for a skinned part."""
    eff = np.array([m if m else part.material for m in sp.face_material], dtype=object)
    groups = list(dict.fromkeys(eff))
    pos = sp.positions - pivot.astype(np.float32)
    if len(groups) == 1:
        mi = mat_index.get(groups[0])
        return [b.mesh_primitive(pos, sp.indices, sp.normals, sp.uvs, mi, sp.colors, tangents=mi in normal_mapped,
                                 uvs1=sp.uvs1, skin=skin)]
    prims = []
    for g in groups:
        faces = sp.indices[eff == g]
        used = np.unique(faces.reshape(-1))
        remap = np.full(len(pos), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        prims.append(b.mesh_primitive(pos[used], remap[faces].astype(np.uint32), sp.normals[used],
                                      None if sp.uvs is None else sp.uvs[used], mat_index.get(g),
                                      None if sp.colors is None else sp.colors[used], tangents=mat_index.get(g) in normal_mapped,
                                      uvs1=None if sp.uvs1 is None else sp.uvs1[used],
                                      skin=None if skin is None else (skin[0][used], skin[1][used])))
    return prims


def write_glb(asset: Asset, surface: Surface, path: Path, validation_status: str = "UNKNOWN", textures=None, collision=True) -> dict:
    """textures: a baked atlas to use instead of baking (LOD files share LOD0's atlas).
    collision: False leaves out the collision proxies (a preview file for web viewers, which draw every mesh); a list
    from collision_proxies() uses those (LOD files)."""
    from ..bake import textures_for, to_png_bytes

    b = _Builder()
    tex = textures if textures is not None else textures_for(asset, surface)
    images, textures, samplers = [], [], []
    if tex is not None:
        trim = getattr(tex, "trim", None)  # Phase 21: the pack's shared trim sheet, same bytes in every member
        prefix = f"{trim['pack']}_trim_{trim['key'][:8]}" if trim else asset.name
        for label, arr in (("base_color", tex.base), ("orm", tex.orm)):
            images.append({"name": f"{prefix}_{label}", "mimeType": "image/png", "bufferView": b.add_bytes(to_png_bytes(arr))})
            textures.append({"source": len(images) - 1, "sampler": 0})
        # a trim sheet repeats along U (10497 REPEAT); per-asset atlases clamp (33071)
        samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497 if trim else 33071, "wrapT": 33071})
    materials, mat_index = [], {}
    image_of: dict = {}  # authored image path -> texture index (each file embedded once, bytes unchanged)

    def authored_texture(rel: str) -> int:
        from ..bake import authored_image_path

        full = authored_image_path(asset.dir, rel, asset.file_roots)
        if rel not in image_of:
            if len(samplers) == (1 if tex is not None else 0):
                samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})  # repeat, as authored
            mime = "image/png" if full.suffix.lower() == ".png" else "image/jpeg"
            images.append({"name": full.stem, "mimeType": mime, "bufferView": b.add_bytes(full.read_bytes())})
            textures.append({"source": len(images) - 1, "sampler": len(samplers) - 1})
            image_of[rel] = len(textures) - 1
        return image_of[rel]

    used = {p.material for p in asset.parts} | {m for sp in surface.parts.values() for m in sp.face_material if m}
    for name, m in asset.materials.items():
        if name not in used:
            continue
        base = list(srgb_to_linear(m["base_color"][:3])) + [m["base_color"][3] if len(m["base_color"]) > 3 else 1.0]
        if m.get("authored"):  # pass-through texture set (docs/IMPORT.md)
            t = m.get("textures") or {}
            pbr = {"baseColorFactor": [round(float(v), 6) for v in base], "metallicFactor": float(m["metallic"]),
                   "roughnessFactor": float(m["roughness"])}
            if "base_color" in t:
                pbr["baseColorTexture"] = {"index": authored_texture(t["base_color"])}
            if "metallic_roughness" in t:
                pbr["metallicRoughnessTexture"] = {"index": authored_texture(t["metallic_roughness"])}
            mat = {"name": name, "pbrMetallicRoughness": pbr, "extras": {"shapewright_material": {"archetype": "authored"}}}
            if "normal" in t:
                mat["normalTexture"] = {"index": authored_texture(t["normal"])}
            if "occlusion" in t:
                mat["occlusionTexture"] = {"index": authored_texture(t["occlusion"])}
            if "emissive" in t:
                mat["emissiveTexture"] = {"index": authored_texture(t["emissive"])}
                mat["emissiveFactor"] = [round(float(v), 6) for v in srgb_to_linear((m.get("emissive") or [1, 1, 1])[:3])]
            elif m.get("emissive"):
                mat["emissiveFactor"] = [round(float(v), 6) for v in srgb_to_linear(m["emissive"][:3])]
            if m.get("alpha_mode", "OPAQUE") != "OPAQUE":
                mat["alphaMode"] = m["alpha_mode"]
            if m.get("double_sided"):
                mat["doubleSided"] = True
            mat_index[name] = len(materials)
            materials.append(mat)
            continue
        mat = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [round(float(v), 6) for v in base],
                                                        "metallicFactor": float(m["metallic"]), "roughnessFactor": float(m["roughness"])}}
        if tex is None and m.get("archetype") == "vertex":  # the colour is in COLOR_0 (Phase 21)
            mat["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, round(float(base[3]), 6)]
            mat["extras"] = {"shapewright_material": _recipe(m)}
        if tex is not None:  # every material samples the shared baked atlas; its recipe travels in extras
            mat["pbrMetallicRoughness"] = {"baseColorFactor": [1.0, 1.0, 1.0, round(float(base[3]), 6)],
                                           "baseColorTexture": {"index": 0}, "metallicRoughnessTexture": {"index": 1},
                                           "metallicFactor": 1.0, "roughnessFactor": 1.0}
            mat["extras"] = {"shapewright_material": _recipe(m)}
        if m.get("emissive"):
            mat["emissiveFactor"] = [round(float(v), 6) for v in srgb_to_linear(m["emissive"][:3])]
        if m.get("alpha_mode", "OPAQUE") != "OPAQUE":
            mat["alphaMode"] = m["alpha_mode"]
        if m.get("double_sided"):
            mat["doubleSided"] = True
        mat_index[name] = len(materials)
        materials.append(mat)

    # root node: the asset name, unless a part has that name (importers would rename the part; FRESH_AGENT_07)
    root = asset.name if all(p.name != asset.name for p in asset.parts) else f"{asset.name}_root"
    nodes = [{"name": root, "children": [], "extras": {}}]
    meshes = []
    node_of: dict[str, int] = {}
    pivots = {p.name: (p.pivot if p.pivot is not None else np.zeros(3)) for p in asset.parts}
    settings = export_settings(asset)
    from .. import rig as R

    try:
        rg = R.build_rig(asset)
    except ValueError:
        rg = None  # reported by validation (RIG_INVALID); export the static mesh
    if rg is not None:  # skinned parts sit at the origin (their vertices are in asset space, like the joints)
        for pn in rg.weights:
            pivots[pn] = np.zeros(3)
        settings = dict(settings, merge="none")
    normal_mapped = {mat_index[n] for n, m in asset.materials.items() if n in mat_index and "normal" in (m.get("textures") or {})}
    group_nodes: dict = {}
    if settings["merge"] == "by_material":  # rigid groups: one node per group, one primitive per material
        group_nodes = _write_groups(b, asset, surface, nodes, meshes, mat_index, normal_mapped)
    else:
        for p in asset.parts:
            sp = surface.parts[p.name]
            piv = pivots[p.name]
            skin = R.top4(R.surface_weights(rg, p, sp.positions)) if rg is not None and p.name in rg.weights else None
            meshes.append({"name": p.name, "primitives": _primitives(b, sp, p, piv, mat_index, normal_mapped, skin)})
            extras = {"part": p.base, "tags": p.tags} if p.tags else {"part": p.base}
            if p.component:
                extras["component"] = p.component
            if p.source != "native":
                extras["geometry_source"] = p.source
            if p.doc:
                extras["doc"] = p.doc
            if p.instance:
                extras["instance"] = p.instance
            node = {"name": p.name, "mesh": len(meshes) - 1, "extras": extras}
            if skin is not None:
                node["skin"] = 0
            node_of[p.name] = len(nodes)
            nodes.append(node)
        for p in asset.parts:  # hierarchy + relative translations
            idx = node_of[p.name]
            parent = node_of.get(p.parent, 0) if p.parent else 0
            rel = pivots[p.name] - (pivots[p.parent] if p.parent in pivots else np.zeros(3))
            if np.any(np.abs(rel) > 0):
                nodes[idx]["translation"] = [float(v) for v in rel]
            nodes[parent].setdefault("children", []).append(idx)
    skins, animations = [], []
    if rg is not None:  # Phase 24: joint nodes (rest translations, no rotations) and the skin
        taken = {n["name"] for n in nodes}
        first = len(nodes)
        for j, jn in enumerate(rg.names):
            par = rg.parents[j]
            t = rg.rest[j] - (rg.rest[par] if par >= 0 else 0)
            nodes.append({"name": jn if jn not in taken else f"{jn}_joint", "translation": [float(v) for v in t],
                          "extras": {"joint": jn}})
        for j in range(len(rg.names)):
            par = rg.parents[j]
            (nodes[first + par] if par >= 0 else nodes[0]).setdefault("children", []).append(first + j)
        ibm = np.tile(np.eye(4, dtype=np.float32), (len(rg.names), 1, 1))
        ibm[:, :3, 3] = -rg.rest
        acc = b.add(ibm.transpose(0, 2, 1).reshape(-1, 16), FLOAT, "MAT4", None)  # glTF matrices are column-major
        skins.append({"name": f"{asset.name}_skin", "joints": list(range(first, first + len(rg.names))),
                      "inverseBindMatrices": acc, "skeleton": first + rg.parents.index(-1)})
        try:
            clips = R.clip_settings(asset)
        except ValueError:
            clips = {}  # reported by validation
        for cname, cp in clips.items():  # Phase 24 (G5): procedural clips as joint rotation (+ root translation) channels
            times, rots, offs = R.clip_keys(rg, cname, cp)
            tacc = b.add(times.astype(np.float32).reshape(-1, 1), FLOAT, "SCALAR", None, minmax=True)
            a_samplers, a_channels = [], []
            for j, eul in rots.items():
                q = np.array([matrix_to_quat(rotation_matrix(e)) for e in eul])
                for k in range(1, len(q)):  # keep neighbouring keys in one hemisphere (slerp takes the short way)
                    if q[k] @ q[k - 1] < 0:
                        q[k] = -q[k]
                a_samplers.append({"input": tacc, "output": b.add(q.astype(np.float32), FLOAT, "VEC4", None), "interpolation": "LINEAR"})
                a_channels.append({"sampler": len(a_samplers) - 1, "target": {"node": first + j, "path": "rotation"}})
            if np.abs(offs).max() > 1e-9:
                root_j = rg.parents.index(-1)
                tr = (rg.rest[root_j] + offs).astype(np.float32)
                a_samplers.append({"input": tacc, "output": b.add(tr, FLOAT, "VEC3", None), "interpolation": "LINEAR"})
                a_channels.append({"sampler": len(a_samplers) - 1, "target": {"node": first + root_j, "path": "translation"}})
            if a_channels:
                animations.append({"name": cname, "samplers": a_samplers, "channels": a_channels})
    try:
        rclips = R.rigid_clips(asset)
    except ValueError:
        rclips = []  # reported by validation
    for clip in rclips:  # rigid clips: rotation channels on the part's node (merged: its hinge group's node)
        targets = []
        for pn in clip["parts"]:
            if pn in node_of:
                targets.append(node_of[pn])
            else:
                for key, (owner, _, _) in (group_nodes or {}).items():
                    if key == pn and owner not in targets:
                        targets.append(owner)
        if not targets:
            continue
        times, eul = R.rigid_keys(clip)
        tacc = b.add(times.astype(np.float32).reshape(-1, 1), FLOAT, "SCALAR", None, minmax=True)
        q = np.array([matrix_to_quat(rotation_matrix(e)) for e in eul])
        for k in range(1, len(q)):
            if q[k] @ q[k - 1] < 0:
                q[k] = -q[k]
        qacc = b.add(q.astype(np.float32), FLOAT, "VEC4", None)
        animations.append({"name": clip["name"], "samplers": [{"input": tacc, "output": qacc, "interpolation": "LINEAR"}],
                           "channels": [{"sampler": 0, "target": {"node": t, "path": "rotation"}} for t in targets]})
    for s in asset.sockets:
        node = {"name": f"SOCKET_{s.name}", "translation": [float(v) for v in s.position], "extras": {"socket": s.name}}
        if s.doc:
            node["extras"]["doc"] = s.doc
        if any(s.rotation):
            node["rotation"] = [float(v) for v in matrix_to_quat(rotation_matrix(s.rotation))]
        nodes.append(node)
        nodes[0]["children"].append(len(nodes) - 1)
    placed = group_nodes if settings["merge"] == "by_material" else None
    counter: dict = {}
    proxies = collision if isinstance(collision, list) else (
        _collision_meshes(asset, rigid_groups(asset) if placed is not None else None) if collision else [])
    for key, V, F in proxies:
        owner, owner_name, pivot = (0, asset.name, np.zeros(3)) if placed is None else placed[key]
        idx = counter[owner_name] = counter.get(owner_name, -1) + 1
        name = settings["target"].collision_name(owner_name, idx, convex=True)
        local = settings["target"].name == "godot" and owner != 0  # Godot: child of the group node, so it moves with it
        verts = np.asarray(V, dtype=np.float64) - (pivot if local else 0)
        prim = b.mesh_primitive(verts.astype(np.float32), np.asarray(F, dtype=np.uint32))
        meshes.append({"name": name, "primitives": [prim]})
        nodes.append({"name": name, "mesh": len(meshes) - 1, "extras": {"collision": True, "for": owner_name}})
        nodes[owner if local else 0].setdefault("children", []).append(len(nodes) - 1)

    skinned_roots = [i for i, n in enumerate(nodes) if "skin" in n]  # glTF: a skinned mesh's parents do not move it
    if skinned_roots:
        nodes[0]["children"] = [c for c in nodes[0].get("children", []) if c not in skinned_roots]
    nodes[0]["extras"] = {"shapewright": {
        "version": __version__, "source_hash": asset.source_hash, "units": "m", "up": "+Y", "front": "+Z",
        "kind": asset.meta.get("kind", ""), "params": {k: round(v, 6) for k, v in asset.env.items()},
        "profile": asset.profile.get("name", ""), "style": asset.style.get("name", ""), "validation": validation_status,
        "pack": asset.source.get("_pack", ""),
        "uv": {"method": surface.uv_method, "lock": surface.lock},
    }}
    if not nodes[0]["children"]:
        nodes[0].pop("children")
    gltf = {
        "asset": {"version": "2.0", "generator": f"shapewright {__version__}"},
        "scene": 0,
        "scenes": [{"name": asset.name, "nodes": [0] + skinned_roots}],
        "nodes": nodes,
        "meshes": meshes,
        "accessors": b.accessors,
        "bufferViews": b.views,
        "buffers": [{"byteLength": len(b.bin)}],
    }
    if materials:
        gltf["materials"] = materials
    if skins:
        gltf["skins"] = skins
    if animations:
        gltf["animations"] = animations
    if images:
        gltf["images"], gltf["textures"], gltf["samplers"] = images, textures, samplers
    js = json.dumps(gltf, separators=(",", ":"), sort_keys=True).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    while len(b.bin) % 4:
        b.bin.append(0)
    blob = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(b.bin))
    blob += struct.pack("<II", len(js), 0x4E4F534A) + js
    blob += struct.pack("<II", len(b.bin), 0x004E4942) + bytes(b.bin)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return {"path": str(path), "bytes": len(blob), "nodes": len(nodes), "meshes": len(meshes), "materials": len(materials)}
