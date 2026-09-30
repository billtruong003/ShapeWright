"""Phase 19: nested components, asset instances, measure on instances, pivot on instances."""

import numpy as np
import pytest

from shapewright.assemble import build
from shapewright.report import SourceError

LEG = """shapewright: 0.1
component: leg
params: {h: {value: 0.4}, w: {value: 0.05}}
parts:
  post:
    shape: {type: box, size: [w, h, w]}
    material: wood
    anchor: bottom
    position: [0, 0, 0]
"""

# a component made of two nested `leg` instances and a top that sits on them
FRAME = """shapewright: 0.1
component: frame
params: {h: {value: 0.4}, span: {value: 0.5}}
parts:
  left:
    component: leg
    with: {h: h}
    materials: {wood: timber}
    origin: keep
    position: [-span / 2, 0, 0]
  right:
    component: leg
    with: {h: h}
    materials: {wood: timber}
    origin: keep
    position: [span / 2, 0, 0]
  top:
    shape: {type: box, size: [span + 0.1, 0.04, 0.1]}
    material: timber
    anchor: bottom
    attach: {to: left_post, at: top}
"""

SELF = """shapewright: 0.1
component: loop
parts:
  again: {component: loop}
"""


def _project(tmp_path, monkeypatch, assets: dict, comps: dict):
    (tmp_path / "components").mkdir()
    for n, t in comps.items():
        (tmp_path / "components" / f"{n}.yaml").write_text(t)
    for n, t in assets.items():
        (tmp_path / "assets" / n).mkdir(parents=True)
        (tmp_path / "assets" / n / "asset.yaml").write_text(t)
    monkeypatch.setenv("SW_PROJECT", str(tmp_path))
    return tmp_path


TABLE = """shapewright: 0.1
asset: {name: table}
materials: {oak: {archetype: wood, color: "#8a5a34"}}
parts:
  frame:
    component: frame
    with: {h: 0.7}
    materials: {timber: oak}
    origin: keep
    position: [0, 0, 0]
    array: {count: 2, offset: [0, 0, 0.6]}
"""


def test_components_nest_and_their_materials_and_names_compose(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch, {"table": TABLE}, {"leg": LEG, "frame": FRAME})
    a = build(p / "assets" / "table")
    names = {q.name for q in a.parts}
    assert {"frame_0_left_post", "frame_0_right_post", "frame_0_top", "frame_1_left_post", "frame_1_top"} <= names
    assert {q.material for q in a.parts} == {"oak"}  # leg.wood -> frame.timber -> table.oak
    top = next(q for q in a.parts if q.name == "frame_0_top")
    assert abs(top.bounds[0][1] - 0.7) < 1e-6  # attached to the nested leg's top, with the outer `with: {h: 0.7}`
    z1 = next(q for q in a.parts if q.name == "frame_1_left_post").bounds.mean(0)[2]
    assert abs(z1 - 0.6) < 1e-6


def test_a_component_that_contains_itself_is_a_cycle(tmp_path, monkeypatch):
    src = "shapewright: 0.1\nasset: {name: x}\nparts:\n  a: {component: loop}\n"
    p = _project(tmp_path, monkeypatch, {"x": src}, {"loop": SELF})
    with pytest.raises(SourceError, match="contains itself"):
        build(p / "assets" / "x")


SHELF = """shapewright: 0.1
asset: {name: shelf}
params: {w: {value: 0.8, min: 0.4, max: 1.2}}
materials: {oak: {archetype: wood, color: "#8a5a34"}}
parts:
  board:
    shape: {type: box, size: [w, 0.03, 0.25]}
    material: oak
    anchor: bottom
    position: [0, 0, 0]
"""

ROOM = """shapewright: 0.1
asset: {name: room}
materials: {oak: {archetype: wood, color: "#8a5a34"}}
parts:
  floor:
    shape: {type: box, size: [3, 0.1, 3]}
    material: oak
    anchor: top
    position: [0, 0, 0]
  shelf:
    asset: shelf
    with: {w: 1.0}
    position: [0, 1.2, 0]
    array: {count: 3, offset: [0, 0.4, 0]}
  lamp:
    asset: shelf
    measure:
      top: {bounds: shelf_2}
    position: [0, top.max.y, 0]
"""


def test_assets_instance_other_assets_with_param_overrides(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch, {"shelf": SHELF, "room": ROOM}, {})
    a = build(p / "assets" / "room")
    boards = sorted((q for q in a.parts if q.name.startswith("shelf_") and q.name.endswith("_board")), key=lambda q: q.name)
    assert [q.name for q in boards] == ["shelf_0_board", "shelf_1_board", "shelf_2_board"]
    assert abs((boards[0].bounds[1][0] - boards[0].bounds[0][0]) - 1.0) < 1e-6  # with: {w: 1.0}
    assert abs(boards[2].bounds[0][1] - 2.0) < 1e-6
    lamp = next(q for q in a.parts if q.name == "lamp_board")
    assert abs(lamp.bounds[0][1] - boards[2].bounds[1][1]) < 1e-6  # measure on an asset instance
    assert lamp.instance.get("asset_instance_of") == "shelf"


def test_asset_instances_refuse_unknown_params_cycles_and_conflicting_materials(tmp_path, monkeypatch):
    bad_param = ROOM.replace("with: {w: 1.0}", "with: {width: 1.0}")
    loop = "shapewright: 0.1\nasset: {name: loop}\nparts:\n  me: {asset: loop}\n"
    clash = SHELF.replace('"#8a5a34"', '"#112233"').replace("name: shelf", "name: shelf2")
    room2 = ROOM.replace("asset: shelf\n    with", "asset: shelf2\n    with").replace("lamp:\n    asset: shelf", "lamp:\n    asset: shelf2")
    p = _project(tmp_path, monkeypatch, {"shelf": SHELF, "shelf2": clash, "room": bad_param, "loop": loop, "room2": room2}, {})
    with pytest.raises(SourceError, match="not a param of asset 'shelf'"):
        build(p / "assets" / "room")
    with pytest.raises(SourceError, match="instances itself"):
        build(p / "assets" / "loop")
    with pytest.raises(SourceError, match="MATERIAL_CONFLICT"):
        build(p / "assets" / "room2")
    ok = room2.replace("asset: shelf2\n", "asset: shelf2\n    materials: {oak: oak}\n")
    (p / "assets" / "room2" / "asset.yaml").write_text(ok)
    build(p / "assets" / "room2")  # an explicit mapping says "use this asset's oak"


DOORWAY = """shapewright: 0.1
asset: {name: doorway}
materials: {wood: {archetype: wood, color: "#8a5a34"}}
parts:
  wall:
    shape: {type: box, size: [2, 2.4, 0.2]}
    material: wood
    anchor: bottom
    position: [0, 0, 0]
  door:
    component: leg
    with: {h: 2.0, w: 0.9}
    materials: {wood: wood}
    measure:
      face: {bounds: wall}
    origin: keep
    position: [0, 0, face.max.z]
    pivot: bottom_left
"""


def test_measure_and_pivot_on_a_component_instance(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch, {"doorway": DOORWAY}, {"leg": LEG})
    a = build(p / "assets" / "doorway")
    door = next(q for q in a.parts if q.name == "door_post")
    assert abs(door.bounds.mean(0)[2] - 0.1) < 1e-6  # placed on the measured wall face, no hand offset
    assert door.pivot is not None and np.allclose(door.pivot, [-0.45, 0, 0.1])  # bottom_left of the placed group
