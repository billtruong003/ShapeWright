"""Benchmark assets: must validate cleanly, be deterministic and survive export."""

import hashlib
import json
import struct
from pathlib import Path

import pytest

from shapewright.assemble import ROOT, build
from shapewright.export.gltf import write_glb
from shapewright.export.verify import roundtrip
from shapewright.mesh import concat, geometry_hash
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

ASSETS = sorted(p.parent.name for p in (ROOT / "assets").glob("*/asset.yaml"))
GOLDEN = Path(__file__).parent / "golden.json"


@pytest.mark.parametrize("name", ASSETS)
def test_benchmark_asset_has_no_errors(name):
    a = build(ROOT / "assets" / name)
    r = run_validation(a, build_surface(a))
    assert r["status"] in ("PASS", "WARN"), [i for i in r["issues"] if i["severity"] == "error"]


@pytest.mark.parametrize("name", ASSETS)
def test_geometry_matches_golden(name):
    """Refactors must not silently change modelling behaviour.
    If a change is intentional: python tests/update_golden.py"""
    golden = json.loads(GOLDEN.read_text())
    a = build(ROOT / "assets" / name)
    h = geometry_hash(concat([p.mesh for p in a.parts]))
    assert golden.get(name) == h, f"{name}: geometry changed ({golden.get(name)} -> {h})"


def test_export_is_byte_deterministic_and_roundtrips(tmp_path):
    a = build(ROOT / "assets" / "tavern_chair")
    p1, p2 = tmp_path / "a.glb", tmp_path / "b.glb"
    write_glb(a, build_surface(a), p1)
    write_glb(build(ROOT / "assets" / "tavern_chair"), build_surface(a), p2)
    assert hashlib.sha256(p1.read_bytes()).digest() == hashlib.sha256(p2.read_bytes()).digest()
    assert roundtrip(a, p1) == []
    blob = p1.read_bytes()
    n = struct.unpack("<I", blob[12:16])[0]
    gltf = json.loads(blob[20:20 + n])
    names = {node["name"] for node in gltf["nodes"]}
    assert {"seat", "front_leg_left", "front_leg_right", "SOCKET_sit_point"} <= names
    assert gltf["nodes"][0]["extras"]["shapewright"]["units"] == "m"


def test_extends_inherits_and_deletes():
    stool = build(ROOT / "assets" / "tavern_stool")
    names = {p.base for p in stool.parts}
    assert "top_rail" not in names and "seat" in names
    assert stool.materials.keys() == build(ROOT / "assets" / "tavern_chair").materials.keys()
