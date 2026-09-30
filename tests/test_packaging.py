"""Phase 16: installed use (library + project roots), `sw init`, llms.txt, the wheel's bundled library."""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from shapewright import paths
from shapewright.assemble import ROOT, build
from shapewright.cli import main

STOOL = """shapewright: 0.1
asset: {name: stool}
pack: tiny
parts:
  seat:
    component: tiny_seat
    with: {w: w}
    materials: {oak: oak}
    position: [0, 0, 0]
"""


def _project(tmp_path: Path) -> Path:
    (tmp_path / "packs").mkdir()
    (tmp_path / "components").mkdir()
    (tmp_path / "assets" / "stool").mkdir(parents=True)
    (tmp_path / "packs" / "tiny.yaml").write_text(
        "shapewright: 0.1\npack: tiny\nparams: {w: 0.4}\nmaterials: {oak: {archetype: wood, color: '#8a5a34'}}\n")
    (tmp_path / "components" / "tiny_seat.yaml").write_text(
        "shapewright: 0.1\ncomponent: tiny_seat\nparams: {w: {value: 0.3}}\nparts:\n  top:\n    shape: {type: box, size: [w, 0.05, w]}\n    material: oak\n")
    (tmp_path / "assets" / "stool" / "asset.yaml").write_text(STOOL)
    return tmp_path


def test_project_packs_and_components_resolve_outside_the_library(tmp_path, monkeypatch):
    proj = _project(tmp_path)
    monkeypatch.chdir(proj)
    assert paths.project() == proj.resolve()
    a = build(proj / "assets" / "stool")
    assert abs(a.parts[0].mesh.bounds()[1][0] - 0.2) < 1e-6  # the project's pack param reached the project's component
    assert "tiny_seat" in paths.names("components") and "house_wall" in paths.names("components")  # project + library


def test_project_files_shadow_library_files_of_the_same_name(tmp_path, monkeypatch):
    (tmp_path / "packs").mkdir()
    (tmp_path / "packs" / "blacksmith.yaml").write_text("shapewright: 0.1\npack: blacksmith\ndoc: my override\n")
    monkeypatch.setenv("SW_PROJECT", str(tmp_path))
    assert paths.find("packs", "blacksmith") == tmp_path / "packs" / "blacksmith.yaml"
    assert paths.find("packs", "cozy_house") == ROOT / "packs" / "cozy_house.yaml"


def test_sw_init_marks_a_project_and_new_assets_go_there(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    assert (tmp_path / paths.MARKER).is_file() and (tmp_path / "assets").is_dir()
    sub = tmp_path / "deep" / "er"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert paths.project() == tmp_path.resolve()  # found by walking up to the marker
    assert main(["new", "my_barrel", "--from", "barrel"]) == 0
    assert (tmp_path / "assets" / "my_barrel" / "asset.yaml").exists()
    build(tmp_path / "assets" / "my_barrel")  # the variant resolves its library base


def test_llms_txt_is_current_and_its_example_builds(tmp_path):
    from shapewright.llms import llms_text

    committed = (ROOT / "llms.txt").read_text()
    assert committed == llms_text(), "llms.txt is stale: run `./sw caps --llms > llms.txt`"
    block = re.search(r"## Minimal asset\n\n(.*?)\n## ", committed, re.S).group(1)
    d = tmp_path / "stool"
    d.mkdir()
    (d / "asset.yaml").write_text("\n".join(line[4:] for line in block.splitlines()))
    assert len(build(d).parts) == 5


def test_the_wheel_bundles_the_library_without_build_products(tmp_path):
    res = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(tmp_path), str(ROOT)],
                         capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        pytest.skip(f"pip wheel unavailable: {res.stderr[-200:]}")
    names = zipfile.ZipFile(next(tmp_path.glob("*.whl"))).namelist()
    for need in ("shapewright/_lib/profiles/mobile_mid.yaml", "shapewright/_lib/packs/cozy_house.yaml",
                 "shapewright/_lib/components/house_wall.yaml", "shapewright/_lib/templates/asset.yaml",
                 "shapewright/_lib/assets/barrel/asset.yaml", "shapewright/workbench/index.html"):
        assert need in names, need
    assert not [n for n in names if "/export/" in n and "_lib" in n or "/history/" in n or "/.build/" in n]
