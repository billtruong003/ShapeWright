# Handoff: a long end-to-end development run on your own machine

Paste everything inside the fence below into **Claude Code (Opus)** in a terminal, from an empty folder. The prompt is self-contained: repository, setup, reading order, rules, the ordered work queue with gates, verification, and when to stop.

````text
You are the lead developer of Shapewright, an agent-native 3D modelling framework for game assets:
declarative YAML asset sources -> deterministic build -> 8 validation layers -> inspection renders -> game-ready GLB.
You will run a LONG, END-TO-END development session: work through the queue below phase by phase, verify every
step, record every result honestly, push each finished phase, and only stop at the stop conditions.

==================================================================================================
0. REPOSITORY AND SETUP  (do this first, in order)
==================================================================================================
Repository: https://github.com/billtruong003/ShapeWright        (default branch: main; everything up to Phase 20a is on main)
Docs site:  https://billtruong003.github.io/ShapeWright/        (built from website/ + tools/site/build_site.py)

  git clone https://github.com/billtruong003/ShapeWright && cd ShapeWright
  git config user.name "billthedev" && git config user.email "truongbill003@gmail.com"
  python3 -m venv .venv && source .venv/bin/activate          (Windows: .venv\Scripts\activate)
  pip install -r requirements.txt "mcp>=1.10" ruff "mkdocs>=1.6,<2" "mkdocs-material>=9.5"
  (optional, Node installed) cd tools/gltf-validator && npm install && cd ../..   # Khronos validator in `sw export`
  ./sw doctor                       # Windows: python -m shapewright doctor
  python3 -m pytest -q              # baseline: all pass (433 tests, ~5 min; Linux and Windows). If not, STOP and report.
  ruff check .                      # baseline: clean
  (optional) blender --version      # Phases 22/24/25 use headless Blender if present

Commit rules for this repository:
  - Commits are authored by billthedev (configured above). Do NOT add Co-Authored-By or session trailers.
  - Never force-push main. Never rewrite history of a pushed branch.

==================================================================================================
1. READ, IN THIS ORDER, BEFORE CHANGING ANYTHING  (skim long files; you need the rules and the open items)
==================================================================================================
  1. README.md                         what the product is, feature map, links
  2. AGENTS.md                         the operating manual for agents using Shapewright (the loop, the rules)
  3. llms.txt                          the one-page brief (generated: ./sw caps --llms). Proves you know the vocabulary.
  4. docs/PHASE_PLAN_16.md             THE PLAN: revision note (Blender backends), status table, RUN PROTOCOL (section 1),
                                       record format (section 2), phase table, dependency graph, phase briefs (section 5)
  5. docs/phases/PHASE_16.md, PHASE_17.md, PHASE_19.md, PHASE_20.md, PHASE_18.md, PHASE_20a.md
                                       what shipped, each gate table, every PARTIAL and why, "not done" lists
  6. docs/experiments/MODULAR_HOUSE_PACK_01.md
                                       the acceptance test that drove Phases 19-20 (kit rules, seam findings, limitations)
  7. docs/ARCHITECTURE.md (skim), docs/ASSET_FORMAT.md (the Composition section),
     docs/VALIDATION.md (codes), docs/MCP.md, CONTRIBUTING.md (how to add shapes/ops/validators)
  Then look, do not read, at: shapewright/assemble.py (build), shapewright/validate/ (layers),
  shapewright/paths.py (library vs project), shapewright/mcp_server.py, tools/site/build_site.py.
  Use `./sw caps`, `./sw doc NAME` and `./sw brief "..."` instead of grepping for vocabulary.

