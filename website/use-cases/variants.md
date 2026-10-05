# One design, many variants

**`extends`: a variant that overrides only what differs.**

```bash
# run
sw new short_chair --from tavern_chair
sw validate short_chair --set seat_height=0.44
sw set short_chair seat_height=0.44
sw family tavern_chair
```

`--set` tries a value without editing anything. `sw set` writes it: on a variant, it adds the inherited param under the variant's own `params:` (a pack's params stay read-only). `sw family` validates the base asset and every variant that extends it. If the base declares an `interface:`, variants may only set its public params. Structural overrides are refused with a hint.

**Seeded variants: many assets from one.** Params that declare `vary: [min, max]` produce seeded variants:

```bash
# run
sw variants rock --count 3 --seed 7
```

**Try without editing.** Any command that builds an asset takes `--set name=value[,name=value]`, which proves the asset stays valid across its parameter range:

```bash
# run
sw validate tavern_chair --set seat_height=0.42
sw validate tavern_chair --set seat_height=0.50
```
