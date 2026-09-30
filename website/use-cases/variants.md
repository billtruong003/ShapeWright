# One design, many variants

**`extends`: a variant that overrides only what differs.**

```bash
# run
sw new short_chair --from tavern_chair
sw validate short_chair --set seat_height=0.42
sw family tavern_chair
```

To keep the value, write it under `params:` in `assets/short_chair/asset.yaml` (`params: {seat_height: 0.42}`). `sw set` edits only params already written in that file; inherited ones are set in the variant's `params:`. `sw family` validates the base asset and every variant that extends it. If the base declares an `interface:`, variants may only set its public params. Structural overrides are refused with a hint.

**Seeded variants: many assets from one.** Params that declare `vary: [min, max]` produce seeded variants:

```bash
# run
sw variants rock --count 3 --seed 7
```

**Try without editing.** Any command that builds an asset takes `--set name=value[,name=value]`, which proves the asset stays valid across its parameter range:

```bash
# run
sw validate tavern_chair --set seat_height=0.43
sw validate tavern_chair --set seat_height=0.50
```
