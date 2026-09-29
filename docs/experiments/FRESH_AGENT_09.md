# FRESH_AGENT_09: a substantially smaller model (Phase 13 substitute)

- **Date:** 2026-09-29
- **Plan and predictions:** [FRESH_AGENT_09_PLAN.md](FRESH_AGENT_09_PLAN.md)
- **Agent:** Claude Haiku 4.5, same harness, the same prompt for both runs, no Shapewright-specific
  coaching. Clones had `docs/experiments` and `docs/research` removed.
- **Artifacts:** [fa09/](fa09/). Run A's asset, its export and history are in
  `run_a_village_signpost/`; my verification render is `run_a_verification.png`. Run B is in
  `run_b_village_signpost/`.

## Why a substitute

Phase 13 asks for a **substantially different coding agent**. The container has no other vendor's
agent CLI and no other vendor's API key, so a cross-vendor run is **blocked by the environment**.
It needs a person to provide one. The substitute is a much smaller model. It tests whether the
repository relies on a frontier model to compensate (reading framework code, recovering from vague
errors). It does not test vendor-specific habits.

## Run A (repository at the Phase 12 follow-up commit)

| Metric | Value | FA-01 (larger model, single prop) |
|---|---|---|
| Wall clock / tool calls / tokens | 252 s / 32 / ~77.6k | ~542 s / 65 / ~150k |
| Result | `village_signpost` exported: 228/800 tris, 1 material, 512² atlas, Khronos 0 errors, status PASS | exported |
| Iterations / snapshots | 1 / 1 | 4 / 4 |
| Framework modifications | **0** | 0 |
| Framework code read | none (`README`, `AGENTS.md`, `sw caps`, two example assets) | `surface.py` (UV packing) |
| Looked at renders | yes, 3 times (sheet twice, textured sheet once) | yes; quantified critiques |

### What happened (from the transcript)

1. The agent read README and AGENTS.md, ran `sw doctor` and `sw caps`, and copied patterns from
   `tavern_chair` and `torch_bracket`. It wrote the whole asset in one edit.
2. The first `sw review` gave `ASM_FLOATING_PARTS: arrow_1, hook_arm, hook_ring`. The agent ran
   `sw stats`, then tried `attach` with offsets. After that only `arrow_1` floated.
3. It then went back to plain positions and tagged **all four mounted parts `floating_ok`**
   ("since they're intentionally attached to the post"). Review: PASS.
4. Critique: all ✓ ("instantly recognizable", "chunky primary forms", "the design looks great").
   It snapshotted, exported and rendered, with no second iteration.

### Verification (mine, from the artifacts)

- **arrow_1 floats**, 4 mm off the post (exact solid distance). The top-view parts render shows it
  running beside the post, not through it.
- arrow_2 cuts diagonally through the post. Both "arrows" are flat triangles, 2.5 cm thick, on one
  line (45° and −135°). They point opposite ways, not in two different directions a traveller
  would read, and are darts rather than boards with a pointed end.
- The post is 12 cm square and 2.2 m tall, a thin stick next to 45 cm signs. That contradicts the
  self-critique's "chunky".
- Hook arm and ring connect. Texture, UVs and export are clean.

**Verdict for run A:** **mechanical success, quality failure.** The toolchain was usable without
reading framework code. The model chose the cheapest path out of a validation error, and the
tool's own hint ("tag floating_ok if intended") invited that path.

### Finding and action

| Finding | Class | Action |
|---|---|---|
| `ASM_FLOATING_PARTS` gave no distance, so the agent could not tell 4 mm from 40 cm; the hint offered `floating_ok` as an equal option | **ERGONOMICS / validation hint** | the message names each part's gap to the nearest connected part ("arrow_1 is 0.004 m from post"). The hint shows `attach: {to: <nearest>, at: <anchor>}` and says `floating_ok` is only for parts meant to hover |
| `floating_ok` silenced the check completely, even on a part 4 mm from the post | **VALIDATION** (an escape hatch without a guard) | new `ASM_FLOATING_TAGGED_NEAR` warning when a tagged part is within max(5 cm, 10% of the asset size) of a connected part. It fires on run A's asset and on no benchmark asset. Regression test in `tests/test_validation.py` |
| Self-critique rubber-stamps (all ✓ with a floating sign) | **model behaviour** (not fixed in the framework) | recorded. The review sheet already shows the gap in the parts view; the model did not look for it |

## Run B (same prompt, repository at commit `7197b92`, with the fix)

_Pending: filled in from the run's artifacts._
