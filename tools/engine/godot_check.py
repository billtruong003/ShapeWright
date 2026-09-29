"""Import exported GLBs into a real game engine (Godot 4, headless) and report what the engine sees.

Usage:
    SW_GODOT=/path/to/Godot_v4.x_linux.x86_64 python tools/engine/godot_check.py FILE.glb [FILE.glb ...] [--json]

Godot is optional and not a dependency. It is the one engine that runs headless in a container,
so it is the Phase 12 evidence that exports enter a normal pipeline. Per file it reports import
errors, node/mesh/surface counts (surfaces ~ draw calls), materials and whether their textures
resolved, physics bodies created from collision naming, the scene's size and lowest point, and
empty marker nodes (sockets).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = r'''
extends SceneTree
var report = {"nodes": 0, "meshes": 0, "surfaces": 0, "materials": {}, "bodies": 0, "shapes": [], "markers": [], "names": []}
var aabb = null
func walk(n, xf):
	report["nodes"] += 1
	report["names"].append(str(n.name))
	var t = xf
	if n is Node3D:
		t = xf * n.transform
	if n is MeshInstance3D and n.mesh:
		report["meshes"] += 1
		report["surfaces"] += n.mesh.get_surface_count()
		var box = t * n.get_aabb()
		aabb = box if aabb == null else aabb.merge(box)
		for i in n.mesh.get_surface_count():
			var m = n.mesh.surface_get_material(i)
			if m is BaseMaterial3D:
				report["materials"][m.resource_name] = {"albedo_texture": m.albedo_texture != null,
					"orm_texture": m.roughness_texture != null or m.metallic_texture != null,
					"normal_texture": m.normal_enabled and m.normal_texture != null,
					"emission": m.emission_enabled, "transparency": m.transparency}
	if n is StaticBody3D or n is RigidBody3D or n is Area3D:
		report["bodies"] += 1
	if n is CollisionShape3D and n.shape:
		report["shapes"].append(n.shape.get_class())
	if n.get_class() == "Node3D" and n.get_child_count() == 0:
		report["markers"].append(str(n.name))
	for c in n.get_children():
		walk(c, t)
func _init():
	var scene = load("res://" + OS.get_cmdline_user_args()[0])
	if scene == null:
		print("SWCHECK " + JSON.stringify({"error": "import failed"}))
		quit(1)
		return
	walk(scene.instantiate(), Transform3D())
	if aabb != null:
		report["size"] = [aabb.size.x, aabb.size.y, aabb.size.z]
		report["min_y"] = aabb.position.y
		report["center_xz"] = [aabb.get_center().x, aabb.get_center().z]
	print("SWCHECK " + JSON.stringify(report))
	quit(0)
'''


def check(files: list[Path], godot: str) -> dict:
    out = {}
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "project.godot").write_text('config_version=5\n[application]\nconfig/name="swcheck"\n')
        (proj / "check.gd").write_text(SCRIPT)
        names = []
        for f in files:
            name = f"{f.parent.parent.name}__{f.name}" if f.parent.name == "export" else f.name
            shutil.copy(f, proj / name)
            names.append((f, name))
        imp = subprocess.run([godot, "--headless", "--path", str(proj), "--import"], capture_output=True, text=True, timeout=900)
        log = imp.stdout + imp.stderr
        for f, name in names:
            r = subprocess.run([godot, "--headless", "--path", str(proj), "--script", "check.gd", "--", name],
                               capture_output=True, text=True, timeout=300)
            line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SWCHECK ")), None)
            rep = json.loads(line[8:]) if line else {"error": (r.stderr or r.stdout)[-400:]}
            rep["import_errors"] = [ln.strip() for ln in log.splitlines() if name in ln and ("ERROR" in ln or "WARNING" in ln)][:5]
            out[str(f)] = rep
    return out


def main(argv):
    godot = os.environ.get("SW_GODOT") or shutil.which("godot") or shutil.which("godot4")
    files = [Path(a) for a in argv if not a.startswith("--")]
    if not godot or not files:
        print(__doc__)
        return 2
    res = check(files, godot)
    if "--json" in argv:
        print(json.dumps(res, indent=1))
        return 0
    for f, r in res.items():
        if "error" in r:
            print(f"FAIL {f}: {r['error']}")
            continue
        mats = r["materials"]
        tex = sum(1 for m in mats.values() if m["albedo_texture"])
        print(f"{Path(f).name:32s} nodes {r['nodes']:4d} meshes {r['meshes']:4d} surfaces {r['surfaces']:4d} "
              f"materials {len(mats)} (textured {tex}) bodies {r['bodies']} markers {len(r['markers'])} "
              f"size {[round(v, 3) for v in r.get('size', [])]} min_y {round(r.get('min_y', 0), 4)} "
              f"{'IMPORT ISSUES ' + str(r['import_errors']) if r['import_errors'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
