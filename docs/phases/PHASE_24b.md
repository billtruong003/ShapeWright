# Phase 24b: character review modes (track G, G3)

Branch `phase/22-organic` (stacked). Plan: docs/REMAINING_WORK.md §9 (G3).

**Verdict: PASS.** A person can review a character without leaving Shapewright: one CPU sheet, three new render
views, and a workbench 3D view with the skeleton, joint weights and clips. Agents get the same sheet from `review`.

## What shipped

| piece | where | notes |
|---|---|---|
| `sw render NAME --character` | `render/views.character_sheet` | look (3 views), reference, UV checker, UV layout, triangle density, weights of up to 3 key joints, two poses; tiles the asset cannot fill are left out |
| mode `density` | `render/views.py` | triangle edge length against the median (blue = dense, red = sparse), with a legend |
| mode `weights` + `--bone` | `render/views.py` | one joint's skinning weight, blue 0 to red 1; other parts grey |
| `--poses`, `--clip NAME` | (Phase 24) | the pose sheet and a looping GIF |
| `sw review` / MCP `review` | `cli.py`, `mcp_server.py` | rigged assets also write `character.png`; MCP returns it instead of the plain sheet |
| MCP `render` mode `density` | `mcp_server.py` | (`weights` needs a joint name: CLI only for now) |
| workbench 3D | `workbench/viewer.js`, `index.html` | skeleton overlay (three.js SkeletonHelper), "joint weights" view with a joint picker (from `skinIndex`/`skinWeight`), clip player with a pose slider (AnimationMixer) |
| docs site | `website/use-cases/characters.md` | a creature from items to a rigged export; its blocks run in the site tests |

Found on the way (BUG, Phase 25a regression): the colour legend of the `provenance` and `regions` modes was drawn
only together with `--scale-ref`. It had been indented into the scale figure's branch. Fixed; the new modes use the
same legend.

## Gates

| gate | measured | met |
|---|---|---|
| CPU sheet: UV checker + layout, density, weight heatmap per joint, pose sheet, concept beside the model | `phase24b/evidence/fox_character_sheet.png`; the reference tile appears when `reference:` is set (Phase 23 test) | yes |
| W viewer: skeleton overlay, weight heatmap per selected joint, pose slider | headless Chromium (Playwright): 19 joints and 3 clips listed, the overlay drawn, the leg weights coloured, the wave clip scrubbed to 30 % (`phase24b/evidence/workbench_skeleton_weights_wave.png`), no page errors | yes |
| MCP `review` returns the character sheet | `review` returns `character.png` when the CLI reports one; `tests/test_rig.py::test_cli_review_writes_the_character_sheet` | yes |

Tests: `tests/test_rig.py::test_review_modes_density_and_weights`, `test_cli_review_writes_the_character_sheet`;
the characters page in `tests/test_site_docs.py`.

## Not done

- **Per-pixel weights:** the CPU weights view colours per triangle (the mean of its corners); the workbench interpolates per vertex.
- **MCP `render` cannot show weights:** it has no joint argument yet.
