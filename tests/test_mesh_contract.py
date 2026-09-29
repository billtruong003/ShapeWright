"""The mesh attribute contract (docs/MESH_MODEL.md), tested against every registered op.

These tests check *behaviour classes*, not example outputs: an op that declares
`preserve` must not touch topology or attributes; `refine` must interpolate;
`rebuild` must keep provenance and invalidate corners; `resample` must transfer.
"""

import numpy as np
import pytest
import yaml

from shapewright.assemble import apply_ops, build_geometry
from shapewright.mesh import POLICY, AttributeError_, Mesh, concat
from shapewright.registry import OPS, load_builtin
from shapewright.source import Ctx

load_builtin()


def attributed_mesh() -> Mesh:
    ctx = Ctx()
    m = build_geometry({"type": "chamfer_box", "size": [0.4, 0.6, 0.3], "chamfer": 0.03}, {}, ctx, "base").recentered()
    m = apply_ops(m, [{"type": "subdivide", "iterations": 1}], {}, ctx, "pre")
    m.set_label("material", "wood")
    m.set_vertex("color", np.c_[np.linspace(0, 1, len(m.V))[:, None].repeat(3, 1), np.ones(len(m.V))])
    m.set_corner("uv", m.V[m.F][:, :, :2])
    assert not ctx.issues
    return m


def valid_labels(m: Mesh):
    for k, codes in m.fattr.items():
        assert len(codes) == m.n_tris
        if k in m.labels:
            assert codes.min() >= -1 and codes.max() < len(m.labels[k])


@pytest.mark.parametrize("name", sorted(OPS))
def test_every_op_obeys_its_declared_attribute_policy(name):
    spec = OPS[name]
    assert spec.topology in POLICY and spec.topology != "generate", f"{name} must declare a topology class"
    base = attributed_mesh()
    ctx = Ctx()
    out = apply_ops(base, [yaml.safe_load(spec.example)], {}, ctx, "ops")
    assert out is not None, ctx.issues
    valid_labels(out)
    assert set(base.fattr) <= set(out.fattr), "face attributes must never disappear"
    if spec.topology == "preserve":
        assert np.array_equal(out.F, base.F)
        for k in base.fattr:
            assert np.array_equal(out.fattr[k], base.fattr[k])
        for k in base.vattr:
            assert np.array_equal(out.vattr[k], base.vattr[k])
        assert "uv" in out.cattr and "uv" not in out.invalidated
    elif spec.topology == "refine":
        assert out.n_tris % base.n_tris == 0 and "uv" in out.cattr and "uv" not in out.invalidated
        assert (out.fattr["origin"] >= 0).all()
    elif spec.topology == "rebuild":
        assert (out.fattr["origin"] >= 0).all(), "rebuild ops must give every face a provenance"
        assert "color" in out.vattr and np.isfinite(out.vattr["color"]).all()
        if out.n_tris != 2 * base.n_tris or name not in ("mirror", "repeat"):
            assert "uv" in out.invalidated or "uv" in out.cattr
    elif spec.topology == "resample":
        assert "uv" in out.invalidated
        assert (out.fattr["origin"] >= 0).all() and set(out.label_values("material")) == {"wood"}


def test_boolean_tool_faces_keep_tool_provenance_and_material():
    ctx = Ctx()
    m = build_geometry({"type": "boolean", "operation": "difference",
                        "base": {"type": "box", "size": [1, 1, 1], "material": "wood"},
                        "tools": [{"type": "cylinder", "radius": 0.2, "height": 2, "material": "iron", "ops": [{"type": "taper", "scale": 0.5}]}]},
                       {}, ctx, "parts.x.shape", materials={"wood": {}, "iron": {}})
    assert not ctx.issues, ctx.issues
    origins = set(m.label_values("origin"))
    assert origins == {"parts.x.shape.base", "parts.x.shape.tools[0]"}
    tool_faces = m.label_values("origin") == "parts.x.shape.tools[0]"
    assert set(m.label_values("material")[tool_faces]) == {"iron"}
    assert set(m.label_values("material")[~tool_faces]) == {"wood"}


def test_trim_marks_new_faces_as_cut():
    ctx = Ctx()
    m = build_geometry({"type": "icosphere", "radius": 0.3, "subdivisions": 2, "ops": [{"type": "flat_bottom", "fraction": 0.3}]}, {}, ctx, "p")
    assert "cut" in set(m.label_values("region"))
    assert (m.fattr["origin"] >= 0).all()


def test_mirror_transform_keeps_corners_attached_to_vertices():
    m = attributed_mesh()
    M = np.diag([-1.0, 1, 1, 1])
    t = m.transformed(M)
    # corner uv was set from vertex x,y; after mirroring, corners must still match their vertices' original (x, y)
    assert np.allclose(t.cattr["uv"][..., 0], -t.V[t.F][..., 0])
    assert np.allclose(t.cattr["uv"][..., 1], t.V[t.F][..., 1])
    assert t.volume() > 0


def test_subdivide_interpolates_corner_attributes():
    m = attributed_mesh()
    ctx = Ctx()
    s = apply_ops(m, [{"type": "subdivide", "iterations": 1}], {}, ctx, "o")
    assert np.allclose(s.cattr["uv"], s.V[s.F][:, :, :2])  # uv = position.xy is linear, so interpolation is exact


def test_concat_remaps_label_tables():
    a = Mesh(np.eye(3), [[0, 1, 2]]).set_label("material", "wood")
    b = Mesh(np.eye(3), [[0, 1, 2]]).set_label("material", "iron")
    c = concat([a, b])
    assert list(c.label_values("material")) == ["wood", "iron"]
    assert list(concat([b, a]).label_values("material")) == ["iron", "wood"]


def test_weld_respects_vertex_attributes():
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]], float)
    m = Mesh(V, [[0, 1, 2], [3, 2, 1]]).set_vertex("color", [[1, 0, 0, 1], [1, 1, 1, 1], [1, 1, 1, 1], [0, 0, 1, 1]])
    assert len(m.merged().V) == 4  # same position, different colour: not welded
    m.vattr["color"][3] = m.vattr["color"][0]
    assert len(m.merged().V) == 3


def test_schema_is_closed():
    m = Mesh(np.eye(3), [[0, 1, 2]])
    with pytest.raises(AttributeError_):
        m.set_vertex("normal", [0, 0, 1])  # derived data is never stored
    with pytest.raises(AttributeError_):
        Mesh(np.eye(3), [[0, 1, 2]], fattr={"whatever": np.zeros(1)})
