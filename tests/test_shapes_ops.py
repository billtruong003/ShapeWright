import numpy as np
import pytest
import yaml

from shapewright.assemble import apply_ops, build_shape
from shapewright.registry import OPS, SHAPES, load_builtin
from shapewright.source import Ctx

load_builtin()


def _closed(mesh):
    e = np.sort(np.concatenate([mesh.F[:, [0, 1]], mesh.F[:, [1, 2]], mesh.F[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return bool((counts == 2).all())


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_shape_example_is_closed_outward_and_deterministic(name):
    spec = SHAPES[name]
    assert spec.example, f"shape '{name}' needs an example (used by docs and this test)"
    raw = yaml.safe_load(spec.example)
    ctx = Ctx()
    m1 = build_shape(raw, {}, ctx, "t")
    m2 = build_shape(raw, {}, ctx, "t")
    assert not ctx.issues, ctx.issues
    assert m1.n_tris > 0
    assert _closed(m1), f"{name} is not closed"
    assert m1.volume() > 0, f"{name} is inside-out"
    assert np.array_equal(m1.V, m2.V) and np.array_equal(m1.F, m2.F)


BASE = {"type": "chamfer_box", "size": [0.4, 0.6, 0.3], "chamfer": 0.02}


@pytest.mark.parametrize("name", sorted(OPS))
def test_every_op_example_runs_and_keeps_surface_closed(name):
    spec = OPS[name]
    raw = yaml.safe_load(spec.example) if spec.example else {"type": name}
    ctx = Ctx()
    base = build_shape(BASE, {}, ctx, "t").recentered()
    if name in ("smooth", "noise", "decimate"):
        base = apply_ops(base, [{"type": "subdivide", "iterations": 2}], {}, ctx, "pre")
    if spec.params and any(p.required for p in spec.params) and not spec.example:
        pytest.skip("op without example and with required params")
    out = apply_ops(base, [raw], {}, ctx, "ops")
    assert not [i for i in ctx.issues if i.severity == "error"], ctx.issues
    assert out.n_tris > 0 and np.isfinite(out.V).all()
    assert _closed(out), f"{name} opened the surface"


def test_boolean_subtract_removes_volume():
    ctx = Ctx()
    base = build_shape({"type": "box", "size": [1, 1, 1]}, {}, ctx, "t")
    out = apply_ops(base, [{"type": "subtract", "shape": {"type": "box", "size": [0.5, 2, 0.5]}}], {}, ctx, "ops")
    assert abs(out.volume() - 0.75) < 1e-6


def test_unknown_param_suggests_fix():
    ctx = Ctx()
    assert build_shape({"type": "cylinder", "radius": 1, "heigth": 2}, {}, ctx, "p") is None
    msgs = " ".join(i.hint for i in ctx.issues)
    assert "height" in msgs


def test_limit_on_segments():
    ctx = Ctx()
    assert build_shape({"type": "cylinder", "radius": 1, "height": 1, "segments": 100000}, {}, ctx, "p") is None
    assert any(i.code == "SRC_RANGE" for i in ctx.issues)
