"""Benchmark assets: must validate cleanly, be deterministic and survive export."""

import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

from shapewright.assemble import ROOT, build
from shapewright.export.gltf import write_glb
from shapewright.export.verify import roundtrip
from shapewright.mesh import concat, geometry_hash, geometry_signature
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

sys.path.insert(0, str(Path(__file__).parent))
import golden  # noqa: E402

ASSETS = sorted(p.parent.name for p in (ROOT / "assets").glob("*/asset.yaml"))


@pytest.mark.parametrize("name", ASSETS)
def test_benchmark_asset_has_no_errors(name):
    a = build(ROOT / "assets" / name)
    r = run_validation(a, build_surface(a))
    assert r["status"] in ("PASS", "WARN"), [i for i in r["issues"] if i["severity"] == "error"]


@pytest.mark.parametrize("name", ASSETS)
def test_geometry_matches_golden(name):
    """Refactors must not silently change modelling behaviour.
    If a change is intentional: python tests/update_golden.py"""
    entry = golden.load().get(name)
    assert entry, f"{name}: new asset has no golden record yet; record it with python tests/update_golden.py"
    mesh = concat([p.mesh for p in build(ROOT / "assets" / name).parts])
    diff = golden.sig_diff(geometry_signature(mesh), entry["sig"])
    assert not diff, f"{name}: geometry changed: {'; '.join(diff)}; if intended: python tests/update_golden.py"
    recorded = entry["hash"].get(golden.platform_key())
    if recorded is None:  # no exact hash from this OS yet: the signature above is the check
        return
    h = geometry_hash(mesh)
    assert recorded == h, (f"{name}: geometry changed below the signature tolerance ({recorded} -> {h} on "
                           f"{golden.platform_key()}); if intended: python tests/update_golden.py")


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
