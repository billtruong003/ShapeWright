# The loop

```
understand -> plan parts -> write asset.yaml -> sw review -> LOOK at the sheet -> critique
     ^                                                                              |
     +---- sw snapshot (note + critique) <- change params / parts / ops <-----------+
                                 ... until done ... -> sw export
```

1. **Plan in parts, not polygons.** List semantic parts (seat, leg, rail), their real sizes in metres, and how they attach. Name every meaningful dimension as a param, and write design intent as `checks:`.
2. **Use the highest abstraction that works.** Prefer params, then placement (`anchor`/`attach`, `measure:`), then ops, then new shapes. Never write vertex lists.
3. **Look.** The review sheet is where proportions, silhouettes and material read are judged. Validators judge everything else.
4. **Critique specifically.** Write `back_slat: 3 thin slats read as modern -> 2 wide slats`, never "looks bad".
5. **Stop** when there are no errors, no significant critique is left and the constraints hold, or after the iteration budget (default 6 revisions).

Units are metres. +Y is up, the front faces +Z, and angles are in degrees. Assets rest on y = 0.
