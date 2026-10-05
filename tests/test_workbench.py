"""Phase 15 gate (docs/WORKBENCH.md): the human workbench drives the same `sw` commands an agent runs and
has no modelling path of its own."""

import ast
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from shapewright.cli import main

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "shapewright" / "workbench" / "server.py"
E2E = ROOT / "tools" / "workbench"
CHROMIUM = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def test_workbench_imports_nothing_but_the_cli():
    # no geometry, validation, surface or export code: every action must go through an sw command
    tree = ast.parse(SERVER.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mods.add(("." * node.level) + (node.module or "") + ("" if node.module else ":" + ",".join(a.name for a in node.names)))
        elif isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
    internal = {m for m in mods if m.startswith(".")}
    assert internal == {"..:cli,paths"}, internal  # paths only locates the project/library (Phase 16); it builds nothing
    external = {m.split(".")[0] for m in mods - internal}
    assert external <= {"__future__", "base64", "contextlib", "io", "json", "re", "shlex", "time", "http", "pathlib", "urllib", "yaml", "webbrowser"}


def test_argv_whitelist(tmp_path, monkeypatch):
    from shapewright.workbench import server

    shutil.copytree(ROOT / "assets" / "crate", tmp_path / "crate")
    monkeypatch.setattr(server, "ASSETS", tmp_path)
    ref = str(tmp_path / "crate")
    assert server.argv_for({"asset": "crate", "cmd": "review", "set": {"w": 1}}) == ["review", ref, "--set", "w=1"]
    assert server.argv_for({"asset": "crate", "cmd": "export", "target": "godot"}) == ["export", ref, "--target", "godot"]
    for bad in ({"asset": "crate", "cmd": "bench"}, {"asset": "../assets/crate", "cmd": "review"},
                {"asset": "crate", "cmd": "render", "view": "front; rm"}, {"asset": "crate", "cmd": "export", "target": "x"}):
        with pytest.raises(ValueError):
            server.argv_for(bad)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def workbench(tmp_path):
    """A workbench over a scratch copy (A) plus an identical copy (B) for the same steps on the CLI."""
    a, b = tmp_path / "A", tmp_path / "B"
    for d in (a, b):
        d.mkdir()
        shutil.copytree(ROOT / "assets" / "tavern_chair", d / "tavern_chair", ignore=shutil.ignore_patterns(".build"))
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "shapewright", "workbench", "--port", str(port), "--assets", str(a)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "api/assets", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield url, a / "tavern_chair", b / "tavern_chair"
    proc.terminate()
    proc.wait(10)


def _post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())


def _same_as_cli(gui: Path, cli: Path, snapshot_msg: str, critique: str):
    """Repeat the session with sw commands on copy B; the files must match copy A's."""
    assert main(["set", str(cli), "seat_height=0.48"]) == 0
    assert main(["review", str(cli)]) == 0
    assert main(["snapshot", str(cli), "-m", snapshot_msg, "--critique", critique]) == 0
    assert main(["export", str(cli)]) == 0
    assert (gui / "asset.yaml").read_text() == (cli / "asset.yaml").read_text()
    ha = json.loads(sorted((gui / "history").glob("*/summary.json"))[-1].read_text())
    hb = json.loads(sorted((cli / "history").glob("*/summary.json"))[-1].read_text())
    for k in ("iteration", "note", "critique", "status", "source_hash", "metrics"):
        assert ha.get(k) == hb.get(k), k
    assert (gui / "export" / "tavern_chair.glb").read_bytes() == (cli / "export" / "tavern_chair.glb").read_bytes()


def test_http_session_equals_the_same_cli_session(workbench):
    url, gui, cli = workbench
    steps = [{"cmd": "review", "set": {"seat_height": 0.48}}, {"cmd": "set", "set": {"seat_height": 0.48}}, {"cmd": "review"},
             {"cmd": "snapshot", "message": "seat up", "critique": "ok"}, {"cmd": "export"}]
    cmds = []
    for s in steps:
        res = _post(url + "api/run", {"asset": "tavern_chair", **s})
        assert res["rc"] == 0, res
        cmds.append(res["command"].split()[1])
    assert cmds == ["review", "set", "review", "snapshot", "export"]
    # a source that does not build is not kept
    before = (gui / "asset.yaml").read_text()
    res = _post(url + "api/source", {"asset": "tavern_chair", "text": before.replace("shape:", "shaep:", 1)})
    assert res["rc"] == 2 and (gui / "asset.yaml").read_text() == before
    _same_as_cli(gui, cli, "seat up", "ok")


@pytest.mark.skipif(not (E2E / "node_modules" / "playwright-core").exists() or not CHROMIUM.exists() or not shutil.which("node"),
                    reason="browser session needs `cd tools/workbench && npm install` and Chromium")