==================================================================================================
2. RUN PROTOCOL  (from docs/PHASE_PLAN_16.md section 1; follow it for every item below)
==================================================================================================
  - One branch per work item: `phase/NN-short-name`, cut from the latest main. Push it with
    `git push -u origin <branch>` when done. Open a pull request against main with the phase record as the body.
    Do NOT merge it yourself; the next item may stack on the previous branch if it depends on it.
  - Before coding: docs/phases/PHASE_NN_PLAN.md (goal, scope, out of scope, gate, risks, predictions).
  - A new capability needs a recorded failing case (benchmark, experiment finding, tutorial). Every framework change
    gets a regression test and a class: BUG / ERGONOMICS / ABSTRACTION GAP / CAPABILITY GAP / VALIDATION GAP, with
    one line on why it is generic, not asset-specific.
  - Before each commit: `python3 -m pytest -q` (use `-k` for the area during iteration, full run before commit) and
    `ruff check .` must pass. Golden changes (`python3 tests/update_golden.py`) must be explained per asset in the
    commit message. Regenerate llms.txt (`./sw caps --llms > llms.txt`) when caps/doc strings change (a test checks it).
  - Look at renders. For any asset work, run `./sw review NAME` and open .build/sheet.png; for kits also
    `python3 tools/experiments/seam_probe.py NAME --tol 0.002`.
  - Finish with docs/phases/PHASE_NN.md: what shipped, evidence (numbers, images under docs/phases/phaseNN/evidence/),
    gate table (met / met with exceptions / not met / not verified) and verdict PASS / PARTIAL / FAIL. Be honest:
    a restated gate or an unverified item is written as such.
  - If you change user-visible behaviour, update: AGENTS.md or docs/*.md, the website/ page that mentions it,
    and README.md if it is a headline feature. Website tutorials: every `# run` block must keep passing
    (tests/test_site_docs.py).

==================================================================================================
3. WORK QUEUE  ->  docs/REMAINING_WORK.md is the single source of truth
==================================================================================================
  Read docs/REMAINING_WORK.md fully (after the reading list above). It has every remaining task with the exact
  how-to, files, commands, gates, effort points and the progress table. Do the tracks in its order:
    A phase/20b-cleanup -> B phase/19b-houses -> R phase/25a-render -> D phase/18b-site -> E release/1.0
    -> F phase/21-shared-surfaces
    (C phase/17b-mcp-verify needs the owner's desktop client: do it when the owner says the client is ready)
  When a task is done: tick it in docs/REMAINING_WORK.md and update its progress table in the same commit.
  Track G (characters, Phases 22-25) only after the owner confirms, following the same file.
  Status at hand-off: main @ d9877eb, CI green on Linux + Windows, 433 tests pass. macOS is out of scope.

==================================================================================================
4. STOP CONDITIONS  (stop, push what you have, write the record, report)
==================================================================================================
  - A gate turns out to be wrong or unmeasurable -> propose a corrected gate, do not quietly change it.
  - More than 3 unplanned framework changes inside one phase.
  - An asset-format change that would break existing sources without a migration.
  - A needed tool is missing (Blender, Godot, an MCP client) -> record "not verified" and continue with the
    next item that does not need it.
  - After track E (v1.0 released) and after track F: stop and report (they change what the next phases should be).

==================================================================================================
5. REPORT FORMAT  (after every item, in chat)
==================================================================================================
  Item / branch / PR link
  Verdict: PASS | PARTIAL | FAIL, and the gate table in one line per row
  What changed (framework, with class; assets; docs)
  Evidence: numbers + image paths
  Not done / not verified, and why
  Next item you will start

==================================================================================================
6. COST DISCIPLINE
==================================================================================================
  - One work item per session context if possible; re-read the phase record instead of old code.
  - Prefer `./sw brief/doc/caps` and the phase records over broad file reading.
  - During iteration run targeted tests (`-k`); the full suite once before each commit.
  - Do not render or export everything repeatedly: review only the assets you touched.
````

## Notes for you (the person)

- **GitHub Pages:** `.github/workflows/docs.yml` publishes to the `gh-pages` branch on every push to `main`. If the site does not appear, open *Settings → Pages* and set *Source: Deploy from a branch → `gh-pages` / root*.
- **Order:** tracks A, B, R, D, E (docs/REMAINING_WORK.md) finish v1.0. F is Phase 21. G is the optional character track.
- **Stopping:** the agent stops by itself after E (v1.0 released) and after F, so you can look at the results before the expensive phases.
- **Your part:** track C needs Claude Desktop or Cursor on your machine; the release (E) may need your PyPI token; Docker verification needs Docker.
