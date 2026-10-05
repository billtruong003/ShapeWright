"""`sw workbench`: a local page for people, driving the same `sw` commands an agent runs (Phase 15).

Rules this module keeps (checked in tests/test_architecture.py):
- every action is an `sw` command line, run in-process through `cli.main(argv)`, and every response
  echoes that command, so anything done here can be repeated, scripted or reviewed by an agent;
- it imports no geometry, validation, surface or export code: it reads files the commands write
  (asset.yaml, .build/*.png, .build/report.json, export/*.glb, history/*/summary.json) and nothing else;
- the only writes are `sw set`, saving the source text (restored if it no longer builds) and viewer
  screenshots under .build/shots/ (notes pinned on the model go through `sw feedback`);
- the 3D view (Phase 15b) is three.js in the browser, vendored under workbench/vendor/: it shows the
  `sw export --preview` GLB; the CPU renderer stays the reference for agents and tests;
- it binds to 127.0.0.1 and serves files only from inside assets/.

Requests are handled one at a time on the main thread (the CLI's build timeout uses SIGALRM), so two
browser tabs cannot interleave commands.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import shlex
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from .. import cli, paths

ROOT = paths.LIB
ASSETS = paths.assets_home()
PAGE = Path(__file__).with_name("index.html")
VIEWER = Path(__file__).with_name("viewer.js")
VENDOR = Path(__file__).with_name("vendor")
NAME = re.compile(r"^[A-Za-z0-9_\-]+$")
VIEWS = ("front", "front_right", "right", "back_right", "back", "back_left", "left", "front_left", "top", "low_front", "uv")
MODES = ("clay", "parts", "material", "wire", "normals", "silhouette", "textured", "albedo", "roughness", "metallic", "texel", "seams",
         "beauty")
NUM = re.compile(r"^-?\d+(\.\d+)?(e-?\d+)?$")
MAX_SHOT_BYTES = 8_000_000


def ref(name: str) -> str:
    """How commands name the asset: the bare name under the repository's assets/, else its folder."""
    d = asset_dir(name)
    return name if ASSETS.resolve() == (ROOT / "assets").resolve() else str(d)


def asset_dir(name: str) -> Path:
    if not NAME.match(name or "") or not (ASSETS / name / "asset.yaml").exists():
        raise ValueError(f"unknown asset '{name}'")
    return ASSETS / name


