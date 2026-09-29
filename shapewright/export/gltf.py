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
from ..surface import Surface

FLOAT, UINT16, UINT32 = 5126, 5123, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


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

    def mesh_primitive(self, positions, indices, normals=None, uvs=None, material=None) -> dict:
        attrs = {"POSITION": self.add(positions.astype(np.float32), FLOAT, "VEC3", ARRAY_BUFFER, minmax=True)}
        if normals is not None:
            attrs["NORMAL"] = self.add(normals.astype(np.float32), FLOAT, "VEC3", ARRAY_BUFFER)
        if uvs is not None:
            attrs["TEXCOORD_0"] = self.add(uvs.astype(np.float32), FLOAT, "VEC2", ARRAY_BUFFER)
        flat = indices.reshape(-1)
        if len(positions) < 65536:
            idx = self.add(flat.astype(np.uint16), UINT16, "SCALAR", ELEMENT_ARRAY_BUFFER)
        else:
            idx = self.add(flat.astype(np.uint32), UINT32, "SCALAR", ELEMENT_ARRAY_BUFFER)
        prim = {"attributes": attrs, "indices": idx, "mode": 4}
        if material is not None:
            prim["material"] = material
        return prim


def _collision_meshes(asset: Asset) -> list[tuple[str, np.ndarray, np.ndarray]]:
    mode = (asset.collision or {}).get("mode", "none")
    if mode == "none":
        return []
    import trimesh

    out = []
    groups: dict[str, list] = {}
    for p in asset.parts:
        groups.setdefault(p.name if mode in ("box", "hull") else "all", []).append(p)
    if mode == "single_box":
        b = asset.bounds()
        t = trimesh.creation.box(bounds=b)
        return [("0", t.vertices, t.faces)]
    for i, (name, ps) in enumerate(groups.items()):
        V = np.concatenate([p.mesh.V for p in ps])
        if mode == "box":
            t = trimesh.creation.box(bounds=np.stack([V.min(0), V.max(0)]))
        else:
            t = trimesh.convex.convex_hull(V)
        out.append((f"{i:02d}", t.vertices, t.faces))
    return out


def write_glb(asset: Asset, surface: Surface, path: Path, validation_status: str = "UNKNOWN") -> dict:
    b = _Builder()
    materials, mat_index = [], {}
    for name, m in asset.materials.items():
        if not any(p.material == name for p in asset.parts):
            continue
        base = list(srgb_to_linear(m["base_color"][:3])) + [m["base_color"][3] if len(m["base_color"]) > 3 else 1.0]
        mat = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [round(float(v), 6) for v in base],
                                                        "metallicFactor": float(m["metallic"]), "roughnessFactor": float(m["roughness"])}}
        if m.get("emissive"):
            mat["emissiveFactor"] = [round(float(v), 6) for v in srgb_to_linear(m["emissive"][:3])]
        if m.get("alpha_mode", "OPAQUE") != "OPAQUE":
            mat["alphaMode"] = m["alpha_mode"]
        if m.get("double_sided"):
            mat["doubleSided"] = True
        mat_index[name] = len(materials)
        materials.append(mat)

    nodes = [{"name": asset.name, "children": [], "extras": {}}]
    meshes = []
    node_of: dict[str, int] = {}
    pivots = {p.name: (p.pivot if p.pivot is not None else np.zeros(3)) for p in asset.parts}
    for p in asset.parts:
        sp = surface.parts[p.name]
        piv = pivots[p.name]
        prim = b.mesh_primitive(sp.positions - piv.astype(np.float32), sp.indices, sp.normals, sp.uvs, mat_index.get(p.material))
        meshes.append({"name": p.name, "primitives": [prim]})
        extras = {"part": p.base, "tags": p.tags} if p.tags else {"part": p.base}
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
            from scipy.spatial.transform import Rotation

            q = Rotation.from_euler("xyz", s.rotation, degrees=True).as_quat()
            node["rotation"] = [float(v) for v in q]
        nodes.append(node)
        nodes[0]["children"].append(len(nodes) - 1)
    naming = (asset.profile.get("export") or {}).get("collision_naming", "ucx")
    for suffix, V, F in _collision_meshes(asset):
        prim = b.mesh_primitive(np.asarray(V, dtype=np.float32), np.asarray(F, dtype=np.uint32))
        name = f"UCX_{asset.name}_{suffix}" if naming == "ucx" else f"{asset.name}_{suffix}-colonly"
        meshes.append({"name": name, "primitives": [prim]})
        nodes.append({"name": name, "mesh": len(meshes) - 1, "extras": {"collision": True}})
        nodes[0]["children"].append(len(nodes) - 1)

    nodes[0]["extras"] = {"shapewright": {
        "version": __version__, "source_hash": asset.source_hash, "units": "m", "up": "+Y", "front": "+Z",
        "kind": asset.meta.get("kind", ""), "params": {k: round(v, 6) for k, v in asset.env.items()},
        "profile": asset.profile.get("name", ""), "style": asset.style.get("name", ""), "validation": validation_status,
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
