# By hand: the CLI and the workbench

```bash
sw init my_assets && cd my_assets
sw brief "a wooden barrel for a mobile game"   # closest example, budgets, rules, vocabulary
sw new my_barrel --from barrel                 # start from the example
sw review my_barrel                            # validation + assets/my_barrel/.build/sheet.png
sw set my_barrel height=0.93                   # change a param in the source (comments kept)
sw export my_barrel --target godot
sw workbench --open                            # a local page: every button runs, and shows, one sw command
```

`sw caps` lists the whole vocabulary. `sw doc NAME` explains any shape, op, profile, pack, component or issue code.
