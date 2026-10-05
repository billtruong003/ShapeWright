"""Phase 20a: builds must not depend on the platform (CI runs Linux and Windows)."""

import os

from shapewright.cli import _extends_path


def test_extends_path_is_posix_and_survives_different_drives(tmp_path, monkeypatch):
    base, new = tmp_path / "lib" / "chair", tmp_path / "proj" / "assets" / "mine"
    assert _extends_path(base, new) == "../../../lib/chair"

    def cross_drive(*_):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", cross_drive)
    assert _extends_path(base, new) == base.resolve().as_posix()


def test_jitter_depends_on_positions_not_vertex_order():
    # macOS arm64 rounded one coordinate a bit differently, merged() sorted vertices differently, and index-keyed jitter
    # put the wear on other vertices (tavern_chair legs 0.8 % volume). Offsets are now a function of position.
    import numpy as np

    from shapewright import backend
    from shapewright.ops.modifiers import jitter

    m = backend.box([0.4, 0.3, 0.2])
    perm = np.random.default_rng(1).permutation(len(m.V))
    shuffled = m.remapped(m.V[perm], np.argsort(perm)[m.F], np.arange(len(m.F)), vert_src=perm)
    a = jitter(m, {"amount": 0.005, "seed": 4}, None)
    b = jitter(shuffled, {"amount": 0.005, "seed": 4}, None)
    assert np.array_equal(a.V[perm], b.V)
    off = a.V - m.V
    assert np.abs(off).max() <= 0.005 + 1e-12 and np.abs(off).max() > 0.002  # bounded by amount, and not trivially small
