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
from .targets import export_settings

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

    def mesh_primitive(self, positions, indices, normals=None, uvs=None, material=None, colors=None, tangents: bool = False) -> dict:
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


def _collision_meshes(asset: Asset) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """Convex collision proxies: none | single_box | single_hull | box | hull (per part); `parts:` limits which parts."""
    cfg = asset.collision or {}
    mode = cfg.get("mode", "none")
    if mode == "none":
        return []
    from .. import backend

    only = set(cfg.get("parts") or [])
    parts = [p for p in asset.parts if not only or p.base in only or p.name in only]
    if not parts:
        return []
    V_all = np.concatenate([p.mesh.V for p in parts])
    if mode == "single_box":
        t = backend.box_bounds(np.stack([V_all.min(0), V_all.max(0)]))
        return [(0, t.V, t.F)]
    if mode == "single_hull":
        t = backend.convex_hull(V_all)
        return [(0, t.V, t.F)]
    out = []
    for i, p in enumerate(parts):
        V = p.mesh.V
        t = backend.box_bounds(np.stack([V.min(0), V.max(0)])) if mode == "box" else backend.convex_hull(V)
        out.append((i, t.V, t.F))
    return out


COLLISION_MODES = ("none", "single_box", "single_hull", "box", "hull")


def _recipe(m: dict) -> dict:
    def conv(v):
        if isinstance(v, (list, tuple)) and len(v) in (3, 4) and all(isinstance(x, float) for x in v):
            return "#" + "".join(f"{int(round(x * 255)):02x}" for x in v[:3])
        return v
    return {"archetype": m.get("archetype", "flat"), "params": {k: conv(v) for k, v in (m.get("args") or {}).items()},
            **({"instance_of": m["instance_of"]} if m.get("instance_of") else {})}


def _write_groups(b: _Builder, asset: Asset, surface, nodes: list, meshes: list, mat_index: dict, normal_mapped) -> None:
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
        P, N, U, C, F = [], [], [], [], []
        base, first = 0, 0
        has_uv = all(sp.uvs is not None for _, sp, _, _ in items)
        has_col = any(sp.colors is not None for _, sp, _, _ in items)
        for name, sp, used, faces in items:
            P.append(sp.positions[used] - (np.zeros(3, np.float32) if pivot is None else np.asarray(pivot, np.float32)))
            N.append(sp.normals[used])
            if has_uv:
                U.append(sp.uvs[used])
            if has_col:
                C.append(sp.colors[used] if sp.colors is not None else np.ones((len(used), 4), np.float32))
            F.append(faces + base)
            ranges.append({"part": name, "material": g, "first_index": first * 3, "index_count": int(len(faces)) * 3})
            base += len(used)
            first += len(faces)
        mi = mat_index.get(g)
        prims.append(b.mesh_primitive(np.concatenate(P), np.concatenate(F).astype(np.uint32), np.concatenate(N),
                                      np.concatenate(U) if has_uv else None, mi, np.concatenate(C) if has_col else None,
                                      tangents=mi in normal_mapped))
    return prims, ranges


def _primitives(b: _Builder, sp, part, pivot, mat_index: dict, normal_mapped=frozenset()) -> list[dict]:
    """One primitive per effective material (face `material` attribute, else the part's)."""
    eff = np.array([m if m else part.material for m in sp.face_material], dtype=object)
    groups = list(dict.fromkeys(eff))
    pos = sp.positions - pivot.astype(np.float32)
    if len(groups) == 1:
        mi = mat_index.get(groups[0])
        return [b.mesh_primitive(pos, sp.indices, sp.normals, sp.uvs, mi, sp.colors, tangents=mi in normal_mapped)]
    prims = []
    for g in groups:
        faces = sp.indices[eff == g]
        used = np.unique(faces.reshape(-1))
        remap = np.full(len(pos), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        prims.append(b.mesh_primitive(pos[used], remap[faces].astype(np.uint32), sp.normals[used],
                                      None if sp.uvs is None else sp.uvs[used], mat_index.get(g),
                                      None if sp.colors is None else sp.colors[used], tangents=mat_index.get(g) in normal_mapped))
    return prims


def write_glb(asset: Asset, surface: Surface, path: Path, validation_status: str = "UNKNOWN", textures=None) -> dict:
    """textures: a baked atlas to use instead of baking (LOD files share LOD0's atlas)."""
    from ..bake import textures_for, to_png_bytes

    b = _Builder()
    tex = textures if textures is not None else textures_for(asset, surface)
    images, textures, samplers = [], [], []
    if tex is not None:
        for label, arr in (("base_color", tex.base), ("orm", tex.orm)):
            images.append({"name": f"{asset.name}_{label}", "mimeType": "image/png", "bufferView": b.add_bytes(to_png_bytes(arr))})
            textures.append({"source": len(images) - 1, "sampler": 0})
        samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071})
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
    normal_mapped = {mat_index[n] for n, m in asset.materials.items() if n in mat_index and "normal" in (m.get("textures") or {})}
    if settings["merge"] == "by_material":  # rigid groups: one node per group, one primitive per material
        _write_groups(b, asset, surface, nodes, meshes, mat_index, normal_mapped)
    else:
        for p in asset.parts:
            sp = surface.parts[p.name]
            piv = pivots[p.name]
            meshes.append({"name": p.name, "primitives": _primitives(b, sp, p, piv, mat_index, normal_mapped)})
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
            node_of[p.name] = len(nodes)
            nodes.append(node)
        for p in asset.parts:  # hierarchy + relative translations
            idx = node_of[p.name]
            parent = node_of.get(p.parent, 0) if p.parent else 0
            rel = pivots[p.name] - (pivots[p.parent] if p.parent in pivots else np.zeros(3))
            if np.any(np.abs(rel) > 0):
                nodes[idx]["translation"] = [float(v) for v in rel]
            nodes[parent].setdefault("children", []).append(idx)
    for s in asset.sockets:
        node = {"name": f"SOCKET_{s.name}", "translation": [float(v) for v in s.position], "extras": {"socket": s.name}}
        if s.doc:
            node["extras"]["doc"] = s.doc
        if any(s.rotation):
            node["rotation"] = [float(v) for v in matrix_to_quat(rotation_matrix(s.rotation))]
        nodes.append(node)
        nodes[0]["children"].append(len(nodes) - 1)
    for idx, V, F in _collision_meshes(asset):
        prim = b.mesh_primitive(np.asarray(V, dtype=np.float32), np.asarray(F, dtype=np.uint32))
        name = settings["target"].collision_name(asset.name, idx, convex=True)
        meshes.append({"name": name, "primitives": [prim]})
        nodes.append({"name": name, "mesh": len(meshes) - 1, "extras": {"collision": True}})
        nodes[0]["children"].append(len(nodes) - 1)

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
        "scenes": [{"name": asset.name, "nodes": [0]}],
        "nodes": nodes,
        "meshes": meshes,
        "accessors": b.accessors,
        "bufferViews": b.views,
        "buffers": [{"byteLength": len(b.bin)}],
    }
    if materials:
        gltf["materials"] = materials
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
