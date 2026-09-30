"""Packaging hook: ship the library (profiles, styles, packs, components, templates, example assets)
inside the wheel as `shapewright/_lib`, so `pip install shapewright` works without a clone.

Everything else is declared in pyproject.toml. Asset build products (export/, .build/, history/) are
left out; they are reproducible with `sw export`.
"""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
LIB_DIRS = ("profiles", "styles", "packs", "components", "templates")
SKIP = {"export", ".build", "history", "__pycache__"}


class BuildWithLibrary(build_py):
    def run(self):
        super().run()
        dest = Path(self.build_lib) / "shapewright" / "_lib"
        if dest.exists():
            shutil.rmtree(dest)
        for d in LIB_DIRS:
            if (ROOT / d).is_dir():
                shutil.copytree(ROOT / d, dest / d)
        for asset in sorted((ROOT / "assets").glob("*/asset.yaml")):
            src = asset.parent
            shutil.copytree(src, dest / "assets" / src.name, ignore=lambda _d, names: [n for n in names if n in SKIP])


setup(cmdclass={"build_py": BuildWithLibrary})
