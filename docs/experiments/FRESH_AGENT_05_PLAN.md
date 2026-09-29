# FRESH_AGENT_05 plan: modelling-breadth matrix (Phase 9, written before the run)

## Question

Can Shapewright build **diverse asset classes** with its current vocabulary, or do agents keep
escaping to framework changes, one-off generators, hand-computed point lists or baked meshes?
Which missing capabilities recur **across** classes? Phase 9 adds only those, then re-tests on
held-out classes.

## Coverage before the run

| Family | Already evidenced by | Probed here |
|---|---|---|
| Furniture | tavern chair/stool/table/bench, smith pack (FA-03) | — |
| Architectural: stairs | wooden_staircase (FA-02) | doorway arch, roof section, wall-with-window kit piece |
| Street prop | street_lamp | fire hydrant |
| Hard-surface | crate, treasure chest (FA-04) | sword (weapon), gearbox (machine component), sci-fi cargo panel |
| Curved / profile | barrel, lamp | vase, pipe assembly, horn |
| Stylized organic | rock | tree stump with roots, mushroom cluster, potted plant |
| Vehicle / mechanical | — | hand cart, mine cart on rails, wheel-and-axle assembly, crank winch |

Existing benchmarks are not re-run; the new classes are 17 requests in four independent runs
(A–D), each a fresh agent in its own clone with the same isolation as FA-02..04.

| Run | Requests |
|---|---|
| A hard-surface | sword, gearbox, sci-fi cargo panel, fire hydrant |
| B architectural + pipes | stone doorway arch, roof section, wall-with-window kit piece, pipe assembly |
| C curved + organic | vase, horn, tree stump with roots, mushroom cluster, potted plant |
| D mechanical | hand cart, mine cart on a rail segment, wheel-and-axle assembly, crank winch |

The prompts state each object, a style and a triangle budget, nothing about how to model it. The
agent may change the framework, and every change is recorded (as in earlier experiments).

## Metrics per asset

Parameterization ratio and escape profile (analyze_source.py), iterations, validation
failures, final status and triangles, plus **gap records**: each place where the agent wanted to
write something it could not, what it wrote instead (hand-computed points, many near-identical
parts, baked mesh, framework change), and its cost in lines/parts. Gaps are counted **by class**,
and one that recurs in ≥ 3 classes (of 17) is a Phase 9 candidate.

## Predictions

| # | Predicted gap | Expected in | Class if it happens |
|---|---|---|---|
| G1 | **Per-index variation**: arrays whose instances differ (shingle rows offset, leaves rotating, spoke angles, gear teeth, roots of different lengths); written as many hand-numbered parts | roof, plant, stump, mushroom, cart, winch | ABSTRACTION (array has no index variable) |
| G2 | **Generated point lists**: arcs, circles and gear profiles typed as literal coordinates in `extrude`/`tube` paths | doorway arch, gearbox, horn, pipes | ABSTRACTION (no curve/arc generators) |
| G3 | **Loft / varying cross-sections**: blades, horns and leaves want one profile blending to another | sword, horn, plant | CAPABILITY |
| G4 | **Selective bevel/inset**: panel lines, sharpened blade edges | sci-fi panel, sword | CAPABILITY (known roadmap gap) |
| G5 | **Smooth blends** between organic parts (roots into trunk, stem into cap) | stump, mushroom | CAPABILITY (SDF/smooth union); may be accepted as hard joins in low-poly style |
| G6 | **Thin/open surfaces** (leaves, cards) trip thin-feature/closed-mesh validators | plant | VALIDATION/CAPABILITY |
| G7 | Rotating parts (wheels, crank) want pivots on the axle | cart, mine cart, wheel, winch | Phase 12 input (not a Phase 9 gap) |
| G8 | Hard-surface and profile classes (hydrant, vase, pipes, gearbox body) succeed with existing shapes | — | — |
| G9 | Framework modifications: 1–3 across all four runs, clustered on G1/G2 | — | each classified |

## Gate (from the program)

"The benchmark set should demonstrate that Shapewright can create diverse asset classes without
frequent framework changes or one-off custom generators." It is operationalized as follows:
after the Phase 9 additions, a **held-out** fresh run over classes not used to design them
(for example: a battle axe, a bridge section, a lantern, a cactus, a wheelbarrow) completes with
≤ 1 framework change and no asset-specific generator, with every asset valid and exported.