def test_browser_session(workbench, tmp_path):
    url, gui, cli = workbench
    out = subprocess.run(["node", "session.mjs", url, "tavern_chair", "seat_height", "0.48", str(tmp_path / "wb.png")],
                         cwd=E2E, capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    cmds = json.loads(out.stdout.strip().splitlines()[-1])
    assert any("sw set" in c for c in cmds) and any("sw export" in c for c in cmds)
    _same_as_cli(gui, cli, "seat_height 0.48 from the workbench", "checked in the browser")


# ---------------------------------------------------------------- Phase 15b: 3D view, screenshots, notes for the agent


def test_3d_and_feedback_commands_are_sw_commands(tmp_path, monkeypatch):
    from shapewright.workbench import server

    shutil.copytree(ROOT / "assets" / "crate", tmp_path / "crate")
    monkeypatch.setattr(server, "ASSETS", tmp_path)
    ref = str(tmp_path / "crate")
    assert server.argv_for({"asset": "crate", "cmd": "glb", "set": {"w": 1}}) == \
        ["export", ref, "--preview", "--target", "generic", "--set", "w=1"]
    argv = server.argv_for({"asset": "crate", "cmd": "feedback_add", "note": "lid too thin", "part": "lid",
                            "at": [0, 0.5, 0.1], "normal": [0, 1, 0], "view": "orbit", "image": "shots/shot_3.png"})
    assert argv == ["feedback", ref, "add", "lid too thin", "--part", "lid", "--at", "0,0.5,0.1", "--normal", "0,1,0",
                    "--view", "orbit", "--image", "shots/shot_3.png"]
    for bad in ({"cmd": "feedback_add", "note": ""}, {"cmd": "feedback_add", "note": "x", "part": "a/b"},
                {"cmd": "feedback_add", "note": "x", "at": [1, 2]}, {"cmd": "feedback_add", "note": "x", "image": "../../etc/passwd"}):
        with pytest.raises((ValueError, TypeError)):
            server.argv_for({"asset": "crate", **bad})
    assert server.argv_for({"asset": "crate", "cmd": "feedback_resolve", "id": 2, "reply": "wider"}) == \
        ["feedback", ref, "resolve", "2", "--reply", "wider"]


def test_screenshots_are_pngs_inside_the_asset(tmp_path, monkeypatch):
    import base64

    from shapewright.workbench import server

    shutil.copytree(ROOT / "assets" / "crate", tmp_path / "crate")
    monkeypatch.setattr(server, "ASSETS", tmp_path)
    png = (ROOT / "docs" / "images" / "readme_gallery.png").read_bytes()
    rel = server.save_shot("crate", "data:image/png;base64," + base64.b64encode(png).decode())
    assert rel == "shots/shot_1.png" and (tmp_path / "crate" / ".build" / rel).read_bytes() == png
    assert server.save_shot("crate", "data:image/png;base64," + base64.b64encode(png).decode()) == "shots/shot_2.png"
    with pytest.raises(ValueError):
        server.save_shot("crate", "data:image/png;base64," + base64.b64encode(b"not a png").decode())
    with pytest.raises(ValueError):
        server.save_shot("../crate", "data:image/png;base64,")


def test_feedback_round_trip_cli_and_mcp(tmp_path, monkeypatch):
    from shapewright import mcp_server as M

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    monkeypatch.setenv("SW_PROJECT", str(tmp_path))
    assert main(["new", "box"]) == 0
    shots = tmp_path / "assets" / "box" / ".build" / "shots"
    shots.mkdir(parents=True)
    (shots / "shot_1.png").write_bytes((ROOT / "docs" / "images" / "readme_gallery.png").read_bytes())
    assert main(["feedback", "box", "add", "make", "it", "taller", "--part", "body", "--at", "0,0.5,0", "--image", "shots/shot_1.png"]) == 0
    text, imgs = M.feedback("box")
    assert "#1 [open] make it taller" in text and "part body" in text and imgs and imgs[0].name == "shot_1.png"
    out = M.resolve_feedback("box", 1, "height 0.8")
    assert "exit 0" in out
    text, imgs = M.feedback("box")
    assert "no open notes (1 resolved)" in text and not imgs
    assert main(["feedback", "box", "resolve", "7"]) == 2


@pytest.mark.skipif(not CHROMIUM.exists(), reason="needs the bundled Chromium")
def test_browser_3d_view_and_pinned_note(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    shutil.copytree(ROOT / "assets" / "crate", tmp_path / "crate", ignore=shutil.ignore_patterns(".build", "export"))
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "shapewright", "workbench", "--port", str(port), "--assets", str(tmp_path)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        url = f"http://127.0.0.1:{port}/"
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "api/assets", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_api.sync_playwright() as p:
            b = p.chromium.launch(executable_path=str(CHROMIUM), args=["--use-gl=angle", "--use-angle=swiftshader",
                                                                      "--enable-unsafe-swiftshader", "--no-proxy-server"])
            pg = b.new_page(viewport={"width": 1400, "height": 1000})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(url)
            pg.click('#assets li[data-name="crate"]')
            pg.wait_for_function("document.getElementById('glbinfo').textContent.endsWith('.glb')", timeout=300000)
            for m in ("clay", "parts", "uv_checker", "texel", "normals", "textured"):
                pg.select_option("#mode3d", m)
            box = pg.locator("#viewer3d").bounding_box()
            pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            pg.wait_for_function("document.getElementById('pickinfo').textContent.startsWith('part ')", timeout=10000)
            pg.fill("#note", "corner posts thicker")
            pg.click("#btn-note")
            pg.wait_for_function("document.getElementById('notes').textContent.includes('corner posts')", timeout=60000)
            b.close()
        assert not errors, errors
        notes = json.loads((tmp_path / "crate" / ".build" / "feedback.json").read_text())["notes"]
        assert notes[0]["note"] == "corner posts thicker" and notes[0]["part"] and len(notes[0]["at"]) == 3
        assert (tmp_path / "crate" / ".build" / notes[0]["image"]).is_file()
    finally:
        proc.terminate()
        proc.wait(10)
