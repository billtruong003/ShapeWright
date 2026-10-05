# Release 1.0.0

Branch `release/1.0`, stacked on `phase/18b-site`. Plan: docs/REMAINING_WORK.md §7 (E1–E7).

**Verdict: PASS for the agent tasks; PyPI (E7) waits for the owner's token.** v1.0 bundles tracks A, B, R, W, C2 and
D (see the changelog) and was accepted by a fresh agent from the wheel alone.

## What shipped

| task | result |
|---|---|
| E1 version | package 1.0.0 (`pyproject.toml`, `shapewright.__version__`); the source format stays `shapewright: 0.1` (documented in ASSET_FORMAT.md: the format changes only with a migration) |
| E2 changelog | `CHANGELOG.md`, generated (Phase 18b) |
| E3 Docker | built and run: `init`, `brief`, `new --from barrel`, `export` (PASS, Khronos inside), `doctor`, MCP `initialize` over stdio; 1.11 GB. Closes Phase 16's open item |
| E4 Godot in CI | new `godot` job (Godot 4.3 headless, cached): imports barrel, cottage and fountain Godot exports; checks meshes, materials, textures, collision bodies, ground contact. Verified here with the same binary |
| E5 fresh-agent acceptance | FRESH_AGENT_12: PASS on a prop and a mini kit from the wheel + llms.txt; 8 framework findings fixed in this release |
| E6 tag and release | done: v1.0.0 published by `.github/workflows/release.yml` (on a version bump on `main`, a `v*` tag, or by hand): tests, a tag/version check, wheel, sdist, `modular_house_pack-vX.zip`, notes from the changelog. `docs/RELEASING.md` |
| E7 PyPI | **owner**: needs a PyPI token (`docs/RELEASING.md`); the documented install is the git URL until then |

## Gate

| gate | result |
|---|---|
| the tag exists, the release has assets | **met**: https://github.com/billtruong003/ShapeWright/releases/tag/v1.0.0 (wheel, sdist, `modular_house_pack-v1.0.0.zip`). The container's proxy refuses tag pushes and workflow dispatch, so `release.yml` now releases by itself when `main` carries an untagged version |
| the fresh agent succeeds on both requests | **met** |
| Docker is verified | **met** |
| CI green on the tag | checked by the release workflow (it runs the tests) and the ci workflow on `main` |
