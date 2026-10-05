"""Generate the docs site's derived pages and media, then (optionally) build it.

Usage: python tools/site/build_site.py [--build]

Writes (all git-ignored, regenerated in CI):
  website/reference/{vocabulary,codes,profiles}.md   from `sw caps --json` and profiles/
  website/gallery.md + website/gallery/models/*.glb + website/gallery/img/*.png
"""

from __future__ import annotations

import shutil
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


THREE_CDN = "https://cdn.jsdelivr.net/npm/three@0.169.0"  # the version vendored in shapewright/workbench/vendor
# a `.sw-3d` box holds a poster <img> and a button; the module swaps in the three.js viewer (auto: at load)
VIEWER_BOOT = (
    '<script type="importmap">{{"imports": {{"three": "' + THREE_CDN + '/build/three.module.min.js", '
    '"three/addons/": "' + THREE_CDN + '/examples/jsm/"}}}}</script>\n'
    '<script type="module">\n'
    'import {{ createViewer }} from "{viewer}";\n'
    'function open(box) {{\n'
    '  const v = createViewer(box, {{background: 0xecebe7}});\n'
    '  v.load(box.dataset.src).then(() => {{ box.querySelectorAll("img, button").forEach(e => e.remove()); }})\n'
    '   .catch(() => {{ box.querySelector("canvas")?.remove(); }});\n'
    '}}\n'
    'document.querySelectorAll(".sw-3d").forEach(box => {{\n'
    '  if ({auto}) open(box); else box.querySelector("button").onclick = () => open(box);\n'
    '}});\n'
    '</script>')


def gallery():
    from shapewright.assemble import build
    from shapewright.render.beauty import render_beauty
    from shapewright.surface import build_surface

    models, img = SITE / "gallery" / "models", SITE / "gallery" / "img"
    models.mkdir(parents=True, exist_ok=True)
    img.mkdir(parents=True, exist_ok=True)
    page = ["# Gallery", "", "Every asset below was written as source by an agent and exported by `sw export`. Press 3D to orbit the model; the "
            "source link opens its `asset.yaml`.", "", '<div class="grid" markdown>', ""]
    for name, caption in GALLERY:
        dst = models / f"{name}.glb"  # web viewers draw every mesh: the preview export has no collision proxies
        res = subprocess.run([sys.executable, "-m", "shapewright", "export", name, "--preview", "--out", str(dst)],
                             cwd=ROOT, capture_output=True, text=True)
        dst.with_suffix(".report.json").unlink(missing_ok=True)
        if not dst.exists():
            print(f"skip {name}: {res.stdout[-200:]}")
            continue
        a = build(ROOT / "assets" / name)
        render_beauty(a, build_surface(a), "front_right", 480).save(img / f"{name}.png")  # poster: presentation render
        # the page is served at /gallery/, next to gallery/models and gallery/img; the poster is what readers see until
        # they open the 3D view (and if WebGL or the CDN is unavailable)
        page += [f'<figure markdown><div class="sw-3d" data-src="models/{name}.glb" style="position:relative;overflow:hidden;height:300px;background:#ecebe7;border-radius:8px">'
                 f'<img src="img/{name}.png" alt="{caption}" style="width:100%;height:300px;object-fit:contain">'
                 '<button class="md-button" style="position:absolute;right:8px;bottom:8px;padding:2px 10px">3D</button></div>',
                 f'<figcaption>{caption}. <a href="https://github.com/billtruong003/ShapeWright/blob/main/assets/{name}/asset.yaml">source</a>'
                 '</figcaption></figure>', ""]
    page += ["</div>", "", VIEWER_BOOT.format(viewer="./viewer.js", auto="false"), ""]
    (SITE / "gallery.md").write_text("\n".join(page))
    # the workbench's viewer, so the site and the workbench show models the same way
    shutil.copy(ROOT / "shapewright" / "workbench" / "viewer.js", SITE / "gallery" / "viewer.js")


def main():
    reference()
    gallery()
    sys.path.insert(0, str(Path(__file__).parent))
    from changelog import changelog_markdown

    (SITE / "changelog.md").write_text(changelog_markdown(site=True))
    if "--build" in sys.argv:
        subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
