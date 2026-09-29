"""`sw import`: turn an external mesh file into an asset source.

Imported files usually lack semantics. The importer never guesses meaning; it
produces *addressable* structure (one part per node, optionally one per
connected piece) with neutral names, keeps the file as the geometry source,
and hands the naming step to the agent, which looks at a `parts`-mode render
and renames pieces (`piece_03` -> `left_armrest`). After that, the asset is
validated, inspected and exported like any native asset, and native parts
can be added next to the imported ones.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import numpy as np
import yaml

from . import backend
from .limits import LIMITS
from .ops.sources import ALLOWED


def _ident(name: str, used: set, fallback: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", name).strip("_").lower()
    if not s or not s[0].isalpha():
        s = fallback
    base, k = s, 2
    while s in used:
        s = f"{base}_{k}"
        k += 1
    used.add(s)
    return s


def import_file(src: Path, asset_dir: Path, name: str, split: bool = False, scale: float = 1.0, z_up: bool = False) -> dict:
    src = Path(src)
    if src.suffix.lower() not in ALLOWED:
        raise ValueError(f"unsupported file type '{src.suffix}' (allowed: {', '.join(sorted(ALLOWED))})")
    if src.stat().st_size > LIMITS.max_mesh_file_bytes:
        raise ValueError(f"{src.name} is larger than {LIMITS.max_mesh_file_bytes} bytes")
    if (asset_dir / "asset.yaml").exists():
        raise FileExistsError(f"{asset_dir / 'asset.yaml'} already exists")
    (asset_dir / "source").mkdir(parents=True, exist_ok=True)
    dest = asset_dir / "source" / src.name
    shutil.copy(src, dest)
    rel = f"source/{src.name}"
    nodes = backend.load_mesh_file(dest, LIMITS.max_triangles_total)
    file_mats, extensions = backend.load_file_materials(dest)
    materials, mat_of_node, mat_used, by_src = {}, {}, set(), {}
    for node, info in file_mats.items():  # one authored material per file material, shared by its nodes
        if info["name"] not in by_src:
            by_src[info["name"]] = _ident(info["name"], mat_used, "material")
            materials[by_src[info["name"]]] = _authored_material(info, by_src[info["name"]], asset_dir)
        mat_of_node[node] = by_src[info["name"]]
    used: set = set()
    parts, report, skipped = {}, [], []
    k = 0
    for node, mesh in nodes:
        if (re.match(r"^(UCX|UBX|UCP|USP|COL)_", node) or re.search(r"-(conv)?col(only)?$", node)
                or node.endswith("_collider")):
            skipped.append(node)  # engine collision proxies are not visible geometry
            continue
        pieces = backend.connected_components(mesh.merged()) if split else [None]
        for j, faces in enumerate(pieces):
            sub = mesh.merged().subset(faces) if faces is not None else mesh
            k += 1
            pname = _ident(f"{node}_{j + 1:02d}" if split and len(pieces) > 1 else node, used, f"piece_{k:02d}")
            V = sub.V.copy()
            if z_up:
                V = V[:, [0, 2, 1]] * np.array([1, 1, -1])
            V = V * scale
            center = (V.min(0) + V.max(0)) / 2
            shape = {"type": "mesh_file", "path": rel, "node": node}
            if faces is not None and len(pieces) > 1:
                shape["piece"] = j
            if scale != 1.0:
                shape["scale"] = scale
            if z_up:
                shape["z_up"] = True
            closed = backend.is_closed_manifold(sub.merged())
            parts[pname] = {
                "doc": f"imported from {rel} node '{node}'" + (f" piece {j}" if faces is not None and len(pieces) > 1 else "") + " (rename me)",
                "shape": shape,
                "position": [round(float(v), 5) for v in center],
                "material": mat_of_node.get(node, "imported"),
                "tags": ["imported"] + ([] if closed else ["open_ok"]),
            }
            report.append({"part": pname, "node": node, "triangles": int(sub.n_tris), "closed": bool(closed),
                           "size_m": [round(float(v), 4) for v in V.max(0) - V.min(0)], "material": mat_of_node.get(node, "imported")})
    doc = {
        "shapewright": 0.1,
        "asset": {"name": name, "kind": "imported", "description": f"Imported from {src.name}. Rename parts after inspecting `sw render {name} --mode parts`."},
        "profile": "desktop_indie",
        "materials": (materials | ({"imported": {"base_color": "#b0b0b0", "roughness": 0.8}}
                         if any(pp["material"] == "imported" for pp in parts.values()) else {})),
        "parts": parts,
    }
    header = (f"# Imported by `sw import {src.name}`. Geometry lives in {rel} (not parametric).\n"
              "# Next: sw render NAME --mode parts --view front_right; rename parts; add materials/sockets/checks;\n"
              "# native parts can be added alongside imported ones.\n")
    (asset_dir / "asset.yaml").write_text(header + yaml.safe_dump(doc, sort_keys=False, width=120))
    size = None
    if report:
        lo = np.min([np.array(p["position"]) - np.array(r["size_m"]) / 2 for p, r in zip(parts.values(), report)], 0)
        hi = np.max([np.array(p["position"]) + np.array(r["size_m"]) / 2 for p, r in zip(parts.values(), report)], 0)
        size = [round(float(v), 4) for v in hi - lo]
    hints = []
    if size and max(size) < 0.05:
        hints.append(f"the asset is only {max(size) * 100:.1f} cm across: if the file uses other units, re-import with --scale (e.g. 10 or 100)")
    elif size and max(size) > 10:  # FRESH_AGENT_07: a 25.7 m street lantern got no hint at the old 50 m threshold
        hints.append(f"the asset is {max(size):.1f} m across: if it is a prop, check its units and re-import with --scale "
                     f"(e.g. {2.5 / max(size):.3g} for a 2.5 m object, 0.01 if the file is in centimetres)")
    unsupported = [e for e in extensions if e not in ("KHR_materials_emissive_strength", "KHR_texture_transform")]
    if unsupported:
        hints.append(f"glTF extensions not imported (appearance may differ): {', '.join(unsupported)}")
    return {"asset": str(asset_dir / "asset.yaml"), "parts": report, "skipped_collision": skipped, "size_m": size,
            "materials": {k: sorted(m.get("textures", {})) for k, m in materials.items()}, "hints": hints}


def _linear_to_srgb_hex(c) -> str:
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in s[:3]) + (f"{int(round(c[3] * 255)):02x}" if len(c) > 3 and c[3] < 1 else "")


def _authored_material(info: dict, mname: str, asset_dir: Path) -> dict:
    """File material -> an `authored` material (docs/IMPORT.md); textures saved as PNG under source/textures."""
    tex_dir = asset_dir / "source" / "textures"
    textures = {}
    for ch, img in info["images"].items():
        tex_dir.mkdir(parents=True, exist_ok=True)
        im = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") and ch == "base_color" else "RGB")
        dest = tex_dir / f"{mname}_{ch}.png"
        im.save(dest, format="PNG")
        textures[ch] = f"source/textures/{dest.name}"
    m = {"archetype": "authored", "textures": textures, "color": _linear_to_srgb_hex(info["color"]),
         "roughness": round(info["roughness"], 4), "metallic": round(info["metallic"], 4),
         "doc": f"imported from the file's material '{info['name']}' (textures pass through unchanged)"}
    if info.get("emissive") and max(info["emissive"]) > 0:
        m["emissive"] = _linear_to_srgb_hex(info["emissive"])
    if info.get("alpha_mode", "OPAQUE") != "OPAQUE":
        m["alpha_mode"] = info["alpha_mode"]
    if info.get("double_sided"):
        m["double_sided"] = True
    return m