def argv_for(req: dict) -> list[str]:
    """Structured request -> `sw` argv. The whitelist is the whole capability surface of the page."""
    name = ref(req.get("asset", ""))
    cmd = req.get("cmd")
    sets = [f"{k}={v}" for k, v in (req.get("set") or {}).items()]
    set_args = ["--set", ",".join(sets)] if sets else []
    if cmd in ("review", "validate", "stats"):
        return [cmd, name, *set_args] + (["--verbose"] if cmd != "stats" and req.get("verbose") else [])
    if cmd == "render":
        view, mode = req.get("view", "front_right"), req.get("mode", "clay")
        if view not in VIEWS or mode not in MODES:
            raise ValueError("unknown view or mode")
        parts = [p for p in str(req.get("part") or "").split(",") if p and NAME.match(p)]
        return ["render", name, "--view", view, "--mode", mode, "--size", "640", *set_args] + (["--part", ",".join(parts)] if parts else [])
    if cmd == "set":
        if not sets:
            raise ValueError("nothing to set")
        return ["set", name, *sets]
    if cmd == "snapshot":
        return ["snapshot", name, "-m", str(req.get("message") or "workbench edit")] + (
            ["--critique", str(req["critique"])] if req.get("critique") else [])
    if cmd == "compare":
        a, b = str(req.get("a", "1")), str(req.get("b", "current"))
        if not all(re.match(r"^(\d+|current|last)$", x) for x in (a, b)):
            raise ValueError("compare takes iteration numbers, 'last' or 'current'")
        return ["compare", name, a, b]
    if cmd == "restore":
        return ["restore", name, str(int(req.get("n")))]
    if cmd == "export":
        t = req.get("target")
        if t and t not in ("generic", "godot", "unity", "unreal"):
            raise ValueError("unknown target")
        return ["export", name] + (["--target", t] if t else [])
    if cmd == "uv_lock":
        return ["uv", name, "lock"]
    if cmd == "glb":  # the 3D view: per-part nodes (generic target), no collision proxies
        return ["export", name, "--preview", "--target", "generic", *set_args]
    if cmd == "feedback":
        return ["feedback", name, "--json", "--all"]
    if cmd == "feedback_add":
        note = str(req.get("note") or "").strip()
        if not note:
            raise ValueError("a note needs text")
        argv = ["feedback", name, "add", note[:2000]]
        part = str(req.get("part") or "")
        if part:
            if not NAME.match(part):
                raise ValueError("bad part name")
            argv += ["--part", part]
        for key in ("at", "normal"):
            v = req.get(key)
            if v is not None:
                vals = [f"{round(float(x), 5):g}" for x in v][:3]
                if len(vals) != 3 or not all(NUM.match(x) for x in vals):
                    raise ValueError(f"{key} must be three numbers")
                argv += [f"--{key}", ",".join(vals)]
        view = str(req.get("view") or "")
        if view:
            argv += ["--view", view if view in VIEWS else "orbit"]
        image = str(req.get("image") or "")
        if image:
            if not re.match(r"^shots/shot_\d+\.png$", image):
                raise ValueError("bad screenshot path")
            argv += ["--image", image]
        return argv
    if cmd == "feedback_resolve":
        return ["feedback", name, "resolve", str(int(req.get("id"))), "--reply", str(req.get("reply") or "done")[:2000]]
    if cmd in ("log", "materials"):
        return [cmd, name]
    raise ValueError(f"'{cmd}' is not a workbench command")


def run(argv: list[str]) -> dict:
    out, err = io.StringIO(), io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(argv)
        except SystemExit as e:  # argparse
            rc = int(e.code or 0)
    return {"command": "./sw " + shlex.join(argv), "rc": rc, "output": out.getvalue() + err.getvalue(), "started": t0}


def images(name: str, since: float = 0.0) -> list[str]:
    b = ASSETS / name / ".build"
    found = [p for p in b.rglob("*.png") if p.stat().st_mtime >= since] if b.exists() else []
    return [str(p.relative_to(ASSETS)) for p in sorted(found, key=lambda p: -p.stat().st_mtime)]


def glbs(name: str, since: float = 0.0) -> list[str]:
    """GLB files a command just wrote (paths for /files), newest first."""
    e = ASSETS / name / "export"
    found = [p for p in e.glob("*.glb") if p.stat().st_mtime >= since] if e.exists() else []
    return [str(p.relative_to(ASSETS)) for p in sorted(found, key=lambda p: -p.stat().st_mtime)]


def asset_info(name: str) -> dict:
    d = asset_dir(name)
    text = (d / "asset.yaml").read_text()
    try:
        src = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        src = {}
    params = []
    for k, v in (src.get("params") or {}).items():
        spec = v if isinstance(v, dict) else {"value": v}
        params.append({"name": k, "value": spec.get("value"), "min": spec.get("min"), "max": spec.get("max"),
                       "doc": spec.get("doc", "")})
    rep = d / ".build" / "report.json"
    report = json.loads(rep.read_text()) if rep.exists() else None
    history = [json.loads(p.read_text()) for p in sorted((d / "history").glob("*/summary.json"))] if (d / "history").exists() else []
    return {"name": name, "source": text, "params": params, "report": report,
            "history": [{k: h.get(k) for k in ("iteration", "note", "critique", "status")} for h in history],
            "images": images(name), "extends": "extends" in src}


THUMBS = (".build/renders/front_right_beauty.png", ".build/renders/front_right_textured.png", ".build/renders/front_right_clay.png",
          ".build/sheet.png")


