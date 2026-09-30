# Phase 18: docs site and gallery

**Verdict: PARTIAL.**
- **Built and checked:** the site builds in strict mode. Every runnable tutorial block passes as a test, and the gallery renders the real models (checked in headless Chromium).
- **Not verified:** deployment. `.github/workflows/docs.yml` is written but has not run; it needs GitHub Pages enabled on the repository.
- **Not tested end to end:** the gate's "a reader reproduces the published GLB byte-identically". Determinism of the export is covered by the existing golden tests, not by a site test.

Branch `phase/18-docs-site`, stacked on `phase/20-seams`. It is not merged.

## What shipped

- **`mkdocs.yml` + `website/`** (MkDocs Material, pinned below 2.0):
  - **home**, with a live `<model-viewer>` of the cottage;
  - **quickstarts:** Claude Code cloud, Claude Code local, MCP clients (Claude Desktop, Cursor, Codex), ChatGPT/chat, by hand;
  - **six use cases:** prop in one session (the FA-11 mailbox), modular kit (a shed built from module assets), variants, import and repair, budgets (VR/mobile/web), CI;
  - **concepts:** the loop, validation layers, composition;
  - **generated reference:** vocabulary, issue codes, profiles.
- **`tools/site/build_site.py`:**
  - writes the reference pages from `sw caps --json` and `profiles/`;
  - builds the gallery: 12 assets, each a model-viewer with a rendered poster fallback;
  - strips collision-proxy nodes from gallery GLBs, because web viewers draw them as grey boxes while engines hide them by name;
  - with `--build`, also runs `mkdocs build --strict`.
- **`tests/test_site_docs.py`:**
  - every `# run` bash block in `website/` runs in a fresh project;
  - `# file:` and `# append:` YAML blocks are written first;
  - `# expect-fail` lines must fail;
  - status: 5 pages, all passing.
- **CI (written, not yet run):**
  - `.github/workflows/ci.yml`: ruff + pytest;
  - `.github/workflows/docs.yml`: doc tests, generator, strict build, deploy to Pages.
- **Framework fix found by the doc tests:** `--set` on a variant rejected params inherited from its base or pack.
  - Class: BUG. Cause: it read only the variant file's own `params:`.
  - It now checks the merged params. `cli._load` was changed; covered by `use-cases/budgets.md` and `variants.md`.

- **Second framework fix found by the doc tests:** `sw variants` wrote the generated variants next to the base asset, i.e. into the *library* (site-packages when installed).
  - Class: BUG.
  - Variants now go to the project's `assets/`, with a relative `extends` path.

## Findings recorded while writing the tutorials

- **`tavern_chair` param range is inconsistent with its check.** `seat_height` has min 0.40, but its check requires ≥ 0.42, so `--set seat_height=0.40` fails. The tutorial uses 0.43; the asset is not changed.
- **`sw set` edits only params written in that file.** On a variant, inherited params must be added under `params:` by hand. The message says so. Auto-inserting them is a possible ergonomics item.
- **Generic GLBs include collision-proxy meshes (`COL_…`).** Correct for engines, but a plain glTF viewer shows them. The gallery strips them; an export option for "web/preview" GLBs would be the general fix.

## Evidence

- `mkdocs build --strict`: 0 warnings, 0.5 s.
- `tests/test_site_docs.py`: 5 passed (about 25 s). Full suite: 427 passed, 2 skipped.
- Screenshots: `phase18/evidence/site_home.png` (live model), `site_gallery.png`.

## Gate

| gate item | result |
|---|---|
| site builds in CI | **met locally** (strict); the CI workflow is written and not yet run |
| every code block in tutorials runs in CI | **met for runnable blocks**; illustrative blocks (client config JSON/TOML, GitHub Actions YAML, import of *your* file) are intentionally not run and are marked as such |
| every gallery item links to its source | **met** |
| a reader reproduces a published GLB byte-identically | **not tested end to end** |
