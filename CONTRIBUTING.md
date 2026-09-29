# Contributing

Contributors include humans and agents. The rules are the same.

## Setup

```bash
pip install -r requirements.txt
python3 -m pytest -q          # must pass before and after your change
./sw bench                    # every benchmark asset must stay PASS/WARN
```

## Extension seams

### A new shape (generator)

```python
# shapewright/ops/shapes.py (or a new module imported by registry.load_builtin)
@shape("wedge", "Right-angle wedge (ramps, roof pieces).",
       [Param("size", "vec3", doc="[x, y, z]")],
       example="{type: wedge, size: [0.4, 0.2, 0.3]}")
def wedge(a, b):
    ...
    return _finish(Mesh(V, F))   # closed, welded, outward
```

Requirements: returns a **closed, outward-wound** mesh (use `_finish`); every
parameter is typed with a doc string; an `example` is mandatory, because
`tests/test_shapes_ops.py` builds it and checks closedness, orientation and
determinism. Use `LIMITS` for any count the user controls.

### A new op (modifier)

```python
@op("bulge", "Push the middle outward along an axis.", [Param("amount", "num", doc="metres")],
    category="deform", example="{type: bulge, amount: 0.02}")
def bulge(mesh, a, b):
    return Mesh(new_vertices, mesh.F)
```

Ops receive a part-local mesh centred on its bounding box. Keep the surface
closed. Use `b.build_shape(raw, "shape")` for nested tool shapes.

### A new validator

```python
@validator("seat_slope", "intent", "Seats must not tilt more than 5 degrees.", ("INT_SEAT_SLOPE",))
def seat_slope(asset, surface, metrics):
    return [Issue("INT_SEAT_SLOPE", "warning", "...", where="seat", layer="intent", hint="...")]
```

Add a **defect-injection test** in `tests/test_validation.py` and document the
code in `docs/VALIDATION.md`.

### Views, modes, profiles, styles
- Views and modes: the `VIEWS`/`MODES` tables in `shapewright/render/views.py`.
  Keep them deterministic (no time or random state).
- Profiles and styles are YAML files in `profiles/` and `styles/`, and they
  appear in `sw caps` automatically.

### Exporters
A function `(Asset, Surface, Path) -> dict` in `shapewright/export/`, a CLI
flag, and a round-trip test.

## Rules

- **Determinism:** no wall-clock, unseeded randomness or dict-order-dependent
  output in geometry, renders or exports.
- **Golden geometry:** if you intentionally change modelling behaviour, run
  `python3 tests/update_golden.py` and explain the change in the commit message.
- **Dependencies:** permissive licences only (BSD, MIT, Apache-2.0, zlib, ISC,
  HPND). Record new ones in `docs/RESEARCH.md#licences` and `requirements.txt`
  with the reason.
- **Agent ergonomics:** errors must say *where* (part or source path) and *what
  to change*. Output stays compact; `--json` is for the full detail.
- **Security:** asset sources never execute code. Do not add `eval`, imports,
  file or network access, or subprocesses to anything reachable from a source.
- **Docs are runtime:** update AGENTS.md or the relevant doc when behaviour
  changes. `sw caps` is generated, so keep `doc=` strings accurate.
