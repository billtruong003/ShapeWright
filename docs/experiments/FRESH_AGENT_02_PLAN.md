# FRESH_AGENT_02 plan: relationship-heavy asset (written before the run)

## Question

When coordinates become inconvenient, does a fresh agent express spatial
structure through **relationships** (derived expressions, `measure`, attach,
components, recursive geometry), and does the result **stay correct when its
parameters change**?

## Benchmark

A straight wooden staircase with handrails. Chosen over a cart, bridge or
scaffold because it has all of these at once:
- **repetition that depends on a parameter** (step count),
- **a slope that every railing element must follow** (a direction, not just a position),
- **grounding** (stringers and newel posts on the floor),
- **attachment chains** (tread → stringer, post → tread or stringer, rail → posts),

and a human can judge correctness at a glance.

Evaluation beyond the agent's own claims (done by the experimenters afterwards):
the asset is rebuilt under a grid of parameter changes (step count, rise, run,
width), each validated, and the parts checked for floating/penetration. The
source is statically analysed for the metrics below.

## Prompt (task part, verbatim)

> Use this repository to create: "A stylized wooden staircase for a game: a straight flight of steps with a
> handrail on both sides (posts and a sloped rail). Game-ready, under 3,000 triangles, clean UVs.
> It must be adjustable: the number of steps, the rise and run of each step, and the stair width must be
> parameters. When they change, the treads must stay supported, the posts must stay attached, the
> handrails must keep following the slope of the stairs and connect the posts, and everything must stay on
> the ground. Inspect and improve your work, and show that at least two other parameter settings still
> produce a valid staircase. Export the final asset."

No mention of `measure`, queries, anchors, attach or components.

## Metrics (tools/experiments/analyze_source.py)

- literal spatial constants, derived expressions, measurement queries, semantic attachments, components,
  recursive geometry expressions, `mesh_file` usage, framework modifications (git diff outside `assets/`)
- **Parameterization ratio** (descriptive): among non-zero spatial numbers (positions, offsets, sizes,
  rotations, path/profile points, query planes), the share given by expressions or queries rather than
  literals.
- **Abstraction escape profile**: parts classified as component / measured (semantic) / parametric
  (expressions only) / literal / geometry-expression composition / mesh escape / framework code.
- edit/review iterations (snapshots and reported cycles), tool calls, tokens, human interventions.
- **Perturbation robustness**: fraction of parameter settings that validate without errors.

## Predictions (made before the run)

| # | Prediction | Failure class if it happens |
|---|---|---|
| P1 | The agent parameterizes the treads well: `array` with an offset of `[0, rise, run]` and `count: steps` | — |
| P2 | Handrail posts: placed with arithmetic on the step index expressed by hand (e.g. only first/last post, or an array with a derived offset) | ABSTRACTION FAILURE (no index variable in arrays) |
| P3 | Handrail slope: a `tube` path or a rotated box whose angle is `atan2(rise, run)`, computed by hand; `measure` not used | DISCOVERY FAILURE (if `measure` would have helped) or none (arithmetic is legitimately fine for a straight stair) |
| P4 | Stringers: a rotated box or an `extrude` polygon with a fixed number of points; a saw-tooth stringer whose tooth count follows `steps` is **not expressible** (lists cannot be generated) | CAPABILITY FAILURE |
| P5 | Checking "two other settings" is done by editing params and reverting, or by `extends` variants; no dedicated tool | API ERGONOMICS FAILURE (no "rebuild with overrides" command) |
| P6 | Some literal coordinates remain for detail parts (caps, brackets); parameterization ratio 0.6–0.8 | — |
| P7 | No framework modification | — |
