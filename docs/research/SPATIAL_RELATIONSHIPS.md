# Research: how systems represent spatial relationships (Phase 5.1)

Question for Shapewright: **which abstractions let an autonomous agent state
spatial intent ("posts stand on every third tread", "the handrail follows the
stair slope") instead of computing coordinates?**

Sources: documentation and design of the systems named below, as known at the
time of writing. Nothing here was benchmarked except Shapewright itself.

## 1. Survey

| Domain | Representative systems | How relationships are represented | What an agent would struggle with | What transfers |
|---|---|---|---|---|
| Feature-based CAD | SolidWorks, Fusion, FreeCAD Sketcher, Onshape | 2D sketch constraints (coincident, parallel, tangent, distance) solved numerically; features reference sketch/face/edge *by selection* | topological naming problem (references break when topology changes); solver states (under/over-constrained) are opaque; relies on picking | **dimension-driven parameters**; references to *named* datums instead of picked faces |
| CAD assemblies | SolidWorks mates, **Onshape mate connectors** | a *mate connector* is a local coordinate frame attached to a feature (face centre, edge midpoint, vertex). Parts are placed by aligning frames (fastened, revolute, slider…) | full mate solving is overkill for static props | **frames as first-class, named attachment points**, derived from geometry, not typed coordinates |
| Code CAD | OpenSCAD, CadQuery, build123d | pure transforms and loops (OpenSCAD); **selectors** and **workplanes** (`faces(">Z").workplane()`), `Locations`/`GridLocations`/`PolarLocations` | OpenSCAD makes the author carry all coordinates; CadQuery selectors are string mini-languages | **distributions** (grid/polar/along-path location sets) and **workplanes derived from geometry** |
| Node-based procedural | Houdini SOPs, Blender Geometry Nodes | points with attributes (P, N, orient, pscale); "copy to points"; "resample curve"; ray/project SOPs | graphs are verbose; everything is implicit in attribute streams | **copy-to-points on a curve**: define a path once, derive positions and orientations from it; per-copy index/parameter `t` |
| Scene graphs | USD, glTF, game engines | parent/child transforms; relative placement via hierarchy; USD `xformOp` stacks | purely numeric local transforms | hierarchy, pivots (already present) |
| Game-engine attachment | Unreal sockets, Unity child transforms, Godot `BoneAttachment3D` | named sockets on meshes; attach actor to socket with an offset | sockets are authored by hand | **named sockets as the agent-facing attach target** |
| Robotics/kinematics | URDF, MJCF, Denavit–Hartenberg | a tree of links and joints; each joint has an origin frame and axis relative to its parent | kinematic solving is not needed for static assets | **frames with an axis**: "along this axis from that frame" is a natural static relation |
| Architectural generators | CityEngine CGA, Rhino/Grasshopper | split rules (`split(y){ ~1: floor }*`), repeat along a scope, component splits (faces) | CGA is a DSL | **repeat with index-derived placement; derive sizes from the enclosing scope** |

## 2. Findings for agents

1. **Solvers are the wrong default.** Every mature solver fails in ways that
   need interactive debugging: under-constrained drift, flips, no solution.
   Agents in a loop need **evaluate-in-order** semantics with failures that name
   the missing thing. Shapewright's `measure` already follows this.
2. **Frames beat points.** Onshape mate connectors and URDF joint origins carry
   an *orientation*, not just a position. Stairs, railings, ramps, roofs and
   bridges all need "along the slope", which is a direction.
3. **Distributions are the missing idiom.** CadQuery `Locations`, Houdini
   copy-to-points and CGA `repeat` all say "N things along something, each
   knowing its index". Shapewright has `array` with a *constant* offset and no
   index variable, so anything that varies per copy (baluster height, spacing
   to fill a length) falls back to arithmetic done by the author outside the tool.
4. **Paths are shared geometry.** A stair's nosing line, a handrail and a
   stringer edge are the same line. In Houdini it is one curve; in Shapewright
   each part would restate it. A named path is the smallest shared primitive.
5. **References by name, never by index.** CAD's topological naming problem
   shows that references to generated sub-elements break. Shapewright must keep
   references to *parts, anchors, regions and paths*, never vertex or face ids.

## 3. Candidate abstractions (ranked by expected value for agents)

| Candidate | Expresses | Cost | Risk |
|---|---|---|---|
| **Index-aware repetition** (`array` exposing `i`, `n`, `t` to the part's expressions) | per-copy variation, fill a length with k copies | small | low |
| **Named paths** (`paths:` polylines/curves defined from params, sampled with `at(t)`, `dir(t)`) usable by `tube`, positions and distributions | "follow the stair line", "posts along the rail" | medium | medium: new namespace |
| **Frames** (`frame` query: origin + axes from a part's anchor, or from two points) | slope-aligned placement, `rotate` from geometry | medium | low |
| `tilt`/`angle` query (direction between two measured points) | orientation without hand trigonometry | small | low |
| Full constraint solver | cyclic intent | large | high |

**Decision rule for Phase 5:** implement nothing before the benchmark.
Predict the failure classes, observe a fresh agent, then fix the layer that
actually failed.
