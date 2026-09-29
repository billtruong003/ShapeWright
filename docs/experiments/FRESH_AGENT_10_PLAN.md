# FRESH_AGENT_10 plan: repeat-class cost (Phase 14, written before any Phase 14 change)

## Question

Can a fresh agent complete a **repeat benchmark class** meaningfully cheaper after Phase 14, **with
quality preserved**? "Repeat class" means a task of a kind the suite has already run: a single
textured stylized prop (FA-01, FA-04) and an articulated or relationship-heavy prop (FA-02, FA-08).

## Design

Two new tasks, each run twice by fresh agents on the same model as FA-01 to FA-08, with the same
prompt and harness:
- **A (before):** at the last Phase 13 commit, before any Phase 14 change;
- **B (after):** at the Phase 14 commit.

Both runs use fresh clones with `docs/experiments` and `docs/research` removed.

| Task | Class | Prompt (task part) |
|---|---|---|
| T1 | single textured prop | "A stylized grindstone on a wooden frame with a hand crank, for a blacksmith in a mobile fantasy game. Under 900 triangles, surface detail in textures." |
| T2 | articulated, wall-mounted prop | "A hanging tavern sign: a wrought-iron wall bracket with a wooden sign board that hangs from two rings and can swing. Mobile fantasy game, under 1,200 triangles, textured, exported for Godot." |

Neither task has a near-copy in `assets/` (no grindstone; no hanging sign). Both prompts end with the FA-09 wording: "Inspect it, critique it, improve it, and export a
validated GLB", followed by the same experiment-report request.

## Measures

- **Cost:** wall clock, tool calls, tokens, calls before the first build, failed builds, and the
  label breakdown from `tools/experiments/cost_breakdown.py`.
- **Quality:**
  - validation status and warnings;
  - my render inspection against the prompt (floating or intersecting parts, readable parts,
    articulation where asked);
  - iterations with specific critiques.
- **Gate:** B uses ≥ 25% fewer tool calls *or* tokens than A on both tasks, with no quality loss:
  - no new failure class in my inspection;
  - validation still PASS;
  - requested features present.

One run per cell is noisy. A difference under about 20% is reported as "no measurable change",
not as a win.

## Predictions

| # | Prediction |
|---|---|
| P1 | A runs cost 60–90 calls; the edit → review → view loop is about 60% of calls |
| P2 | At least one A run hits a YAML flow-list comma failure or a boolean `OP_FAILED` |
| P3 | Framework-code reads in A answer placement or rotation questions |
| P4 | B's savings come mainly from fewer failed builds and a shorter onboarding, not a shorter loop |

## Amendment (after the A runs of T1 and T2, before any B run)

`sw brief`'s example ranking was tuned while the T1/T2 prompts were known, and the A runs' friction
points fed Phase 14 fixes. T1/T2 B results may therefore overstate the effect. A **held-out T3** was
added to control for that. Its prompt was not used during development, and it runs both A (at `b7f67de`, the
pre-Phase-14 commit) and B (at the Phase 14 commit):

| Task | Class | Prompt (task part) |
|---|---|---|
| T3 | single textured prop, held out | "A small wooden rowing boat with two oars resting inside it, for a lakeside level in a stylized mobile game. Under 1,000 triangles, surface detail in textures." |

The gate is judged on all three tasks. T3 carries the most weight, because nothing was tuned to it.
