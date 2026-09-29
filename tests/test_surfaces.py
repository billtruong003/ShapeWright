"""Surface system contracts (docs/SURFACES.md): recipes, bake, semantic edits, export, validation."""

import json
import struct

import numpy as np
import pytest
from PIL import Image

from shapewright.assemble import ROOT, build
from shapewright.bake import bake, textures_for
from shapewright.export.gltf import write_glb
from shapewright.export.verify import roundtrip
from shapewright.report import SourceError
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

ASSET = """
profile: mobile_mid
materials:
  oak: {{archetype: wood, color: "{color}", grain_strength: {grain}, grain_scale: 0.02, edge_wear: 0.3}}
  iron: {{archetype: metal, color: "#8a8f96", edge_wear: 0.5}}
parts:
  plank: {{shape: {{type: chamfer_box, size: [0.8, 0.06, 0.25], chamfer: 0.012}}, anchor: bottom, position: [0, 0.1, 0], material: oak}}
  post: {{shape: {{type: chamfer_box, size: [0.08, 0.5, 0.08], chamfer: 0.01}}, anchor: bottom, position: [0.3, 0, 0], mirror: x, material: oak}}
  band: {{shape: {{type: ring, radius: 0.06, thickness: 0.015, height: 0.03}}, position: [0.3, 0.35, 0], mirror: x, material: iron}}
"""


def make(make_asset, name="t", color="#8a5a36", grain=0.4, extra=""):
    return make_asset(ASSET.format(color=color, grain=grain) + extra, name)


def baked(p):
    a = build(p)
    s = build_surface(a)
    return a, s, bake(a, s)


def test_flat_materials_stay_texture_free():
    a = build(ROOT / "assets" / "tavern_chair")
    s = build_surface(a)
    assert bake(a, s) is None


def test_bake_is_deterministic(make_asset):
    _, _, t1 = baked(make(make_asset))
    _, _, t2 = baked(make(make_asset, "t2"))
    assert np.array_equal(t1.base, t2.base) and np.array_equal(t1.orm, t2.orm)
    assert set(t1.lifecycle.values()) == {"DERIVED"}


def _material_texels(a, s, t, material):
    vals = []
    for p in a.parts:
        if p.material == material:
            uv = s.parts[p.name].corner_uv.mean(1)
            x = np.clip((uv[:, 0] * t.resolution).astype(int), 0, t.resolution - 1)
            y = np.clip(((1 - uv[:, 1]) * t.resolution).astype(int), 0, t.resolution - 1)
            vals.append(t.base[y, x])
    return np.concatenate(vals)


def test_semantic_edits_move_the_texture_in_the_intended_direction(make_asset):
    oak_strong = _material_texels(*baked(make(make_asset, "a", grain=0.8)), "oak").std(0).mean()
    oak_none = _material_texels(*baked(make(make_asset, "b", grain=0.0)), "oak").std(0).mean()
    assert oak_strong > oak_none  # "less grain" reduces variation
    warm = baked(make(make_asset, "c", color="#a0582a"))
    cool = baked(make(make_asset, "d", color="#6a5a50"))
    rw = _material_texels(*warm, "oak").mean(0)
    rc = _material_texels(*cool, "oak").mean(0)
    assert (rw[0] - rw[2]) > (rc[0] - rc[2])  # "warmer" = more red than blue


def test_material_instances_and_errors(make_asset):
    p = make(make_asset, extra="  # appended\n").parent / "asset.yaml"
    text = p.read_text().replace("  iron:", "  oak_light: {use: oak, color: \"#b08050\"}\n  iron:")
    p.write_text(text)
    a = build(p)
    assert a.materials["oak_light"]["archetype"] == "wood" and a.materials["oak_light"]["instance_of"] == "oak"
    assert a.materials["oak_light"]["args"]["grain_strength"] == 0.4
    for bad, code in [('archetype: wod', "SRC_SCHEMA"), ('grain_strenght: 0.2', "SRC_SCHEMA"), ('use: nope', "SRC_REF")]:
        p.write_text(text.replace('oak_light: {use: oak, color: "#b08050"}', f'oak_light: {{{bad}}}'))
        with pytest.raises(SourceError) as e:
            build(p)
        assert any(i.code == code and (i.hint or "") for i in e.value.issues), e.value.issues


def test_resolution_follows_texel_density_and_budget(make_asset):
    lo = baked(make(make_asset, "lo", extra="uv: {texel_density: 128}\n"))[2]
    hi = baked(make(make_asset, "hi", extra="uv: {texel_density: 512}\n"))[2]
    assert hi.resolution > lo.resolution
    a, s, capped = baked(make(make_asset, "cap", extra="uv: {texel_density: 4096}\nbudget: {texture_size: 256}\n"))
    assert capped.resolution == 256 and capped.needed_resolution > 256
    assert "TEX_DENSITY_BELOW_TARGET" in {i["code"] for i in run_validation(a, s)["issues"]}


