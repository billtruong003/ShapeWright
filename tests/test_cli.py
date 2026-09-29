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
