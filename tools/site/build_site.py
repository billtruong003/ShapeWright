"""Generate the docs site's derived pages and media, then (optionally) build it.

Usage: python tools/site/build_site.py [--build]

Writes (all git-ignored, regenerated in CI):
  website/reference/{vocabulary,codes,profiles}.md   from `sw caps --json` and profiles/
  website/gallery.md + website/gallery/models/*.glb + website/gallery/img/*.png
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SITE = ROOT / "website"
GALLERY = [  # (asset, caption); houses come from the modular_house_pack bundle
    ("house_cottage", "Cottage built from the cozy_house kit (26 modules)"),
    ("house_townhouse", "Townhouse from the same kit: gable to the street, shopfront"),
    ("house_workshop", "Workshop-tavern: a 2-storey block and a wing sharing a grid line"),
    ("tavern_chair", "Tavern chair: the first critique loop (2 iterations)"),
    ("treasure_chest", "Treasure chest: a fresh agent's textured asset (FA-04)"),
    ("ornate_fountain", "Ornate fountain: 44k-triangle mid-poly stress test (FA-06)"),
    ("well_winch", "Well winch: gears, rope and a crank"),
    ("iron_lantern", "Iron lantern: hex frame, glass, candle"),
    ("rope_bridge", "Rope bridge: arrays and measured sag"),
    ("smith_workbench", "Blacksmith pack: shared scale and palette"),
    ("battle_axe", "Battle axe"),
    ("mine_cart", "Mine cart"),
]


def reference():
    from shapewright.caps import manifest

    m = manifest()
    (SITE / "reference").mkdir(exist_ok=True)
    out = ["# Shapes and ops", "", "*Generated from `sw caps --json`. `sw doc NAME` prints the same entries.*", ""]
    for fam, title in (("shapes", "Shapes"), ("ops", "Ops"), ("material_archetypes", "Material archetypes"),
                       ("part_features", "Part features"), ("point_generators", "Point generators")):
        out += [f"## {title}", "", "| name | what | example |", "|---|---|---|"]
        for k, v in m[fam].items():
            doc = (v.get("doc", "") if isinstance(v, dict) else str(v)).replace("|", "\\|")
            ex = (v.get("example", "") if isinstance(v, dict) else "").replace("|", "\\|")
            out.append(f"| `{k}` | {doc} | {f'`{ex}`' if ex else ''} |")
        out.append("")
    (SITE / "reference" / "vocabulary.md").write_text("\n".join(out))
    codes = ["# Issue codes", "", "*Generated from the validator registry. Meanings and fixes: "
             "[VALIDATION.md](https://github.com/billtruong003/ShapeWright/blob/main/docs/VALIDATION.md).*", "",
             "| layer | validator | what it checks | codes |", "|---|---|---|---|"]
    for v in m["validators"]:
        codes.append(f"| {v['layer']} | `{v['name']}` | {v['doc']} | {' '.join(f'`{c}`' for c in v['codes'])} |")
    (SITE / "reference" / "codes.md").write_text("\n".join(codes) + "\n")
    import yaml

    from shapewright import paths

    prof = ["# Profiles", "", "| profile | triangles | materials | texture | texel px/m | for |", "|---|---|---|---|---|---|"]
    for f in paths.files("profiles"):
        d = yaml.safe_load(f.read_text()) or {}
        b = d.get("budget") or {}
        prof.append(f"| `{f.stem}` | {b.get('triangles', '')} | {b.get('materials', '')} | {b.get('texture_size', '')} | "
                    f"{b.get('texel_density', '')} | {d.get('doc', '')} |")
    (SITE / "reference" / "profiles.md").write_text("\n".join(prof) + "\n")


def _strip_collision(src: Path, dst: Path):
    """Web viewers draw every mesh; engines hide collision proxies by name. Drop COL_/UCX_/-colonly nodes from the scene."""
    import struct

    data = src.read_bytes()
    jlen = struct.unpack("<I", data[12:16])[0]
    doc = json.loads(data[20:20 + jlen])
    bad = {i for i, n in enumerate(doc.get("nodes", [])) if str(n.get("name", "")).startswith(("COL_", "UCX_"))
           or str(n.get("name", "")).endswith(("-colonly", "-convcolonly"))}
    for holder in doc.get("scenes", []) + doc.get("nodes", []):
        key = "nodes" if "nodes" in holder else "children"
        if key in holder:
            holder[key] = [c for c in holder[key] if c not in bad]
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    rest = data[20 + jlen:]
    total = 12 + 8 + len(js) + len(rest)
    dst.write_bytes(data[:8] + struct.pack("<I", total) + struct.pack("<I", len(js)) + b"JSON" + js + rest)


def gallery():
    from shapewright.assemble import build
    from shapewright.render.views import render
    from shapewright.surface import build_surface

    models, img = SITE / "gallery" / "models", SITE / "gallery" / "img"
    models.mkdir(parents=True, exist_ok=True)
    img.mkdir(parents=True, exist_ok=True)
    page = ["# Gallery", "", "Every asset below was written as source by an agent and exported by `sw export`. Drag to orbit; the "
            "source link opens its `asset.yaml`.", "", '<div class="grid" markdown>', ""]
    for name, caption in GALLERY:
        glb = ROOT / "assets" / name / "export" / f"{name}.glb"
        bundled = ROOT / "modular_house_pack" / "demo_houses" / f"{name}.glb"
        src = glb if glb.exists() else bundled if bundled.exists() else None
        if src is None:
            res = subprocess.run([sys.executable, "-m", "shapewright", "export", name], cwd=ROOT, capture_output=True, text=True)
            src = glb if glb.exists() else None
            if src is None:
                print(f"skip {name}: {res.stdout[-200:]}")
                continue
        _strip_collision(src, models / f"{name}.glb")
        a = build(ROOT / "assets" / name)
        render(a, build_surface(a), "front_right", "textured", 480).save(img / f"{name}.png")
        # the page is served at /gallery/, next to gallery/models and gallery/img; the <img> in the poster slot is also
        # what readers see when the model-viewer script cannot load
        page += [f'<figure markdown><model-viewer src="models/{name}.glb" camera-controls '
                 f'style="width:100%;height:300px;background:#ecebe7;border-radius:8px" alt="{caption}">'
                 f'<img slot="poster" src="img/{name}.png" alt="{caption}" style="width:100%;height:300px;object-fit:contain"></model-viewer>',
                 f'<figcaption>{caption}. <a href="https://github.com/billtruong003/ShapeWright/blob/main/assets/{name}/asset.yaml">source</a>'
                 '</figcaption></figure>', ""]
    page += ["</div>", ""]
    (SITE / "gallery.md").write_text("\n".join(page))


def main():
    reference()
    gallery()
    if "--build" in sys.argv:
        subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
