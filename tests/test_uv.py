"""UV stability contract (docs/UV.md)."""

import shutil

import numpy as np

from shapewright.assemble import ROOT, build
from shapewright.surface import build_surface, write_lock
from shapewright.validate.run import run_validation


def copy_chair(tmp_path):
    d = tmp_path / "chair"
    d.mkdir()
    shutil.copy(ROOT / "assets" / "tavern_chair" / "asset.yaml", d / "asset.yaml")
    return d


def uvs(d):
    a = build(d)
    s = build_surface(a)
    return a, s, {n: sp.corner_uv for n, sp in s.parts.items()}


def edit(d, old, new):
    p = d / "asset.yaml"
    text = p.read_text()
    assert old in text
    p.write_text(text.replace(old, new))


def test_uvs_are_deterministic(tmp_path):
    d = copy_chair(tmp_path)
    _, _, u1 = uvs(d)
    _, _, u2 = uvs(d)
    assert all(np.array_equal(u1[k], u2[k]) for k in u1)


def test_locked_regions_confine_changes_to_the_edited_part(tmp_path):
    d = copy_chair(tmp_path)
    write_lock(build(d))
    _, _, before = uvs(d)
    edit(d, "slat_width:     0.09", "slat_width:     0.12")  # only the back slats change shape
    a, s, after = uvs(d)
    assert s.lock == "used"
    changed = {k for k in before if not np.array_equal(before[k], after[k])}
    assert changed == {"back_slat_0", "back_slat_1"}
    for k in changed:  # regenerated charts stay inside their locked rectangle
        r = s.regions[s.owners[k]]
        assert after[k][..., 0].min() >= r[0] - 1e-9 and after[k][..., 0].max() <= r[2] + 1e-9
    codes = {i["code"] for i in run_validation(a, s)["issues"]}
    assert "UV_REGION_REGENERATED" in codes and "UV_OVERLAP" not in codes


def test_without_lock_an_edit_moves_unrelated_parts(tmp_path):
    """Documents why the lock exists: area-proportional regions shift globally."""
    d = copy_chair(tmp_path)
    _, _, before = uvs(d)
    edit(d, "slat_width:     0.09", "slat_width:     0.12")
    _, _, after = uvs(d)
    moved = {k for k in before if not np.array_equal(before[k], after[k])} - {"back_slat_0", "back_slat_1"}
    assert moved  # parts nobody edited (the stretchers, with the current wear pattern)


def test_structural_change_makes_the_lock_stale(tmp_path):
    d = copy_chair(tmp_path)
    write_lock(build(d))
    edit(d, "  front_stretcher:\n", "  front_stretcher:\n    enabled: false\n")
    a, s, _ = uvs(d)
    assert s.lock == "stale" and "front_stretcher" in s.lock_notes
    assert "UV_LOCK_STALE" in {i["code"] for i in run_validation(a, s)["issues"]}


def test_shared_instance_uvs(tmp_path):
    d = copy_chair(tmp_path)
    edit(d, "    mirror: x\n    material: wood_dark\n\n  rear_leg:", "    mirror: x\n    uv: {share_instances: true}\n    material: wood_dark\n\n  rear_leg:")
    a, s, u = uvs(d)
    assert s.owners["front_leg_left"] == s.owners["front_leg_right"] == "front_leg*"
    assert np.array_equal(u["front_leg_left"], u["front_leg_right"][:, ::-1])  # mirrored twin: same charts, reversed winding
    r = run_validation(a, s)
    assert r["metrics"]["uv_overlap"] == 0  # intentional sharing is not an overlap error


def test_region_seams_cut_charts_at_region_boundaries(tmp_path):
    d = copy_chair(tmp_path)
    _, s0, _ = uvs(d)
    edit(d, "    anchor: top\n    position: [0, seat_height, 0]", "    uv: {seams: regions}\n    anchor: top\n    position: [0, seat_height, 0]")
    _, s1, _ = uvs(d)
    # every face region (top, bottom, sides, bevels) becomes its own chart, so UV vertices are split more
    assert len(np.unique(s1.parts["seat"].uvs, axis=0)) > len(np.unique(s0.parts["seat"].uvs, axis=0))
