# Phase 15b: web workbench with a three.js 3D view (track W)

Branch `phase/15b-web-viewer`, stacked on `phase/25a-render`. Plan: docs/REMAINING_WORK.md §6c (W1–W6).

**Verdict: PASS with exceptions.** Everything shipped and was driven in a real browser (headless Chromium, WebGL
through SwiftShader). Not verified: Windows, Edge and Firefox (no such browsers here).

## What shipped

| task | result |
|---|---|
| W1 3D view | three.js r169 vendored (`shapewright/workbench/vendor/three`, MIT, ~880 KB, in the wheel), `workbench/viewer.js` (shared module): glTF of `sw export ASSET --preview --target generic`, orbit, studio environment, soft shadow on the ground, 1 m grid, 1.75 m figure, frame button |
| W2 view modes | textured, clay, material colours, colour by part, normals, UV checker, texel density (relative to the median px/m), wireframe overlay, UV layout of the picked part (zoomed to its charts) or of all parts |
| W3 model list | thumbnail grid (newest beauty/textured render or the sheet), status, triangles, build time, search, status filter |
| W4 edit/save/export | Preview/Apply rebuild and reload the 3D view (`export --preview --set` works now: `export` takes `--set`); save source (as before); export + a download link; Screenshot → `.build/shots/` |
| W5 notes for the agent | click → part, point, normal; *Pin note* saves a marked screenshot and runs `sw feedback ASSET add ...`; new `sw feedback ASSET [add|resolve]` (`shapewright/feedback.py`), MCP tools `feedback` (text + screenshots) and `resolve_feedback` (18 tools) |
| W6 docs gallery | the site uses the same `viewer.js` (three.js from jsDelivr, same version); posters are beauty renders, a 3D button opens the viewer; the home page hero loads it directly; `<model-viewer>` is gone |

## Evidence

- `phase15b/evidence/workbench_note_pinned.png`: the treasure chest in the 3D view with wireframe, figure and UV
  layout on, a picked point and a pinned note (also `docs/images/workbench.png`)
- `view_modes.png` (clay, parts, UV checker, texel, normals), `uv_layout_part.png`, `note_screenshot.png` (what the
  agent receives), `site_gallery_3d.png` (the docs gallery with the cottage opened in 3D)

**One recorded round** (a note reaching the agent and being fixed): in the browser the note "the lock plate should be
2 cm wider" was pinned on the chest. `sw feedback` (and the MCP tool `feedback`, tested) returned it with the part, the
point and the screenshot; the agent ran `sw set treasure_chest lp_w=0.19`, validated (WARN as before, texel only) and
resolved the note with a reply, which the page shows. The click landed on `lid_rim_front` just above the plate: the
agent acted on the text and the screenshot, not on the part name alone. That is why notes carry all three.

## Gate

| gate | result |
|---|---|
| opens a library and a project asset in 3D on Linux and Windows (Chrome/Edge/Firefox) | **met with exceptions**: Linux + Chromium (workbench and site); Windows, Edge and Firefox not verified |
| every view mode works on the cottage and the treasure chest | **met with exceptions**: all modes on the chest (screenshots) and in the browser test on the crate; the cottage was shown in 3D (textured) on the site, not cycled through every mode |
| a comment reaches an agent through MCP and the agent fixes it | **met** (round above; `test_feedback_round_trip_cli_and_mcp`, `test_browser_3d_view_and_pinned_note`) |
| the wheel installs offline and serves the viewer | **met**: the wheel contains viewer.js and the vendored three.js (`test_packaging`); no CDN in the workbench |
| deterministic tests unchanged | **met** (no golden or render change) |

## Framework changes

- `sw feedback` + `feedback.py` + 2 MCP tools (CAPABILITY GAP: a person could not point at a problem; they had to
  describe it in words).
- `sw export --set` (ERGONOMICS: the 3D preview of unapplied slider values; `export` was the one build command without it).
