import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def make_asset(tmp_path):
    """Write an asset source to a temp dir and return its path."""

    def _make(text: str, name: str = "t") -> Path:
        d = tmp_path / name
        d.mkdir(exist_ok=True)
        (d / "asset.yaml").write_text(text)
        return d / "asset.yaml"

    return _make