def test_image_layer_and_sandbox(make_asset):
    p = make(make_asset)
    (p.parent / "textures").mkdir()
    Image.fromarray(np.full((8, 8, 3), [0, 0, 255], np.uint8)).save(p.parent / "textures" / "blue.png")
    text = p.read_text().replace("edge_wear: 0.3}", "edge_wear: 0.3, layers: [{image: textures/blue.png, opacity: 1.0}]}")
    p.write_text(text)
    a, s, t = baked(p)
    oak = _material_texels(a, s, t, "oak")
    assert oak[:, 2].mean() > 0.9 and oak[:, 0].mean() < 0.1  # fully covered by the blue layer
    p.write_text(text.replace("textures/blue.png", "../../etc/x.png"))
    a = build(p)
    codes = {i["code"] for i in run_validation(a, build_surface(a))["issues"]}
    assert "TEX_IMAGE_INVALID" in codes


def test_textured_glb_embeds_textures_and_recipe(make_asset, tmp_path):
    a, s, _ = baked(make(make_asset))
    out = tmp_path / "t.glb"
    write_glb(a, s, out)
    blob = out.read_bytes()
    n = struct.unpack("<I", blob[12:16])[0]
    g = json.loads(blob[20:20 + n])
    assert len(g["images"]) == 2 and all(im["mimeType"] == "image/png" for im in g["images"])
    oak = next(m for m in g["materials"] if m["name"] == "oak")
    assert oak["pbrMetallicRoughness"]["baseColorTexture"]["index"] == 0
    assert oak["extras"]["shapewright_material"]["archetype"] == "wood"
    assert roundtrip(a, out) == []


def test_multi_material_part_survives_roundtrip(make_asset, tmp_path):
    # found by FRESH_AGENT_04: a boolean cut whose faces keep the tool's material -> one node, two primitives
    extra = ("  plate: {shape: {type: chamfer_box, size: [0.2, 0.2, 0.03], ops: [{type: subtract, "
             "shape: {type: cylinder, radius: 0.03, height: 0.03, rotate: [90, 0, 0], material: oak}, position: [0, 0, 0.015]}]}, "
             "anchor: bottom, position: [0, 0.16, 0], material: iron}\n")
    a, s, _ = baked(make(make_asset, extra=extra))
    out = tmp_path / "m.glb"
    write_glb(a, s, out)
    blob = out.read_bytes()
    g = json.loads(blob[20:20 + struct.unpack("<I", blob[12:16])[0]])
    assert len(next(m for m in g["meshes"] if m["name"] == "plate")["primitives"]) == 2
    assert roundtrip(a, out) == []


def test_grime_darkens_the_lower_band_and_creases(make_asset):
    a0, s0, clean = baked(make(make_asset, "clean"))
    p = make(make_asset, "dirty")
    p.write_text(p.read_text().replace("edge_wear: 0.3}", "edge_wear: 0.3, grime: 1.0, grime_height: 0.2}"))
    a1, s1, dirty = baked(p)

    def band(a, s, t, lo, hi):  # mean luminance of post texels in a height band
        uv, P = [], []
        for part in a.parts:
            if part.base == "post":
                m = part.mesh
                uv.append(s.parts[part.name].corner_uv.mean(1))
                P.append(m.V[m.F].mean(1))
        uv, P = np.concatenate(uv), np.concatenate(P)
        sel = (P[:, 1] >= lo) & (P[:, 1] < hi)
        x = np.clip((uv[sel, 0] * t.resolution).astype(int), 0, t.resolution - 1)
        y = np.clip(((1 - uv[sel, 1]) * t.resolution).astype(int), 0, t.resolution - 1)
        return t.base[y, x].mean()

    assert band(a1, s1, dirty, 0, 0.08) < band(a0, s0, clean, 0, 0.08) - 0.03  # dirt near the ground
    assert abs(band(a1, s1, dirty, 0.4, 0.5) - band(a0, s0, clean, 0.4, 0.5)) < 0.02  # high up: unchanged


def test_pbr_plausibility_warnings(make_asset):
    p = make(make_asset, color="#0a0806")
    text = p.read_text().replace('iron: {archetype: metal, color: "#8a8f96"', 'iron: {archetype: metal, color: "#202224"')
    p.write_text(text)
    a = build(p)
    codes = {i["code"] for i in run_validation(a, build_surface(a))["issues"]}
    assert {"PBR_ALBEDO_RANGE", "PBR_METAL_TOO_DARK"} <= codes


def test_uv_projection_without_authored_uvs_is_reported(make_asset):
    p = make(make_asset)
    (p.parent / "textures").mkdir()
    Image.fromarray(np.full((4, 4, 3), 200, np.uint8)).save(p.parent / "textures" / "g.png")
    p.write_text(p.read_text().replace("edge_wear: 0.3}", "edge_wear: 0.3, layers: [{image: textures/g.png, projection: uv}]}"))
    a = build(p)
    s = build_surface(a)
    t = textures_for(a, s)
    assert "INVALID" in t.lifecycle.values()
    assert "TEX_UV_SOURCE_MISSING" in {i["code"] for i in run_validation(a, s)["issues"]}


def test_texel_density_target_metric_uses_the_asset_setting(make_asset):
    # FRESH_AGENT_05 finding: the report showed the profile's target, not uv.texel_density
    a = build(make(make_asset, extra="uv: {texel_density: 200}\n"))
    assert run_validation(a, build_surface(a))["metrics"]["texel_density_target"] == 200
