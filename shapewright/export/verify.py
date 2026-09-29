"""Export-layer validation: Khronos glTF-Validator (if installed) and round-trip."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from ..assemble import ROOT, Asset
from ..report import Issue

VALIDATOR_DIR = ROOT / "tools" / "gltf-validator"


def khronos_validate(path: Path) -> tuple[list[Issue], dict]:
    node = shutil.which("node")
    script = VALIDATOR_DIR / "validate.mjs"
    if not node or not (VALIDATOR_DIR / "node_modules" / "gltf-validator").exists():
        return [Issue("EXP_VALIDATOR_UNAVAILABLE", "info", "Khronos glTF-Validator not installed; round-trip check only",
                      "", "export", "cd tools/gltf-validator && npm install")], {}
    try:
        res = subprocess.run([node, str(script), str(path)], capture_output=True, text=True, timeout=60)
        data = json.loads(res.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        return [Issue("EXP_VALIDATOR_FAILED", "warning", f"could not run glTF-Validator: {e}", "", "export")], {}
    issues = []
    for msg in data.get("messages", []):
        sev = {0: "error", 1: "warning"}.get(msg.get("severity"), None)
        if sev:
            issues.append(Issue("EXP_GLTF_" + msg.get("code", "UNKNOWN"), sev, msg.get("message", ""), msg.get("pointer", ""), "export"))
    return issues, {"gltf_validator": {k: data.get(k) for k in ("numErrors", "numWarnings", "numInfos", "numHints")}}


def roundtrip(asset: Asset, path: Path) -> list[Issue]:
    import trimesh

    scene = trimesh.load(str(path), force="scene")
    issues = []
    names = set(scene.graph.nodes_geometry)
    missing = [p.name for p in asset.parts if p.name not in names]
    if missing:
        issues.append(Issue("EXP_ROUNDTRIP_PARTS", "error", f"parts missing after re-import: {', '.join(missing[:6])}", "", "export"))
    tris = sum(len(scene.geometry[scene.graph[n][1]].faces) for n in names if not n.startswith(("UCX_",)) and not n.endswith("-colonly"))
    if tris != asset.n_tris:
        issues.append(Issue("EXP_ROUNDTRIP_TRIS", "error", f"re-imported {tris} triangles, expected {asset.n_tris}", "", "export"))
    geo_nodes = [n for n in names if n in {p.name for p in asset.parts}]
    if geo_nodes:
        bounds = np.stack([scene.geometry[scene.graph[n][1]].bounds + scene.graph[n][0][:3, 3] for n in geo_nodes])
        b = np.stack([bounds[:, 0].min(0), bounds[:, 1].max(0)])
        if not np.allclose(b, asset.bounds(), atol=1e-4):
            issues.append(Issue("EXP_ROUNDTRIP_BOUNDS", "error", "re-imported bounds differ from the model", "", "export"))
    return issues
