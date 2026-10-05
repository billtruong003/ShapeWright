# Phase 18b: docs site completion (track D)

Branch `phase/18b-site`, stacked on `phase/17b-mcp-verify`. Plan: docs/REMAINING_WORK.md §6 (D1–D7).

**Verdict: PASS.** It also closes Phase 18's untested gate ("a reader reproduces the published GLB").

## What shipped

| task | result |
|---|---|
| D1 composition tutorial | `website/use-cases/composition.md`: a component, a component made of components, an asset using it with `measure:` and `pivot:`, an asset made of assets with `with:` and inherited sockets. Every block runs in the doc tests. Writing it found a validator doing its job: a sign hung 4 cm under its arm is `ASM_FLOATING_PARTS`, so the tutorial adds iron straps and says why |
| D2 seams page | `website/concepts/seams.md`: the three codes, what is not reported and why, a runnable before/after (a plinth flush with its wall → 5 mm proud), the three recipes from track A, the park bench before/after |
| D3 changelog | `tools/site/changelog.py` generates `CHANGELOG.md` (root) and `website/changelog.md` (site nav) from the phase-plan status table and each record's verdict; a test checks `CHANGELOG.md` is current |
| D4 Windows notes | admonitions in the local, CLI and MCP quickstarts (`sw.cmd`, venv activation, the desktop-app config with `python.exe -m shapewright` and escaped paths). Also fixed: the MCP pages said `pip install "shapewright[mcp]"`, which needs PyPI; they now use the git URL like the README |
| D5 README badges | CI, docs, platforms, licence; changelog link |
| D6 reproducibility | `test_a_reader_reproduces_the_tutorial_glb`: the prop tutorial's mailbox exports to identical bytes in two fresh projects |
| D7 beauty renders in the docs | done in track R (gallery posters, README images, the presentation page) |

**Bug found and fixed:** the seam message's `near (x, y, z)` was the first overlap sample, which could be a hidden
one (on the ground), so it pointed at the floor. It now names the first *visible* spot
(`test_the_reported_spot_is_a_visible_one`).

## Gate

| gate | result |
|---|---|
| `mkdocs build --strict` passes | **met** |
| doc tests pass (every `# run` block) | **met** |
| docs workflow green | **not verified here**: runs when this reaches `main` |
| new pages linked from the nav and the README | **met** (nav: composition, presentation, seams, changelog; README: changelog) |
| a reader reproduces the tutorial GLB | **met** for two fresh projects on one machine; across machines the geometry is covered by the per-platform golden hashes, and the GLB embeds the package version, so a committed byte hash would change with every release (not added) |
