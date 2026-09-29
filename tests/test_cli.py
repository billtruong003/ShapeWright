import json

from shapewright.cli import main


def test_caps_json_lists_registered_vocabulary(capsys):
    assert main(["caps", "--json"]) == 0
    m = json.loads(capsys.readouterr().out)
    assert {"chamfer_box", "lathe", "tube", "extrude"} <= set(m["shapes"])
    assert {"subtract", "taper", "jitter"} <= set(m["ops"])
    assert "front_right" in m["views"] and "clay" in m["modes"]
    assert any(v["layer"] == "assembly" for v in m["validators"])


def test_validate_exit_codes(make_asset, capsys):
    ok = make_asset("parts:\n  a:\n    shape: {type: box, size: [0.2, 0.2, 0.2]}\n    anchor: bottom\n    material: m\nmaterials: {m: {}}\n")
    assert main(["validate", str(ok)]) == 0
    bad = make_asset("parts:\n  a:\n    shape: {type: box, size: [0.2, 0.2, 0.2]}\n    position: [0, 1, 0]\n  b:\n    shape: {type: box, size: [0.2, 0.2, 0.2]}\n    anchor: bottom\n", "bad")
    assert main(["validate", str(bad)]) == 1
    broken = make_asset("parts:\n  a:\n    shape: {type: nope}\n", "broken")
    assert main(["validate", str(broken)]) == 2
    out = capsys.readouterr().out
    assert "SRC_SCHEMA" in out


def test_render_and_snapshot_cycle(make_asset, capsys):
    p = make_asset("parts:\n  a:\n    shape: {type: box, size: [0.2, 0.2, 0.2]}\n    anchor: bottom\n")
    assert main(["render", str(p), "--view", "front", "--mode", "clay", "--size", "96"]) == 0
    assert (p.parent / ".build" / "renders" / "front_clay.png").exists()
    assert main(["snapshot", str(p), "-m", "one"]) == 0
    p.write_text(p.read_text().replace("0.2, 0.2, 0.2", "0.3, 0.2, 0.2"))
    assert main(["snapshot", str(p), "-m", "two"]) == 0
    assert main(["compare", str(p), "1", "2", "--size", "96"]) == 0
    out = capsys.readouterr().out
    assert '"a": {"x": "+50.0%"}' in out
    assert main(["restore", str(p), "1"]) == 0
    assert "0.2, 0.2, 0.2" in p.read_text()


def test_set_overrides_params_without_touching_the_source(capsys):
    from shapewright.assemble import ROOT

    src = (ROOT / "assets" / "tavern_chair" / "asset.yaml").read_text()
    assert main(["validate", "tavern_chair", "--set", "lean=0.14,seat_width=0.56"]) == 0
    assert "0.607x" in capsys.readouterr().out
    assert (ROOT / "assets" / "tavern_chair" / "asset.yaml").read_text() == src
    assert not (ROOT / "assets" / "tavern_chair" / ".set_override.yaml").exists()
    assert main(["validate", "tavern_chair", "--set", "nope=1"]) == 2


def test_checks_can_address_first_last_and_count(make_asset):
    from shapewright.assemble import build
    from shapewright.surface import build_surface
    from shapewright.validate.run import run_validation

    p = make_asset("""
params: {n: 4}
materials: {m: {}}
parts:
  step:
    shape: {type: box, size: [0.5, 0.1, 0.3]}
    anchor: bottom
    array: {count: n, offset: [0, 0.1, 0.3]}
    material: m
sockets:
  floor: {attach: {to: origin}}
checks:
  - {expr: step.count, min: 4, max: 4}
  - {expr: step.last.max.y - step.first.min.y, min: 0.39, max: 0.41}
""")
    a = build(p)
    r = run_validation(a, build_surface(a))
    assert r["metrics"]["checks"] == {"step.count": 4, "step.last.max.y - step.first.min.y": 0.4}
    assert list(a.sockets[0].position) == [0, 0, 0]
