"""Phase 22: the native organic kernel (`blend` shape, shapewright/organic.py)."""

import time

import numpy as np
import pytest

from shapewright import organic
from shapewright.assemble import ROOT, build
from shapewright.mesh import geometry_hash
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

CREATURES = ("chibi_fox", "creature_slime", "creature_mushroom")


def _edges_ok(m):
    E = np.sort(np.concatenate([m.F[:, [0, 1]], m.F[:, [1, 2]], m.F[:, [2, 0]]]), axis=1)
    _, c = np.unique(E, axis=0, return_counts=True)
    return bool((c == 2).all())


def _blend_asset(tmp_path, items, extra="", name="blob"):
    d = tmp_path / name
    d.mkdir()
    (d / "asset.yaml").write_text(
        f"shapewright: 0.1\nasset: {{name: {name}, placement: free}}\nmaterials: {{m: {{base_color: '#888888'}}, w: {{base_color: '#eeeeee'}}}}\n"
        f"parts:\n  body: {{material: m, origin: keep, shape: {{type: blend, {extra}items: {items}}}}}\n")
    return d


def test_marching_tets_closes_a_sphere_and_winds_it_outward():
    h = 0.02
    ax = np.arange(-0.3, 0.3 + h, h)
    G = np.stack(np.meshgrid(ax, ax, ax, indexing="ij"), -1)
    F = np.linalg.norm(G, axis=-1) - 0.2
    m = organic.marching_tets(F, np.array([ax[0]] * 3), h)
    assert _edges_ok(m)
    assert m.volume() == pytest.approx(4 / 3 * np.pi * 0.2 ** 3, rel=0.02)  # positive: wound outward


@pytest.mark.parametrize("name", CREATURES)
def test_creatures_are_one_closed_mesh_within_budget_and_fast(name):
    t0 = time.perf_counter()
    a = build(ROOT / "assets" / name)
    took = time.perf_counter() - t0
    assert len(a.parts) == 1 and _edges_ok(a.parts[0].mesh)
    r = run_validation(a, build_surface(a))
    assert r["status"] == "PASS", [i for i in r["issues"] if i["severity"] != "info"]
    assert took < 10  # G1 gate: under 10 s each


def test_blend_is_deterministic(tmp_path):
    d = _blend_asset(tmp_path, "[{sdf: sphere, radius: 0.2}, {sdf: capsule, a: [0, 0, 0], b: [0.3, 0.2, 0], radius: 0.06}]")
    assert geometry_hash(build(d).parts[0].mesh) == geometry_hash(build(d).parts[0].mesh)


def test_smooth_union_rounds_the_seam_and_subtract_carves(tmp_path):
    hard = build(_blend_asset(tmp_path, "[{sdf: sphere, radius: 0.15}, {sdf: sphere, center: [0.2, 0, 0], radius: 0.15}]",
                              "radius: 0, ", "hard")).parts[0].mesh
    soft = build(_blend_asset(tmp_path, "[{sdf: sphere, radius: 0.15}, {sdf: sphere, center: [0.2, 0, 0], radius: 0.15}]",
                              "radius: 0.08, ", "soft")).parts[0].mesh
    assert soft.volume() > hard.volume() * 1.01  # the smooth union fills the crease between the spheres
    cut = build(_blend_asset(tmp_path, "[{sdf: sphere, radius: 0.2}, {sdf: sphere, center: [0, 0.2, 0], radius: 0.1, op: subtract}]",
                             "", "cut")).parts[0].mesh
    full = build(_blend_asset(tmp_path, "[{sdf: sphere, radius: 0.2}]", "", "full")).parts[0].mesh
    assert cut.volume() < full.volume() * 0.97


def test_mirror_material_and_ground(tmp_path):
    d = _blend_asset(tmp_path, "[{sdf: ellipsoid, center: [0, 0.2, 0], radii: [0.2, 0.25, 0.15]}, "
                               "{sdf: sphere, center: [0.18, 0.3, 0], radius: 0.07, mirror: x, material: w}]", "ground: true, ")
    m = build(d).parts[0].mesh
    lo, hi = m.bounds()
    assert lo[1] == pytest.approx(0.0, abs=1e-6)  # cut flat on the floor
    assert lo[0] == pytest.approx(-hi[0], abs=0.01)  # the mirrored pair makes it symmetric
    mats = m.label_values("material")
    assert (mats == "w").sum() > 20 and (mats == None).sum() > (mats == "w").sum()  # noqa: E711


def test_bad_items_are_explained(tmp_path):
    from shapewright.report import SourceError

    with pytest.raises(SourceError, match="Did you mean 'ellipsoid'"):
        build(_blend_asset(tmp_path, "[{sdf: elipsoid, radii: [0.1, 0.1, 0.1]}]"))
    with pytest.raises(SourceError, match="first item must be a union"):
        build(_blend_asset(tmp_path, "[{sdf: sphere, radius: 0.1, op: subtract}]", name="sub"))


def test_a_crevice_too_narrow_for_the_budget_is_reported(tmp_path):
    # an eye in a socket: the gap between them is far narrower than the edges a 600-triangle budget allows
    d = _blend_asset(tmp_path, "[{sdf: sphere, center: [0, 0.2, 0], radius: 0.2}, "
                               "{sdf: sphere, center: [0, 0.2, 0.19], radius: 0.06, op: subtract, blend: 0.005}, "
                               "{sdf: sphere, center: [0, 0.2, 0.175], radius: 0.05, blend: 0.002}]", "triangles: 600, ")
    a = build(d)
    codes = {i.code for i in a.issues}
    assert _edges_ok(a.parts[0].mesh) or "GEO_BLEND_PINCHED" in codes  # clean, or the pinch is reported with its place
