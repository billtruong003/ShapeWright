# Fresh-agent experiment suite

Each experiment gives a new coding agent only the repository, with this folder and `docs/research`
removed from its clone, and a task. The agent is observed, not coached. Plans and predictions are
written **before** the run. Results are verified from the artifacts, not taken from the agent's report.
Every record lists:
- the exact prompt and the environment;
- outputs and iterations;
- failures and friction;
- framework modifications;
- time, tool calls and tokens;
- the conclusions.

The program suggested an order (single prop, relationships, pack, textured, diverse, imported,
other vendor, mid-poly). The phases ran it in a different order, so the numbers map as follows:

| # | Question | Phase | Result | Framework changes by the agent |
|---|---|---|---|---|
| [01](FRESH_AGENT_01.md) | single unseen prop (anvil on a stump) | hardening | exported, 0 interventions | 0 |
| [02](FRESH_AGENT_02.md) | relationship-heavy asset (staircase) + perturbations | 5 spatial language | gate passed | 0 |
| [03](FRESH_AGENT_03.md) | six-asset component pack (blacksmith) | 6 reuse | gate passed with caveats | 3 (one real bug) |
| [04](FRESH_AGENT_04.md) | textured asset, request → GLB (treasure chest) | 8 surfaces | gate passed | 1 (bug fix) |
| [05](FRESH_AGENT_05.md) | 17-class breadth matrix (4 agents) + held-out 5-class gate | 9 breadth | gate passed | 1 + 1 (bug / false positive) |
| [06](FRESH_AGENT_06.md) | mid-poly stress, 44k-tri fountain | 10 performance | gate passed | 0 |
| [07](FRESH_AGENT_07.md) | import and modify real CC0 assets | 11 import | gate passed | 0 |
| [08](FRESH_AGENT_08.md) | engine-ready delivery for Godot and Unreal | 12 production | gate passed (Godot in-engine) | 0 |
| [09](FRESH_AGENT_09.md) | a much smaller model (Haiku 4.5), 2 runs; cross-vendor blocked | 13 cross-agent | partial: mechanical pass, quality model-dependent | 0 |
| [10](FRESH_AGENT_10.md) | repeat-class cost, before/after on 3 tasks (1 held out) | 14 agent cost | **not met**: onboarding −⅓, total −10–20% / +81% (held out) | 0 |

All runs used the same model family as the authors. FA-09 swapped in a much smaller model from that family. No other vendor's agent was available.

**Framework-modification rate** (the success condition warns against it): after the FA-03 spike, every
change an agent made was a genuine bug or false-positive fix with a regression test, and 0
capability additions came from agents since Phase 6. Each finding was fixed at its own layer (discovery,
ergonomics, abstraction, capability or architecture) and recorded in the experiment's table.

## Acceptance tests (authors as real users)

| record | question | result | framework changes |
|---|---|---|---|
| [MODULAR_HOUSE_PACK_01](MODULAR_HOUSE_PACK_01.md) | 26-module cozy half-timbered house kit + 3 demo houses, seam probe, 5-param stress test | **PARTIAL**: kit, seams, stress and exports OK; 3 framework changes; fresh-agent editability untested | 3 (bug, abstraction gap, performance) |
