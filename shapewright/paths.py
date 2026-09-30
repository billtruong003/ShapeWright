"""Where Shapewright looks for things: the bundled library and the user's project.

Library (`LIB`): the profiles, styles, packs, components, templates and example assets that ship with
Shapewright. In a source checkout it is the repository root; in an installed wheel it is the `_lib`
folder packaged next to this module (setup.py copies it in).

Project (`project()`): the user's workspace, when there is one. It is, in order:
  - `$SW_PROJECT`;
  - the nearest folder at or above the working directory that holds a `shapewright.yaml` marker
    (`sw init` writes one);
  - the working directory, when it has an `assets/` folder.
Project files shadow library files of the same name, so a project can override a library pack or
component without editing the installation.
"""

from __future__ import annotations

import os
from pathlib import Path

_PKG = Path(__file__).resolve().parent
_CHECKOUT = _PKG.parent
LIB = _CHECKOUT if (_CHECKOUT / "profiles").is_dir() else _PKG / "_lib"
MARKER = "shapewright.yaml"
KINDS = ("profiles", "styles", "packs", "components")


def project() -> Path | None:
    env = os.environ.get("SW_PROJECT")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        if (d / MARKER).is_file():
            return d
    return cwd if (cwd / "assets").is_dir() else None


def roots() -> list[Path]:
    """Search order for named files: the project first, then the library."""
    out = []
    for r in (project(), LIB):
        if r is not None and r.resolve() not in [o.resolve() for o in out]:
            out.append(r)
    return out


def find(kind: str, name: str) -> Path | None:
    for r in roots():
        p = r / kind / f"{name}.yaml"
        if p.exists():
            return p
    return None


def files(kind: str) -> list[Path]:
    """Every `<kind>/*.yaml`, project files shadowing library files with the same stem."""
    seen: dict[str, Path] = {}
    for r in roots():
        for p in sorted((r / kind).glob("*.yaml")):
            seen.setdefault(p.stem, p)
    return [seen[k] for k in sorted(seen)]


def names(kind: str) -> list[str]:
    return [p.stem for p in files(kind)]


def asset_dirs() -> list[Path]:
    """Folders that hold assets, project first."""
    out = [r / "assets" for r in roots() if (r / "assets").is_dir()]
    cwd_assets = Path.cwd() / "assets"
    if cwd_assets.is_dir() and cwd_assets.resolve() not in [o.resolve() for o in out]:
        out.insert(0, cwd_assets)
    return out


def assets_home() -> Path:
    """Where new assets go: the project's assets/, else the library's (a source checkout)."""
    p = project()
    return (p or LIB) / "assets"


def build_dir() -> Path:
    return (project() or LIB) / ".build"
