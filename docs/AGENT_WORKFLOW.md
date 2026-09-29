# Agent workflow

`AGENTS.md` is the short manual. This document explains the loop in depth: what
to do at each step, what good output looks like, how to recover and when to stop.

```
discover → plan → create → validate → inspect → critique → revise ─┐
                               ▲                                   │
                               └───────── snapshot ◄───────────────┘
                                     ... stop rule ... → export → report
```

## 1. Discover (once per session, about 1k tokens)

```bash
./sw doctor && ./sw caps
ls assets/            # worked examples; open the closest one
./sw log tavern_chair # see how a previous loop went
```

Read `docs/ASSET_FORMAT.md` if you have not written a source before. You do not
need to read the framework code to model.

## 2. Plan

Write the plan in your head or in the source's `notes:` before writing parts:

- **Constraints:** budget (`budget.triangles`), `profile`, `style`, and the
  real-world dimensions (look them up or use common standards: chair seat
  0.42–0.48 m, table 0.72–0.76 m, door 2.0–2.1 m, a human is 1.75 m).
- **Parts:** a tree of named parts, the shape family of each, and repetitions
  (mirror/array).
- **Relationships:** which part attaches to which, and which dimensions derive
  from which (these become params and expressions).
- **Intent checks:** 2–5 `checks:` capturing what must stay true while you
  iterate (seat height, overall height, key ratios).
- **Budget split:** roughly 44 triangles per chamfer_box, and
  `2 × segments × rings` for revolved shapes. Keep 20% headroom.

## 3. Create

`./sw new NAME` (template) or `./sw new NAME --from BASE` (inherit). Start
with a **blockout**: primary forms only, correct dimensions, no jitter or
detail. Get it validating before adding character.

## 4. Validate (cheap, deterministic)

`./sw validate NAME`. Fix errors in this order: source → geometry → assembly →
budget → intent → surface. Warnings are judgement calls; resolve them or leave
them knowingly.

## 5. Inspect (the image step)

`./sw review NAME` writes `.build/sheet.png`. **Look at it.** Read it like this:

| Tile | Look for |
|---|---|
| front / right / top (ortho) | true proportions; use the scale bar; symmetry; alignment of parts; ground contact |
| front_right 3/4 (clay) | overall read, silhouette, chamfers catching light |
| parts | that every region is the part you think it is |
| back_left 3/4 | the hidden side: gaps, missing parts, back faces |
| wire | density: triangles spent where they don't change the silhouette |
| UV | red = overlap; very small islands mean low texel density |

Magenta anywhere means inside-out or holed geometry. Zoom with
`sw render NAME --part P --view front [--isolate]`.

## 6. Critique (make it actionable)

Write each finding as **observation → part.param change → reason**:

```
- rear_leg: posts perfectly vertical, reads machined -> shear amount -0.06 (style: gentle lean)
- back_slat: 3 thin slats read "modern kitchen" -> count 2, slat_width 0.09 (fewer, larger forms)
- seat vs legs: legs 4.5 cm look spindly under a 46 cm seat -> leg 0.07 (+55%)
```

Bad: "looks off", "improve the design", "make it better". Use `sw stats` for
exact sizes and ratios. Quantify changes (+15%, 0.045 → 0.07).

Separate **technical** findings (validators) from **perceptual** ones (your
eyes). If a perceptual rule becomes important and measurable, turn it into a
`checks:` entry so it can't regress.

## 7. Revise

- Prefer parameter edits. Then restructure parts. Then new ops/shapes (as
  framework code with tests; see CONTRIBUTING.md).
- Change a few related things per iteration. Many unrelated changes make
  comparisons uninformative.
- `./sw snapshot NAME -m "what changed" --critique "what you saw"` after each
  meaningful revision (at least after the blockout and before export).
- `./sw compare NAME A B` (or `1 current`) to confirm the change did what you
  intended. Look at the diff image: red = removed, green = added.

## 8. Stop

Stop and export when **all** hold:
1. `sw validate` has no errors, and remaining warnings are understood.
2. Your latest critique has no significant perceptual findings.
3. The user's explicit constraints are met (budget, dimensions, style keywords).

Also stop (and say why) when:
- the iteration budget is reached (default 6 revisions after the blockout,
  unless the user set one);
- two consecutive revisions produce no improvement you can name;
- you are oscillating (A → B → A); compare and pick the better one with `restore`.

## 9. Export and report

`./sw export NAME`. Report back:

```
tavern_chair: assets/tavern_chair/export/tavern_chair.glb
  484 / 700 triangles, 0.53 x 0.98 x 0.47 m, 2 materials, 11 parts, sockets: sit_point
  validation PASS (Khronos glTF-Validator: 0 errors), 2 iterations (see sw log)
  known limitations: no textures (flat PBR colours), UV0 ready for baking/painting
```

## Error recovery

| Situation | Action |
|---|---|
| Source won't build | read the `where` path and `->` hint; for a typo, take the suggestion |
| Boolean `OP_FAILED` | tool must overlap the part; both closed; try a slightly larger tool so faces aren't coplanar |
| `ASM_FLOATING_PARTS` | `sw stats` to see the gap; fix `attach` offsets; embed parts 1–2 cm into each other (standard for props) |
| Regression after an edit | `sw compare LAST current`; `sw restore N` (the current file is backed up in `.build/`) |
| Budget exceeded | the error lists the heaviest parts; reduce `segments`; replace `sphere` with a low `rings` count; `decimate` organic parts |
| Renders look wrong but validation passes | check `--mode normals` (magenta = inverted) and `--isolate` the part |
| Missing capability | extend the framework: one decorated function plus an example (automatically tested) |

## Multi-asset work (packs)

- Share a `style` and `profile`. Put pack-wide dimensions in a base asset and
  `extends` it, or copy the relevant params with the same names.
- Cross-asset intent belongs in `checks:` (for example the table checks its
  height relative to the chair seat).
- `sw bench` validates everything. Review sheets side by side to judge
  consistency.
