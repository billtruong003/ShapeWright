"""Phase 20a: builds must not depend on the platform (CI runs Linux, Windows and macOS)."""

import os

from shapewright.cli import _extends_path


def test_extends_path_is_posix_and_survives_different_drives(tmp_path, monkeypatch):
    base, new = tmp_path / "lib" / "chair", tmp_path / "proj" / "assets" / "mine"
    assert _extends_path(base, new) == "../../../lib/chair"

    def cross_drive(*_):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", cross_drive)
    assert _extends_path(base, new) == base.resolve().as_posix()
