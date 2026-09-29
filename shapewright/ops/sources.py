"""Non-parametric geometry sources.

`mesh_file` makes baked, imported or externally generated meshes first-class
geometry expressions. They take part in everything native geometry does
(transforms, ops, booleans when closed, semantic naming, materials, validation,
rendering, export, UV regions) but are not parametrically editable: their shape
is data in a file, and the source records where it came from.

Trust boundary: files are read, never executed. Paths must stay inside the
asset directory; only self-contained formats are accepted (no .gltf with
external URIs); size and triangle limits apply.
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

import numpy as np

from .. import backend
from ..limits import LIMITS
from ..mesh import concat, rotation_matrix, scale_matrix
from ..registry import Param, shape

ALLOWED = {".glb", ".obj", ".stl", ".ply"}


FILE_ROOTS: ContextVar[tuple] = ContextVar("FILE_ROOTS", default=())  # set by build(): base assets' folders


def within(root: Path, rel: str) -> Path | None:
    """rel resolved inside root, or None if it would escape it."""
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        return None
    full = (root / p).resolve()
    return full if root.resolve() in full.parents else None


def resolve_file(asset_dir: Path | None, rel: str, roots=None) -> Path:
    """A mesh file inside the asset's directory, or (for variants) inside a base asset's directory."""
    if asset_dir is None:
        raise ValueError("mesh_file needs an asset directory")
    if within(asset_dir, rel) is None:
        raise ValueError(f"path '{rel}' must be relative and stay inside the asset directory")
    for root in (asset_dir, *(FILE_ROOTS.get() if roots is None else roots)):
        full = within(Path(root), rel)
        if full is not None and full.exists():
            break
    else:
        raise ValueError(f"file not found: {rel}")
    if full.suffix.lower() not in ALLOWED:
        raise ValueError(f"unsupported file type '{full.suffix}' (allowed: {', '.join(sorted(ALLOWED))})")
    if full.stat().st_size > LIMITS.max_mesh_file_bytes:
        raise ValueError(f"{rel} is larger than {LIMITS.max_mesh_file_bytes} bytes")
    return full


@shape("mesh_file", "Baked / imported / externally generated mesh from a file inside the asset directory "
       "(GLB, OBJ, STL, PLY). Keeps authored UVs and vertex colours as attributes. Not parametric.",
       [Param("path", "str", doc="file path relative to the asset directory, e.g. source/rock.glb"),
        Param("node", "str", "", "node/mesh name inside the file ('' = all nodes merged)"),
        Param("piece", "int", -1, "connected component index within the node (-1 = all); `sw import --split` uses this"),
        Param("scale", "num|vec3", 1.0, "unit conversion, e.g. 0.01 for centimetre files"),
        Param("z_up", "bool", False, "true if the file is Z-up (converted to Y-up)"),
        Param("generated_by", "str", "", "provenance note: the command/tool that produced the file (recorded, never run)")],
       category="source", example="{type: mesh_file, path: source/example.obj}")
def mesh_file(a, b):
    full = resolve_file(b.asset_dir, a["path"])
    nodes = backend.load_mesh_file(full, LIMITS.max_triangles_per_part)
    if a["node"]:
        picked = [m for n, m in nodes if n == a["node"]]
        if not picked:
            raise ValueError(f"node '{a['node']}' not in {a['path']} (nodes: {', '.join(n for n, _ in nodes)[:200]})")
    else:
        picked = [m for _, m in nodes]
    if not picked:
        raise ValueError(f"{a['path']} contains no triangles")
    m = concat(picked)
    if a["piece"] >= 0:
        comps = backend.connected_components(m.merged())
        if a["piece"] >= len(comps):
            raise ValueError(f"piece {a['piece']} out of range ({len(comps)} pieces)")
        m = m.merged().subset(comps[a["piece"]])
    if a["z_up"]:
        m = m.transformed(rotation_matrix([-90, 0, 0]))
    m = m.transformed(scale_matrix(a["scale"])).merged()
    if backend.is_closed_manifold(m):
        m = m.oriented_outward()
    tag = f"file:{a['path']}" + (f"#{a['node']}" if a["node"] else "") + (f"[{a['piece']}]" if a["piece"] >= 0 else "")
    m.set_label("origin", tag)
    if not np.all(np.isfinite(m.V)):
        raise ValueError("file contains non-finite vertices")
    return m
