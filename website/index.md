# Shapewright

**3D game assets written like code, by AI agents, checked like code.**

An asset is a short YAML file of named parts, parameters and design checks. Shapewright builds the mesh, validates it in layers (geometry, assembly, seams, budgets, UVs, style), renders inspection sheets that an agent looks at, and exports a game-ready GLB for Godot, Unity, Unreal or the web.

It needs no GPU, no display and no Blender. The same command gives the same bytes on a laptop, in CI and in a cloud agent container.

<div class="sw-3d" data-src="gallery/models/house_cottage.glb" style="position:relative;overflow:hidden;height:420px;background:#ecebe7;border-radius:8px"><img src="gallery/img/house_cottage.png" alt="A cozy half-timbered cottage built from a 26-module kit" style="width:100%;height:100%;object-fit:contain"><button class="md-button" style="display:none">3D</button></div>

<script type="importmap">{"imports": {"three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.min.js", "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/"}}</script>
<script type="module">
import { createViewer } from "./gallery/viewer.js";
document.querySelectorAll(".sw-3d").forEach(box => {
  const v = createViewer(box, {background: 0xecebe7});
  v.load(box.dataset.src).then(() => box.querySelectorAll("img, button").forEach(e => e.remove())).catch(() => box.querySelector("canvas")?.remove());
});
</script>

*Built from a 26-module kit by an agent. Drag to orbit. The source of every piece is in the repository.*

## Why it exists

| Blender or a DCC tool driven by an AI | Shapewright |
|---|---|
| Imperative commands into a live scene | A declarative source file in git: diff it and review it |
| The result depends on the scene state | Deterministic: the same source gives the same mesh, image and GLB |
| The agent judges from screenshots | 8 validation layers with issue codes and fix hints, plus renders |
| One asset at a time | Packs, components and module assets: whole kits stay consistent |
| Needs a desktop | Headless: cloud, CI, containers |

Blender is still the better tool for sculpting, rigging and hero renders. Shapewright is for producing *sets* of game-ready assets that an agent can build, check and change reliably.

## Start

- **[Pick your setup](quickstart/index.md)**: Claude Code (cloud or local), MCP clients (Claude Desktop, Cursor, Codex), ChatGPT, or by hand.
- **[Make a prop in one session](use-cases/prop.md)**: the core loop in ten minutes.
- **[Build a modular kit](use-cases/modular-kit.md)**: modules, then buildings made of modules.
