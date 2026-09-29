# Geometry backend boundary

`shapewright/backend.py` is **the only module allowed to import geometry
libraries** (Manifold, trimesh, scipy, fast-simplification, xatlas).
`tests/test_architecture.py` fails the build otherwise. It caught one leak
on its first run: the exporter used scipy for quaternions.

## Why

In v0.1, ops called trimesh and Manifold directly. A library change or an
upgrade touched many modules, and nothing stated which behaviour was a
contract (DESIGN_REVIEW §11).

## The boundary (deliberately small)

| Function | Policy | Current implementation |
|---|---|---|
| `boolean(a, b, op)` | rebuild (face provenance, vertex interpolation) | Manifold |
| `trim(mesh, normal, offset)` | rebuild (caps are new faces) | Manifold |
| `min_gap(a, b)`, `uncovered_volume(a, others)`, `is_closed_manifold(m)` | query | Manifold |
| `convex_hull(points)`, `box`, `box_bounds`, `icosphere` | generate | trimesh / qhull |
| `extrude_polygon`, `revolve_polygon` | generate | Manifold CrossSection |
| `subdivide_midpoint(m)` | refine | numpy (own) |
| `simplify(m, ratio)` | resample | fast-simplification + nearest transfer |
| `smooth_taubin(m, ...)` | preserve | trimesh |
| `raycast`, `section_points` | query | numpy (own) |
| `connected_components(m)` | query | scipy |
| `load_mesh_file(path)`, `load_scene_summary(path)` | generate / query | trimesh |
| `unwrap_charts(m, res, pad)` | UV | xatlas |

What was **not** abstracted: generic mesh I/O, vector maths, and anything
cheap and library-free. It is not a universal geometry interface. It covers
the places where a library's semantics leak.

## What in an asset source is backend-independent

| Source-level semantics | Independent of the backend? |
|---|---|
| params, expressions, checks, materials, sockets, interfaces, components | yes |
| part names, hierarchy, placement by anchors (bbox-based) | yes, up to floating-point tolerance |
| booleans as solid operations (`subtract` = set difference) | yes as a *shape*; triangle layout differs |
| `measure` queries (sections, gaps, rays) | yes, up to tolerance: they measure surfaces, not topology |
| **triangle counts of generators** (`chamfer_box` = 44, cylinder = 4n−4, ...) | **no**: a contract of *our* generators, pinned by `tests/test_architecture.py::test_generator_topology_contract`; budgets are written against it |
| `jitter`, `noise`, `decimate` results | **no**: they operate on vertices and depend on vertex order and count |
| UV charts | **no**: xatlas-specific; regions (docs/UV.md) contain the damage to one part |
| golden geometry hashes | **no**: they intentionally detect any change |

## Swapping a backend

1. Re-implement the functions above.
2. Run `tests/test_mesh_contract.py` (attribute policies), `test_architecture.py`
   (topology contract), `test_shapes_ops.py` (closedness, determinism).
3. Expect golden hashes to change. Review renders with `sw compare` on every
   benchmark before accepting new goldens.

A **paradigm** change (B-rep, SDF) is not a backend swap. The vertex-level ops
have no meaning there. That would be a second kernel behind the same source
format, with a reduced op vocabulary.
