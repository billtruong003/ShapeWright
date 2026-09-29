"""Phase 10 scaling benchmark: time every pipeline stage at 1k..50k triangles.

Usage:
    python tools/perf/scaling.py [--sizes 1000,5000,10000,25000,50000] [--dense] [--out docs/perf/scaling.json]

--dense: one single part (noised sphere with a boolean and a trim) instead of many small parts.

A synthetic but representative mid-poly asset (booleans, lathe, helix tube, spheres, arrays,
two textured materials) is generated at each target size; each size runs in a fresh process
so peak memory (ru_maxrss) is per size. Stages: build, UV (surface), validate, bake, render
(one 512px view), sheet (review contact sheet), export (GLB), verify (Khronos + re-import),
import (sw import of the exported GLB). Numbers are measurements on this machine only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TEMPLATE = """\
asset: {{name: scale_{n}}}
profile: desktop_indie
budget: {{triangles: 200000, texture_size: 1024}}
uv: {{texel_density: 128}}
params:
  s: {s}
  k: {k}
materials:
  steel: {{archetype: metal, color: "#9aa0a8", edge_wear: 0.4}}
  oak: {{archetype: wood, color: "#8a5a36", edge_wear: 0.3}}
parts:
  base:
    shape: {{type: chamfer_box, size: [0.4 * k + 0.4, 0.1, 0.8], chamfer: 0.01}}
    anchor: bottom
    material: oak
  plate:
    shape:
      type: chamfer_box
      size: [0.3, 0.04, 0.3]
      chamfer: 0.005
      ops: [{{type: subtract, shape: {{type: cylinder, radius: 0.08, height: 0.1, segments: s}}}}]
    anchor: bottom
    position: [-0.2 * k + 0.2, 0.1, -0.2]
    material: steel
    array: {{count: k, offset: [0.4, 0, 0]}}
  column:
    shape: {{type: lathe, segments: s, profile: [[0.06, 0], [0.08, 0.05], [0.05, 0.1], [0.05, 0.5], [0.07, 0.55], [0.0, 0.6]]}}
    anchor: bottom
    position: [-0.2 * k + 0.2, 0.1, 0.2]
    material: steel
    array: {{count: k, offset: [0.4, 0, 0]}}
  knob:
    shape: {{type: sphere, radius: 0.07, segments: s, rings: "max(4, s // 2)"}}
    anchor: bottom
    position: [-0.2 * k + 0.32, 0.13, -0.2]
    material: oak
    array: {{count: k, offset: [0.4, 0, 0]}}
  coil:
    shape: {{type: tube, radius: 0.012, sides: "max(4, s // 3)", path: [{{helix: {{radius: 0.07, pitch: 0.05, turns: 4, axis: y, segments_per_turn: "max(6, s // 2)"}}}}]}}
    anchor: bottom
    position: [-0.2 * k + 0.2, 0.1, 0.2]
    material: oak
    array: {{count: k, offset: [0.4, 0, 0]}}
"""

DENSE = """\
asset: {{name: dense_{n}}}
profile: desktop_indie
budget: {{triangles: 200000, texture_size: 1024}}
uv: {{texel_density: 128}}
params:
  s: {s}
  k: {k}
materials:
  stone: {{archetype: stone, color: "#8b8f94", edge_wear: 0.3}}
parts:
  boulder:
    shape:
      type: sphere
      radius: 0.5
      segments: s
      rings: "s // 2"
      ops:
        - {{type: noise, amount: 0.04, frequency: 3, seed: 2}}
        - {{type: subtract, shape: {{type: cylinder, radius: 0.15, height: 1.2, segments: 24}}}}
        - {{type: flat_bottom, fraction: 0.1}}
    anchor: bottom
    material: stone
"""

STAGES_SCRIPT = r"""
import json, resource, sys, time, tempfile, shutil
from pathlib import Path
sys.path.insert(0, sys.argv[1])
asset_dir = Path(sys.argv[2])
t = {}
def stage(name, fn):
    t0 = time.perf_counter(); r = fn(); t[name] = round(time.perf_counter() - t0, 3); return r
from shapewright.assemble import build
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation
from shapewright.bake import textures_for
from shapewright.render.views import render, contact_sheet
from shapewright.export.gltf import write_glb
from shapewright.export.verify import khronos_validate, roundtrip
from shapewright.importer import import_file
a = stage("build", lambda: build(asset_dir))
s = stage("uv", lambda: build_surface(a))
rep = stage("validate", lambda: run_validation(a, s))  # includes the texture bake (surface_textures validator)
stage("bake_cached", lambda: textures_for(a, s))
stage("render_512", lambda: render(a, s, "front_right", "clay", 512))
stage("render_textured_512", lambda: render(a, s, "front_right", "textured", 512))
stage("sheet", lambda: contact_sheet(a, s, tile=384))
out = asset_dir / "x.glb"
stage("export", lambda: write_glb(a, s, out, rep["status"]))
kh = stage("khronos", lambda: khronos_validate(out))
stage("roundtrip", lambda: roundtrip(a, out))
tmp = Path(tempfile.mkdtemp())
stage("import", lambda: import_file(out, tmp / "imp", "imp"))
stage("import_build", lambda: build(tmp / "imp"))
shutil.rmtree(tmp)
tris = sum(len(p.mesh.F) for p in a.parts)
print(json.dumps({"tris": tris, "parts": len(a.parts), "status": rep["status"], "seconds": t,
                  "khronos": kh[1].get("gltf_validator"), "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                  "glb_kb": round(out.stat().st_size / 1024, 1)}))
"""


def tris_for(s: int, k: int, template: str) -> int:
    from shapewright.assemble import build  # noqa: E402

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "asset.yaml"
        p.write_text(template.format(n=0, s=s, k=k))
        return sum(len(x.mesh.F) for x in build(p).parts)


def choose(target: int, template: str) -> tuple[int, int]:
    """Pick (segments, modules) whose triangle count is closest to target."""
    best = None
    for k in ((1,) if template is DENSE else (1, 2, 4, 6, 8, 12, 16)):
        for s in range(6, 257, 2):
            n = tris_for(s, k, template)
            if best is None or abs(n - target) < abs(best[2] - target):
                best = (s, k, n)
            if n > target * 1.3:
                break
    return best[0], best[1]


def main(argv):
    sys.path.insert(0, str(ROOT))
    sizes = [1000, 5000, 10000, 25000, 50000]
    out = None
    template = DENSE if "--dense" in argv else TEMPLATE
    for i, a in enumerate(argv):
        if a == "--sizes":
            sizes = [int(x) for x in argv[i + 1].split(",")]
        if a == "--out":
            out = Path(argv[i + 1])
    results = []
    for target in sizes:
        s, k = choose(target, template)
        with tempfile.TemporaryDirectory() as d:
            ad = Path(d) / f"scale_{target}"
            ad.mkdir()
            (ad / "asset.yaml").write_text(template.format(n=target, s=s, k=k))
            r = subprocess.run([sys.executable, "-c", STAGES_SCRIPT, str(ROOT), str(ad)], capture_output=True, text=True,
                               cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)})
            if r.returncode:
                print(r.stderr[-2000:], file=sys.stderr)
                results.append({"target": target, "error": r.stderr[-500:]})
                continue
            res = {"target": target, "segments": s, "modules": k, **json.loads(r.stdout.strip().splitlines()[-1])}
            results.append(res)
            print(json.dumps(res))
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
