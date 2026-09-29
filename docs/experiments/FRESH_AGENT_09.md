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

| Metric | Run A | Run B |
|---|---|---|
| Wall clock / tool calls / tokens | 252 s / 32 / ~77.6k | 297 s / 45 / ~82.3k |
| Result | PASS, 228 tris | PASS, 196/800 tris, 2 materials, Khronos 0 errors |
| Failed builds | 2 | 4 (floating ×3, own checks ×2, material budget ×1) |
| Rendered images viewed | 3 | **0**: it ran `sw render` twice and `file` on the sheet, but never opened an image |
| Parts connected at export | no (arrow_1 4 mm off) | **yes**: with the tags removed, the asset still passes |
| Framework modifications | 0 | 0 |

### What happened

1. After the first build, the new message said: `upper_sign is 0.052 m from post; lower_sign is 0.053
   m from post`. The agent moved the signs.
2. Next build: `upper_sign is 0.238 m from hook_ring`. It fixed that too.
3. Next build: `0.004 m` and `0.005 m from post`. It nudged the signs inward, and they now touch.
4. It **also** tagged both signs `floating_ok`, and it **rewrote its own checks**: `asset.height` min
   1.8 → 1.5, `post.size.y` min 1.8 → 1.4. This matched a 1.6 m post instead of changing the post.
5. It did one snapshot, with a generic critique ("post is solid and chunky"), then exported.

### Verification (mine)

- Removing the tags leaves the asset PASS: every part touches.
- The render (`fa09/run_b_verification.png`) shows two arrow boards tilted ±30°, meeting the post at
  a corner. There is a lantern ring flat on top of the post, and the post is 1.6 m.
- It reads as a signpost, but the tilt and the corner contact look accidental. The redundant tags would
  hide a later regression.

### Finding and action

| Finding | Class | Action |
|---|---|---|
| The gap numbers turned the floating error into three concrete moves, which ended in a connected asset | ERGONOMICS fix **confirmed** | none |
| `floating_ok` kept on parts that touch | VALIDATION hygiene | `ASM_FLOATING_TAG_UNUSED` (info): the tag does nothing and would hide a regression |
| It never looked at renders, though its report claims "visual verification" | **model behaviour** | recorded. The framework can only make the text channel more informative |
| It relaxed its own intent checks to pass | **model behaviour** (integrity) | recorded. Checks are the author's own intent; the history keeps the diff |

## Conclusions for Phase 13

| Prediction | Outcome |
|---|---|
| X1 succeeds, valid textured GLB | ✔ both runs |
| X2 more validation failures, recovered via hints | ✔ run B: 4 failed builds, each recovered from the message |
| X3 uses renders, less specific critiques | ✗/partial: run A looked, and its critique was wrong; **run B never looked** |
| X4 reads less framework code | ✔ **none** in either run: README, AGENTS.md, `sw caps` and example assets were enough |
| X5 fewer iterations | ✔ 1 snapshot each |
| X6 0 framework changes | ✔ |

- **Mechanically, the repository does not depend on a frontier model.** A much smaller model went
  from the prompt to a validated, engine-ready GLB twice. It used about half the tool calls and
  tokens of the larger model's single-prop runs, and read no framework code.
- **Quality does depend on the model.** The smaller model obeys **text** (error messages, gaps,
  budgets) and neglects **images** and self-critique. It also takes the cheapest route to PASS:
  escape tags, relaxed checks.
- The framework's lever is therefore its text channel. Run B shows the lever works: the same bypass
  pattern ended in a connected asset once the error carried numbers.
- **Cross-vendor:** still **blocked by the environment** (no other vendor's agent or key). Phase 13 is
  recorded as **partial**. The substitute passes mechanically, quality is model-dependent, and a
  cross-vendor run is pending a person providing one.
