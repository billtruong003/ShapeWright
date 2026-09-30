---
name: shapewright
description: Model, validate, render and export game-ready 3D assets (props, modular kits, asset packs) with Shapewright. Use when the user asks to create, modify, review, import or export a 3D asset, GLB, prop, kit piece or asset pack, or mentions Shapewright, `sw`, asset.yaml, packs or components.
---

# Shapewright

You edit declarative asset sources (`assets/NAME/asset.yaml`); the `sw` CLI (or `./sw` in a clone) builds,
validates, renders and exports them. The full manual is `AGENTS.md`; the one-page brief is `llms.txt`
(`sw caps --llms`).

## Loop

1. `sw brief "<request>"` first. It returns the closest example asset with its full source, the profile and
   budget, the rules for that kind of prop and the vocabulary. Usually no other reading is needed.
2. `sw new NAME [--from EXAMPLE]`, then write the source: named parts, params with min/max, `checks:`.
3. `sw review NAME`, then **Read `assets/NAME/.build/sheet.png`** and critique it specifically
   (`part.param -> change, reason`). Zoom with `sw render NAME --part P --view front`.
4. Fix errors by their code (`sw doc CODE`). Change params first, then placement, then ops.
5. `sw snapshot NAME -m "..." --critique "..."` after each meaningful step; `sw compare NAME 1 current`.
6. Stop when there are no errors, no significant critique left and the constraints hold (default max 6
   revisions). `sw export NAME [--target godot|unity|unreal]` and report tris vs budget, size, materials, path.

## Sets and kits

- Several assets sharing scale and materials: `packs/NAME.yaml` + `pack: NAME` in each; review with
  `sw pack --pack NAME`.
- Repeated sub-assemblies: `components/NAME.yaml` + `component: NAME` on a part, with `origin: keep` when
  the component's own origin is its pivot.
- Variants of one design: `extends:` + `sw family NAME`.

## Don'ts

- Don't hand-compute another part's position: use `anchor`/`attach` or `measure:` queries.
- Don't tag a floating part `floating_ok` to silence `ASM_FLOATING_PARTS`; fix its placement.
- Don't commit `.build/`. Do commit `asset.yaml`, `uv.lock.yaml`, `history/`.
- In the Shapewright repository itself, framework changes need a regression test
  (`python3 -m pytest -q`) and a new asset needs `python3 tests/update_golden.py`.
