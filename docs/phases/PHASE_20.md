# Phase 20: seam validation

**Verdict: PASS, with two gate items restated.**

- **The "26 recorded cases".** The iteration-1 list predates the probe's visibility filter, and the iteration-1 geometry was never committed. The honest fixture is the committed MHP-01 cottage (below): 6 visible pairs, all flagged; 18 buried pairs, correctly not flagged; 2 already fixed before that commit.
- **"0 false positives".** 16 existing benchmark assets are now flagged. Each flag is a real flush-face overlap, listed below.
- **Near-float (1–5 mm).** Not implemented as a separate check. See the end of this record.

Branch `phase/20-seams`, stacked on `phase/19-composition`. It is not merged.

## What shipped

| change | class | evidence it is generic |
|---|---|---|
| `seams` validator (assembly layer), `SEAM_COPLANAR_OVERLAP` (warning) | VALIDATION GAP | MHP-01 §11.1: z-fighting between parts passed every layer. It is also present in 16 older benchmark assets (below). |
| `OP_FACES_INVERTED` (warning, geometry): a displacing op (`jitter`, `noise`, `inflate`) turned faces inside out | VALIDATION GAP | MHP-01 §11.3: a 1 mm shingle wedge inverted under 6 mm of jitter, and every layer passed. Also found in the existing `wheelbarrow` tray (2 faces). |
| `ASM_CONTACT_ONLY` (info, assembly): a part touches its neighbours only face to face, with no overlap | VALIDATION GAP | MHP-01 §11.2: the awning met the wall only by exact contact, which showed as a hairline in renders. |
| `tools/experiments/seam_probe.py` kept as the instrument (tolerance switch, full listing); the validator is the same algorithm | — | — |
| Validator registration order made independent of import order | BUG | A test importing `validate.seams` first reordered `sw caps` output, which broke the llms.txt freshness test. |

**How `SEAM_COPLANAR_OVERLAP` works:**
- **Candidates.** Triangles are bucketed by quantised plane. Pairs from different parts are compared only within a bucket and only when their bounding boxes overlap.
- **Overlap.** Each pair is clipped exactly in the shared plane. A local plane-separation check drops near-parallel false matches.
- **Visibility.** A sample point in front of each overlap is tested against every other closed part with a generalised winding number. Overlap buried inside a third part is classified as hidden and not reported.
- **Thresholds.** Plane tolerance 1 mm. A pair is reported at 0.5 cm² of visible overlap.
- **Output.** Data `{parts, area_m2}` for agents; the hint gives three fixes (depth ranks, embedding, cut).

## Evidence

**MHP-01 committed cottage** (`git worktree` at the MHP-01 commit):
- the validator flags all **6/6** visible pairs: 4 X-brace crossings of 402 cm² and 2 gable rake apexes of 42 cm²;
- it agrees with the probe on the **18** buried pairs;
- the remaining **2** iteration-1 pairs (head rail vs infill) were already fixed in that commit.

**Current kit houses.** 0 flagged in the cottage, townhouse and workshop.

The townhouse still has 2 door brace ↔ ledge pairs at 1–2 mm separation. The probe flags them at its stricter 2 mm tolerance. The validator does not, since 1–2 mm is far above depth-buffer precision at game camera distances. They are recorded here, not hidden.

**Existing benchmark assets now flagged** (warnings; status stays WARN or PASS for the other layers). All are real flush coplanar overlaps between parts:

| asset | pairs | example |
|---|---|---|
| stone_doorway | 2 | wall ↔ plinth fronts flush, 1,396 cm² |
| ornate_fountain | 13 | bed ↔ plinth tops, 268 cm² each |
| wooden_staircase (+3 variants) | 6 each | stringer ↔ newel, 57.8 cm² |
| park_bench (+unreal) | 6 each | rear_leg ↔ seat_rail, 19.2 cm² |
| pipe_assembly | 2 | stand_post ↔ stand_foot, 36 cm² |
| well_winch | 1 | crank ↔ grip, 10.4 cm² |
| roof_section | 8 | wall_plate ↔ rafter, 5.6 cm² |
| tavern_table | 2 | stretcher ↔ cross_stretcher, 6.1 cm² |
| mine_cart | 5 | chassis ↔ bumper 5.6 cm²; wheel ↔ axle 4.6 cm² |
| smith_wall_shelf | 2 | back_board ↔ batten, 3.2 cm² |
| storage_chest (+unreal) | 2 each | lid ↔ hinge, 1.3 cm² |

**Cost.** Townhouse (33k tris) 0.74 s against 30 s of validation (2.5 %). Workshop (45k) 0.73 s. Fountain (44k, many flush faces) 4.9 s. All 78 assets: 7.3 s in total.

**Tests.** `tests/test_seams.py` (8 tests), MHP findings reduced to their geometry:
- X-brace crossing flagged, and the depth-rank fix clears it;
- buried plank ends classified hidden and not flagged;
- face-to-face contact gives `ASM_CONTACT_ONLY` (embedding clears it);
- flush plinth flagged;
- jitter on a 1 mm slab gives `OP_FACES_INVERTED`, and 4 cm does not;
- the kit cottage and workshop are seam-clean.

All 422 tests pass.

## Gate

| gate item | result |
|---|---|
| recorded MHP cases re-created as fixtures and flagged | **met, restated**: every *visible* recorded case in committed geometry is flagged (6/6); buried ones are correctly classified; the class of each finding is a unit fixture |
| 0 unexplained false positives across `sw bench` | **met**: 16 assets flagged, each a real flush overlap (table) |
| under 10 % extra validation time on the townhouse | **met** (2.5 %) |

## Not done

- **Near-float (1–5 mm gaps) as its own check.** The 1 mm contact tolerance already reports such parts as floating when they have no other connection. A part that is connected elsewhere but hovers 1–5 mm off a *second* surface is not detected.
- **The 16 flagged benchmark assets are not fixed.** That is asset work, left for the next session.
