"""Phase 25a: presentation renders (beauty mode, turntable, presentation sheet, scale reference)."""

import numpy as np

from shapewright.assemble import ROOT, build
from shapewright.cli import main
from shapewright.render import beauty
from shapewright.render.views import MODES, render
from shapewright.surface import build_surface


def _barrel():
    a = build(ROOT / "assets" / "barrel")
    return a, build_surface(a)


def test_beauty_is_deterministic_and_tone_mapped():
    a, s = _barrel()
    one = np.asarray(render(a, s, "front_right", "beauty", 160))
    two = np.asarray(render(a, s, "front_right", "beauty", 160))
    assert "beauty" in MODES and np.array_equal(one, two)
    assert one.max() < 255  # tone mapped: no clipped highlights


def test_turntable_frames_share_one_framing(tmp_path):
    a, s = _barrel()
    frames = beauty.turntable(a, s, 4, 96)
    assert len(frames) == 4 and all(f.size == (96, 96) for f in frames)
    written = beauty.save_turntable(frames, tmp_path / "t.gif")
    assert written[0].stat().st_size > 1000


def test_present_sheet_picks_detailed_parts():
    a, s = _barrel()
    names = beauty._detail_parts(a)
    assert names and len(set(names)) == len(names)
    tris = {p.base: p.mesh.n_tris for p in a.parts}
    assert tris[names[0]] == max(tris.values())


def test_scale_reference_only_changes_side_views():
    a, s = _barrel()
    plain = np.asarray(render(a, s, "front", "clay", 160))
    ref = np.asarray(render(a, s, "front", "clay", 160, scale_ref=True))
    assert not np.array_equal(plain, ref)  # a figure and dimension lines were drawn (and the framing grew)
    assert np.array_equal(np.asarray(render(a, s, "front_right", "clay", 160, scale_ref=True)),
                          np.asarray(render(a, s, "front_right", "clay", 160)))


def test_cli_turntable_and_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    monkeypatch.setenv("SW_PROJECT", str(tmp_path))
    assert main(["render", "crate", "--turntable", "4", "--size", "128"]) == 0
    assert main(["render", "crate", "--present", "--size", "256"]) == 0
    out = tmp_path / ".build" / "library" / "crate" / ".build" / "renders"
    assert (out / "turntable.gif").is_file() and (out / "present.png").is_file()
