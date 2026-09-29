# Reuse: components, packs, families, variants and instances

## The five concepts (Phase 6 semantics)

| Concept | Encapsulates | Mechanism | Changes allowed from outside | Evidence |
|---|---|---|---|---|
| **Component** | *structure* (a sub-assembly) | `components/NAME.yaml`, `component:` + `with:` | public params only; group placement, `mirror`/`array` of the whole group | blacksmith pack: `plank_top` ×11, `iron_band` ×9, `leg_frame` ×3 |
| **Pack** | *shared vocabulary of a set* (scale, construction params, palette, profile/style) | `packs/NAME.yaml`, `pack: NAME` in each member | none: pack params/materials are **read-only** in members (`PACK_OVERRIDE`); members add their own | blacksmith pack: 0 material drift across 6 assets |
| **Family** | *intent* of a base design | `interface: {params}` on a base asset | via variants only | tavern_chair, wooden_staircase |
| **Variant** | a family member | `extends:` + public params | public params, metadata, budget, extra checks | tavern_stool, staircase variants |
| **Instance** | repetition inside one asset | part `array`/`mirror`, `repeat`/`mirror` ops, component-instance `array`/`mirror`, `share_instances` UVs | per-instance transforms and names | treads, balusters, legs, crate bands |

**Why "pack" was added (not planned):** in FRESH_AGENT_03 the agent needed shared scale and materials for
six structurally different assets. The only sharing mechanism was `extends`, so it wrote a parts-less
"kit" base that every asset extended, and modified `sw family` so a base without parts would pass. It
worked (zero drift) but collapsed two concepts: **inheritance of a design** and **membership of a set**.
A kit base also carries `FAMILY_NO_INTERFACE` on every member and would let members override the shared
palette. The pack makes membership explicit and drift impossible, and leaves `extends` for families.

Rules of thumb for agents:
- Same *structure* in several places → **component**.
- Several different assets that must look like one set → **pack**.
- One design with knobs → **family** (`interface`) + **variants**.
- The same thing several times in one asset → **instances** (`array`, `mirror`).

## Problem (v0.1)

`extends` deep-merged a base source. `tavern_stool` had to override the chair's
`rear_leg` ops, anchor and rotation, and repurposed `back_height` to mean
"leg length". A variant needed intimate knowledge of its base, and any change
to the base's construction broke variants silently (DESIGN_REVIEW §6).

## Alternatives considered

| Option | Verdict |
|---|---|
| Object-oriented inheritance with overridable methods | Solves the general problem we don't have; invites the same coupling |
| Copy-paste assets | No shared evolution; packs drift |
| Keep deep merge, add conventions | Conventions aren't enforced; agents follow what works |
| **Three explicit mechanisms: components, `enabled`, family interfaces** | Chosen |

## 1. Components: reusable sub-assemblies

`components/NAME.yaml` (repository-wide, or inside an asset directory):

```yaml
component: plank_top
params:            # PUBLIC: the only values an instance may set
  length: {value: 1.2, min: 0.3, max: 3.0}
  width: 0.7
  planks: 3
private:           # derived/internal: never settable from outside
  plank_w: (width - (planks - 1) * gap) / planks
parts:             # like asset parts; may reference only parts of this component
  plank: {...}
  batten: {...}
```

Instance in an asset:

```yaml
parts:
  top:
    component: plank_top
    with: {length: length, width: width, planks: 3}   # evaluated in the asset's params
    materials: {top: wood, under: wood_dark}           # map component material slots
    anchor: top
    position: [0, top_height, 0]                       # the whole group is placed like one part
```

- Parts become `top_plank_0`, `top_batten_left`, ...; the group is addressable
  as `top` in `measure`, `attach` and `checks`.
- Setting an unknown or private param → `COMPONENT_PRIVATE` (with the public list).
- A component part referencing anything outside the component → `SRC_REF`.
- Used by `tavern_table` and `tavern_bench`: one construction, two assets.

## 2. Optional structure: `enabled`

Any part or component instance can take `enabled: <bool | expression>`.
Disabled parts are not built. A reference from an enabled part to a disabled
one is an error that says so and suggests sharing the condition. Checks can be
conditional: `{expr: ..., when: has_back}`.

## 3. Family interfaces

A base asset declares its contract:

```yaml
interface:
  params: [seat_width, seat_depth, seat_height, leg, back_height, lean, has_back, rear_splay, wear]
```

A variant that `extends` it may set **only** those params (plus metadata,
budget, profile, style, materials, uv, collision). Its `checks` are
**added** to the family's checks. Anything else, including overriding parts
or a private param, raises `FAMILY_PRIVATE` with the hint "ask the base to
expose it". Bases without an interface still work (v0.1 behaviour) and get a
`FAMILY_NO_INTERFACE` info note.

`sw family tavern_chair` validates the base and every asset that extends it,
directly or transitively. It is the contract test to run after editing a base.

## Migration of the benchmarks

| Asset | v0.1 | now |
|---|---|---|
| tavern_stool | overrode `rear_leg` internals, deleted parts with `null`, repurposed `back_height` | 4 public params: `has_back: false`, sizes, `rear_splay: 3` |
| tavern_chair | no interface | interface of 10 params; `has_back` switches posts, rail and slats |
| tavern_table | planks + battens inline | `plank_top` component |
| tavern_bench | — | new: same component, different params |

## Not solved (yet)

- Components cannot nest other components (FRESH_AGENT_03 duplicated a foot-band recipe because of this).
- Component instances cannot take `measure:` queries (the agent re-derived a component's rail height by hand).
- ~~Component instances cannot be mirrored or arrayed~~: **fixed in Phase 6.**
- There is no versioning of interfaces; a base removing a public param breaks variants loudly (by design) but without a migration path.
