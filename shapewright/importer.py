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
    used: set = set()
    parts, report, skipped = {}, [], []
    k = 0
    for node, mesh in nodes:
        if re.match(r"^(UCX|UBX|UCP|USP)_", node) or node.endswith("-colonly") or node.endswith("-col"):
            skipped.append(node)  # engine collision proxies are not visible geometry
            continue
        pieces = backend.connected_components(mesh.merged()) if split else [None]
        for j, faces in enumerate(pieces):
            sub = mesh.merged().subset(faces) if faces is not None else mesh
            k += 1
            pname = _ident(f"piece_{k:02d}" if split and len(pieces) > 1 else node, used, f"piece_{k:02d}")
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
                "material": "imported",
                "tags": ["imported"] + ([] if closed else ["open_ok"]),
            }
            report.append({"part": pname, "node": node, "triangles": int(sub.n_tris), "closed": bool(closed)})
    doc = {
        "shapewright": 0.1,
        "asset": {"name": name, "kind": "imported", "description": f"Imported from {src.name}. Rename parts after inspecting `sw render {name} --mode parts`."},
        "profile": "desktop_indie",
        "materials": {"imported": {"base_color": "#b0b0b0", "roughness": 0.8}},
        "parts": parts,
    }
    header = (f"# Imported by `sw import {src.name}`. Geometry lives in {rel} (not parametric).\n"
              "# Next: sw render NAME --mode parts --view front_right; rename parts; add materials/sockets/checks;\n"
              "# native parts can be added alongside imported ones.\n")
    (asset_dir / "asset.yaml").write_text(header + yaml.safe_dump(doc, sort_keys=False, width=120))
    return {"asset": str(asset_dir / "asset.yaml"), "parts": report, "skipped_collision": skipped}