def list_assets() -> list[dict]:
    out = []
    for d in sorted(ASSETS.iterdir()):
        if (d / "asset.yaml").exists():
            rep = d / ".build" / "report.json"
            report = json.loads(rep.read_text()) if rep.exists() else {}
            m = report.get("metrics") or {}
            thumb = next((f"{d.name}/{t}" for t in THUMBS if (d / t).is_file()), None)
            out.append({"name": d.name, "status": report.get("status"), "triangles": m.get("triangles"),
                        "built": int(rep.stat().st_mtime) if rep.exists() else None, "thumb": thumb})
    return out


def save_shot(name: str, data_url: str) -> str:
    """A viewer screenshot (PNG data URL) -> .build/shots/shot_N.png; returns the path relative to .build/."""
    import base64

    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        raise ValueError("expected a PNG data URL")
    raw = base64.b64decode(data_url[len(prefix):], validate=True)
    if len(raw) > MAX_SHOT_BYTES or not raw.startswith(b"\x89PNG"):
        raise ValueError("not a PNG, or too large")
    d = asset_dir(name) / ".build" / "shots"
    d.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(p.stem.split("_")[1]) for p in d.glob("shot_*.png")] + [0])
    (d / f"shot_{n}.png").write_bytes(raw)
    return f"shots/shot_{n}.png"


def save_source(name: str, text: str) -> dict:
    """Write asset.yaml; if it no longer builds (a source error, rc 2), put the old text back."""
    f = asset_dir(name) / "asset.yaml"
    before = f.read_text()
    f.write_text(text)
    res = run(["validate", ref(name)])
    if res["rc"] == 2:
        f.write_text(before)
        res["output"] += "\nthe source did not build; the previous text was restored"
    return res


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/assets":
                return self._json(list_assets())
            if u.path == "/api/asset":
                return self._json(asset_info(q.get("name", "")))
            if u.path == "/files":
                p = (ASSETS / q.get("path", "")).resolve()
                if not p.is_relative_to(ASSETS.resolve()) or p.suffix.lower() not in (".png", ".glb", ".json", ".gif") or not p.is_file():
                    return self._json({"error": "not found"}, 404)
                ctype = {".png": "image/png", ".glb": "model/gltf-binary", ".json": "application/json", ".gif": "image/gif"}[p.suffix.lower()]
                return self._send(200, p.read_bytes(), ctype)
            if u.path == "/viewer.js":
                return self._send(200, VIEWER.read_bytes(), "text/javascript; charset=utf-8")
            if u.path.startswith("/vendor/"):  # three.js, vendored (offline, no CDN)
                p = (VENDOR / u.path[len("/vendor/"):]).resolve()
                if not p.is_relative_to(VENDOR.resolve()) or p.suffix != ".js" or not p.is_file():
                    return self._json({"error": "not found"}, 404)
                return self._send(200, p.read_bytes(), "text/javascript; charset=utf-8")
            return self._json({"error": "not found"}, 404)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > (MAX_SHOT_BYTES * 4 // 3 + 4096 if self.path == "/api/shot" else 1_000_000):
            return self._json({"error": "request too large"}, 413)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/run":
                argv = argv_for(req)
                res = run(argv)
                started = res.pop("started") - 0.05
                res["images"] = images(req["asset"], started)
                res["glbs"] = glbs(req["asset"], started)
                return self._json(res)
            if self.path == "/api/shot":
                return self._json({"image": save_shot(req.get("asset", ""), str(req.get("png", "")))})
            if self.path == "/api/source":
                res = save_source(req.get("asset", ""), str(req.get("text", "")))
                res.pop("started", None)
                return self._json(res)
            return self._json({"error": "not found"}, 404)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            return self._json({"error": str(e)}, 400)


def serve(port: int = 8765, open_browser: bool = False, assets: str | None = None) -> None:
    global ASSETS
    if assets:
        ASSETS = Path(assets).resolve()
    httpd = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"Shapewright workbench at {url}  (every action runs an `sw` command and shows it; Ctrl+C to stop)", flush=True)
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
