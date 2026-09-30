# Phase 16: packaging + AI docs

**Verdict: PASS**, with one item not verified: the Docker image was not built, because this environment has no Docker.

Branch `phase/16-packaging`, stacked on `test/modular-house-pack`. It is not merged.

## Goal

Make Shapewright installable and learnable without cloning the repository. An agent that has only `pip install` and a one-page brief should get from a request to an exported asset.

## What shipped

| change | class | why it is generic |
|---|---|---|
| `shapewright/paths.py`: library root vs project root (`$SW_PROJECT` → nearest `shapewright.yaml` → cwd with `assets/`); project files shadow library files | ABSTRACTION GAP | Every lookup of profiles, styles, packs, components and assets assumed the repository root. An installed package had no place for user files. |
| `setup.py` build hook: the wheel ships `shapewright/_lib` (profiles, styles, packs, components, templates, example asset sources). Build products (export/, .build/, history/) are left out. | CAPABILITY GAP | `pip install` gave a CLI with no library. The wheel is now 396 KB, with 78 example assets. |
| `sw init [DIR]` | ERGONOMICS | A project folder with a marker, found from any subfolder. |
| `sw caps --llms` → `llms.txt` (generated; a test fails when it is stale; its example asset must build) | ERGONOMICS | A one-page brief for any agent or chat, which cannot drift from the code. |
| `sw doc PROFILE / STYLE / PACK / COMPONENT` prints the file | ERGONOMICS | Found by the acceptance run: budgets were undiscoverable. |
| `templates/asset.yaml`: archetype materials, and a profile comment that names the material budget | BUG (doc) | Found by the acceptance run: the template used a legacy material form, and the budget was a surprise. |
| `SW_GLTF_VALIDATOR` overrides the Khronos validator location | ERGONOMICS | Installed copies and Docker keep the validator outside the package. |
| `.claude/skills/shapewright/SKILL.md`, `Dockerfile`, `.dockerignore`, `MANIFEST.in` | — | Distribution. |
| README: "first asset in five minutes" and a "use it from your agent" table | — | Onboarding. |

**Tests.** `tests/test_packaging.py` covers:
- project packs and components resolving outside the library;
- project files shadowing library files;
- `sw init` from a subfolder;
- llms.txt being current, and its example asset building;
- the wheel containing the library and no build products.

`tests/test_cli.py` was updated to use a project root instead of monkeypatching the library path.

## Acceptance: FA-11, a fresh agent with pip + llms.txt only

**Setup:**
- a clean venv with the wheel installed;
- an `sw init` project containing only `llms.txt`;
- a Sonnet-class subagent, told not to read the repository;
- the task was an unseen prop: *"a stylized wooden mailbox on a post for a cozy mobile game, under 900 triangles, a curved or peaked roof-like top, a small door on the front, and a little flag on the side; inspect and improve at least once; export for Godot"*.

**Result: success.**
- Figures: 308/850 tris, PASS on all layers, export PASS.
- Effort: about 12 tool calls and 2 review cycles, in about 70 s.
- Evidence: `phase16/evidence/fa11_mailbox_sheet.png` and `fa11_mailbox_asset.yaml`.

Baselines:
- FA-01 (clone + AGENTS.md): 65 calls, ~150k tokens.
- FA-10 (after the `sw brief` work): 25–40 calls.

The FA-11 run was lighter (~69k tokens). It is not a like-for-like comparison: it used a different model tier and a different prop.

**Friction reported by the agent, and what was done about each point:**

| friction | action |
|---|---|
| Material budget per profile was nowhere in llms.txt; hit `BUDGET_MATERIALS` after the first review | llms.txt now has a generated profile table (tris, materials, texture, texel) |
| `sw doc mobile_mid` → unknown name | `sw doc` now prints profiles, styles, packs and components |
| `brief` suggested desktop_indie, while the `new` template says mobile_mid | llms.txt step 2 says to set the profile `brief` suggested |
| The template's material syntax differed from llms.txt | template fixed (archetype form) |
| Anchor names and extrude orientation were not in llms.txt | both are now in llms.txt Rules (checked against the code: anchors combine x/y/z tokens, and extrude runs XY→+Z centred) |
| Snapshot after editing captured nothing to compare | llms.txt now says to snapshot the first version before editing |
| Export name `NAME_godot.glb` did not match the llms.txt text | text fixed |
| "2 info items hidden" does not say what they are | open (minor) |

## Gate

| gate item | result | evidence |
|---|---|---|
| clean install runs `sw doctor`, `brief` → `export` with no clone | **met** | clean venv from the wheel; FA-11 |
| a fresh agent with only `llms.txt` exports a valid asset | **met** | FA-11 |
| Docker image builds and runs | **not verified** | no Docker in this environment |
