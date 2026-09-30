# Reuse and composition

| mechanism | use it for | key |
|---|---|---|
| **params + expressions** | every meaningful dimension | `params:` |
| **components** | a reusable sub-assembly with public params (a wall, a timber, a plank top); they nest | `component:` |
| **asset instances** | a whole asset placed inside another (modules in a building) | `asset:` |
| **packs** | shared scale, construction params and materials for a set (read-only in members) | `pack:` |
| **extends** | variants of one design (optionally restricted by an `interface`) | `extends:` |
| **array / mirror** | repetition and symmetry, on parts and on instances | `array:`, `mirror:` |
| **measure** | place against real geometry built earlier (section, gap, bounds, anchor, ray), on parts and instances | `measure:` |
| **pivot** | a hinge: one animatable node for a part or a whole instance | `pivot:` |

See the format specification: [ASSET_FORMAT.md](https://github.com/billtruong003/ShapeWright/blob/main/docs/ASSET_FORMAT.md).
