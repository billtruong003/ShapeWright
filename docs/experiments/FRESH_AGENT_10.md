# FRESH_AGENT_10: repeat-class cost before/after Phase 14 (Phase 14 gate)

- **Date:** 2026-09-29
- **Plan:** [FRESH_AGENT_10_PLAN.md](FRESH_AGENT_10_PLAN.md). The amendment added held-out task T3 after the
  A runs of T1/T2.
- **Model:** same as FA-01 to FA-08.
- **A (before):** commit `b7f67de`.
- **B (after):** commit `c4a96e8`, with `sw brief`, `pivot: {at}`, `flat_bottom at`, the info-level profile
  texel target and comma rejoining.
- **Artifacts:** every final asset is in [fa10/](fa10/) (`t1_a_…` to `t3_b_…`). My verification renders are
  `a_runs_verification.png` and `b_runs_verification.png`. `tools/experiments/cost_breakdown.py` produced the
  label counts.

## Results

| Task | Run | Wall clock | Tool calls | Tokens | Calls before the first build | Snapshots | Final |
|---|---|---|---|---|---|---|---|
| T1 grindstone | A | 340 s | 40 | ~130k | 16 | 4 | PASS, 840/900 |
| | B | 275 s | 35 (−12%) | ~108k (−17%) | 10 | 3 | PASS, 836/900 |
| T2 tavern sign | A | 450 s | 42 | ~144k | 17 | 3 | PASS, 892/1200 |
| | B | 393 s | 38 (−10%) | ~116k (−20%) | 11 | 4 | PASS, 716/1200 |
| **T3 rowboat (held out)** | A | 494 s | 36 | ~134k | 15 | 3 | PASS, 804/1000 |
| | B | 930 s | **65 (+81%)** | **~179k (+34%)** | 10 | 4 | PASS, 836/1000 |

**Quality (my inspection of renders and files):** preserved in every pair. Every run passed validation with
Khronos 0/0. No new failure class appeared.
- T1 B is a little better than A: the trough sits under the wheel and the proportions are chunkier.
- T2 A and B are equally good: a readable bracket, the board on a pivot, the emblem.
- T3 B's hull is smoother, with a curved sheer. It painted the inner transom to hide end grain.

## Where the calls went

| Label | T1 A → B | T2 A → B | T3 A → B |
|---|---|---|---|
| read docs + examples + `sw doc` + caps/brief | 14 → 9 | 16 → 14 | 11 → 12 |
| read framework code | 3 → 4 | 4 → 1 | 2 → **11** |
| `sw review` | 5 → 6 | 5 → 7 | 6 → **16** |
| view image | 6 → 6 | 8 → 7 | 9 → 15 |
| edit asset | 5 → 4 | 5 → 6 | 6 → **17** |

## Predictions vs outcome

| # | Prediction | Outcome |
|---|---|---|
| P1 | A runs cost 60–90 calls, ~60% in the loop | ✗: A runs cost only 36–42 calls. The repository was already cheaper than FA-01 (65). The loop was about half |
| P2 | an A run hits a comma trap or boolean `OP_FAILED` | ✗: neither occurred |
| P3 | A's framework reads answer placement/rotation questions | ✔: strut ops frame (T1), pivot format (T2), nested recentring (T3) |
| P4 | B's savings come from a shorter onboarding, not a shorter loop | ✔ for T1/T2: onboarding fell from 16–17 to 10–11 calls. T3 shows the loop dominating |

## Gate verdict: **NOT MET**

The gate required ≥ 25% fewer calls or tokens on every task, with quality preserved.
- **T1 and T2 (tuned tasks):** −10 to −20%. Below the bar, and optimistic because of the tuning.
- **T3 (held out):** B cost *more*. Onboarding still shrank (15 → 10 calls before the first build). Then the
  agent chose a more ambitious hull (a lathe bowl, stern cut, a lathe cavity cut back by a nested intersection,
  a cylinder cut for the curved sheer). It met the nested-recentring trap (11 framework reads) and made 16
  review passes. It also ran `update_golden.py` and the full test suite (2 min), as AGENTS.md says to for a
  new asset; the A agents skipped that.

**What the evidence says:**
1. **Onboarding cost is reliably reducible.** `sw brief` cut the calls before the first build by 33–38% in
   all three B runs, including the held-out one (16→10, 17→11, 15→10).
2. **Total cost is dominated by iteration effort.** That effort varies with the agent's ambition and with
   capability gaps it runs into, not with onboarding. Single runs vary by ±50% at the same commit. The effect
   of a 5-call saving is below that noise.
3. **The cost lever that remains is capability gaps that force hand work.** T3 B's extra 29 calls
   centre on the nested-recentring trap and the absence of a hull/loft shape. `origin: keep` for nested
   expressions was added after this run. It is untested by a fresh agent.
4. `sw brief`'s ranking was weak on the held-out prompt: it proposed `hand_cart` as the closest example for a
   boat. Keyword ranking has limits when no similar asset exists. The rules and vocabulary sections were
   still useful.

## Findings and action

| Finding | Class | Action |
|---|---|---|
| 16–17 onboarding calls | DISCOVERY | `sw brief` (−33–38% calls before the first build, measured) |
| pivot needed hand-derived −1..1 coefficients (T2 A) | ERGONOMICS | `pivot: {at: [x, y, z]}` and expression coefficients |
| splayed legs grounded by a hand-tuned `flat_bottom` fraction (T1 A) | ERGONOMICS | `flat_bottom: {at: 0}` in authoring coordinates |
| texel target of the profile default unreachable → warning every run | VALIDATION noise | info unless the asset set the target |
| `sw compare` showed WARN for a snapshot recorded PASS (T2 A) | BUG | `status_recorded` |
| `measure` on an unknown instance name → AttributeError (T1 B) | **BUG** | `MEASURE_FAILED` with a word-order suggestion; test |
| UV lock hints printed `sw uv lock ASSET` (fails) (T1 B) | BUG | hints say `sw uv ASSET lock` |
| nested boolean/combine inputs recentred: cavity offsets by hand (T3 A and B, T2 B) | **ABSTRACTION** | `origin: keep` on nested expressions; documented on boolean and combine |
| no hull/loft shape; no shared deformation across parts (T3) | CAPABILITY | recorded (capability map) |
| interpenetration (tool rest through wheel, T1 A; seat through hull, T3) not validated | VALIDATION gap | recorded. Deliberate embedding is normal in props; a "passes through" check needs care |
| mobile props export one node per part unless `export.merge` is set (T1 A/B) | ERGONOMICS | a `sw brief` rule. A profile default was tried and reverted: it changes the export structure the committed tests assume |

**Framework modifications by agents:** 0. T3 B updated `tests/golden.json` as AGENTS.md instructs for a new
asset.
