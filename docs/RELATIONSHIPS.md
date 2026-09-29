# Spatial relationships: anchors, queries and (not) constraints

## Problem (v0.1)

Placement had two tools: absolute `position` and `attach` (bbox anchor to bbox
anchor). Any relationship involving a part's *actual shape* had to be derived
by hand. The chair's crest rail used `post_z - lean * rail_y / back_height`
and the stretchers assumed vertical legs. Change `shear` to `bend`, splay
the legs or change the lean, and the formulas silently become wrong.
DESIGN_REVIEW §2 called this the biggest risk in the format.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Full constraint solver** (CAD-style: coincident, parallel, distance, tangent) | Rejected for now. Solvers fail opaquely (over/under-constrained, flips between solutions), which is the worst failure mode for an agent in a loop. They also need an explicit degree-of-freedom model for every part. Justified only if benchmarks show cyclic relationships that ordering cannot resolve. |
| **Surface anchors** (`at: {surface: top, uv: [0.2, 0.5]}`) | Useful but narrow: they cover "point on a face", not "gap between", "cross-section at height", or "where does this ray hit". |
| **Named local frames on parts** | Good for authored attachment points (sockets already do this). They don't remove derivations that depend on another part's deformed shape. |
| **Geometric queries on already-built parts** (`measure:`) | **Chosen.** Deterministic, ordered (no solving), explainable failures, and they compose with the existing expression language. |

## The abstraction: `measure`

A part may declare named queries. They run against parts built **before** it
(dependency ordering is automatic from the references). The results are
read-only namespaces usable in any expression of that part: shape size,
position, rotate, ops.

```yaml
top_rail:
  measure:
    post: {section: rear_leg_right, axis: y, at: rail_y}      # real cross-section of the (sheared) post
  shape: {type: chamfer_box, size: [seat_width + 0.04, rail_height, leg * 0.8]}
  position: [0, rail_y, post.center.z]

front_stretcher:
  measure:
    span: {gap: [front_leg_left, front_leg_right], axis: x, section: {axis: y, at: 0.22}}
    leg_at: {section: front_leg_right, axis: y, at: 0.22}
  shape: {type: chamfer_box, size: [span.length + 0.03, 0.04, 0.04]}
  position: [span.center, 0.22, leg_at.center.z]
```

| Query | Returns | Intent it expresses |
|---|---|---|
| `section: part, axis, at` | `min max center size` (x, y, z) of the surface cut by a plane | "where is this (sheared, bent, tapered) part at height h" |
| `gap: [a, b], axis, section?` | `start end length center` of the free interval between two parts | "span between the inner surfaces of these legs" |
| `bounds: part` | box namespace | "relative to that part's extent" |
| `anchor: part, at: top_front` | point | "at that anchor" (as an expression value) |
| `ray: part, from, dir` | hit point, distance | "project onto that surface" |

Failures name the part and the plane or ray (`MEASURE_FAILED: section plane
y=1.92 misses 'rear_leg_right' (it spans y 0.0000..0.9826)`).

## Evidence it works

`tests/test_relationships.py` perturbs the chair through its public interface:
lean 0 to 0.15 m, rear splay 6°, wider seat, thicker legs, shallower seat, no
back. It asserts **no validation errors** (nothing floats, grounding holds) and
that the rail follows the post's actual cross-section for every lean. With
v0.1's hand-derived formulas, the stretchers did not follow the legs'
splay at all.

## Limits (honest)

- **Order-dependent, not simultaneous.** A queries B only if B was built first.
  Mutual relationships ("A and B centred on each other") cannot be expressed.
  Cycles are reported.
- **Orientation is still authored.** The rail's tilt is still
  `-atan2(lean, back_height)`. A two-section query can compute it, but there is
  no `tilt` query yet.
- **Anchors remain bounding-box based** for `attach`. Queries are the surface-aware path.
- **Sections use the part's full surface,** so a part with several disjoint
  pieces at that height yields the extent of all of them.
- Parts are placed by translation after queries; there is no "rotate to fit"
  or "scale to fit". Fitting is expressed through sizes in the shape.

## Next steps (only when benchmarks need them)

`tilt` and `normal` queries (orientation from geometry), region-restricted
sections (`section: {part: leg, region: side}`), and, only if cyclic intent
appears, a *small* solver for 1-DoF relations (slide along axis until touch)
that reports unsatisfiable sets by name.
