"""`sw mcp`: the Shapewright loop as MCP tools (stdio by default, streamable HTTP optional).

Every tool is a thin wrapper over one `sw` command, run as a subprocess of this server so each call has
the CLI's own time limit and cannot take the server down. Images come back as image content, so a
client model can look at the review sheet it just produced.

Sandbox: tools take asset *names* (letters, digits, `_`, `-`), never paths. Sources are read from the
project or the library (`paths`), and written only inside the project's assets/ folder (or the checkout's
assets/ when there is no separate project). Library assets are read-only from an installed package: copy
one first with `new(name, from_asset=...)`.
"""

from __future__ import annotations

import inspect
import os
import re
import subprocess
import sys
import typing
from pathlib import Path
from typing import Literal

from . import paths

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")
PARAM_SETS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=[^,;&|`$<>]+(,[A-Za-z_][A-Za-z0-9_]*=[^,;&|`$<>]+)*$")
VIEWS = ("front", "back", "left", "right", "top", "bottom", "front_right", "front_left", "back_right", "back_left", "low_front")
MODES = ("clay", "parts", "material", "wire", "normals", "silhouette", "provenance", "regions", "textured", "albedo",
         "roughness", "metallic", "texel", "seams", "beauty")
TARGETS = ("generic", "godot", "unity", "unreal")
# choices as types, so the tool schemas carry enums (MCP Inspector, Phase 17b): clients can offer them
View = Literal["front", "back", "left", "right", "top", "bottom", "front_right", "front_left", "back_right", "back_left", "low_front"]
Mode = Literal["clay", "parts", "material", "wire", "normals", "silhouette", "provenance", "regions", "textured", "albedo",
               "roughness", "metallic", "texel", "seams", "density", "beauty"]
Target = Literal["", "generic", "godot", "unity", "unreal"]
TIMEOUT_S = 600
MAX_SOURCE_BYTES = 512 * 1024

INSTRUCTIONS = """Shapewright: agent-native 3D modelling for game assets. Loop: brief(request) -> new(name, from_asset)
-> write_source(name, yaml) -> review(name) and LOOK at the returned sheet -> critique specifically -> edit
params/parts -> snapshot(name, message, critique) -> ... -> export(name, target). Units metres, +Y up,
front +Z. Use params first, then anchors/attach and `measure:` queries, then ops. Every validation issue
has a code; doc(code) explains it. The one-page manual is the `guide` tool."""


class ToolError(ValueError):
    pass


def _name(name: str) -> str:
    if not NAME.match(name or ""):
        raise ToolError(f"invalid asset name {name!r}: use letters, digits, '_' or '-' (no paths)")
    return name


def _writable_home() -> Path:
    return paths.assets_home()


def _find(name: str) -> Path:
    _name(name)
    for d in paths.asset_dirs() + [paths.LIB / "assets"]:
        if (d / name / "asset.yaml").is_file():
            return d / name
    raise ToolError(f"no asset named {name!r}; list_assets() shows what exists, new(name) creates one")


def _writable(name: str) -> Path:
    d = _find(name)
    home = _writable_home().resolve()
    if not d.resolve().is_relative_to(home):
        raise ToolError(f"{name!r} is a library example (read-only here); copy it: new('my_{name}', from_asset='{name}')")
    return d


def _sw(*args: str, timeout: int = TIMEOUT_S) -> str:
    env = dict(os.environ)
    proj = paths.project()
    if proj is not None:
        env["SW_PROJECT"] = str(proj)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(paths._PKG.parent), env.get("PYTHONPATH", "")) if p)
    try:
        res = subprocess.run([sys.executable, "-m", "shapewright", *args], capture_output=True, text=True, timeout=timeout,
                             cwd=str(proj or Path.cwd()), env=env)
    except subprocess.TimeoutExpired:
        raise ToolError(f"`sw {' '.join(args)}` exceeded {timeout}s") from None
    out = (res.stdout + (("\n" + res.stderr) if res.stderr.strip() else "")).strip()
    return f"$ sw {' '.join(args)}   (exit {res.returncode})\n{out}"


# ---------------------------------------------------------------- tool implementations (plain functions: testable without MCP)


def guide() -> str:
    """The one-page manual (llms.txt): the loop, the rules, a minimal asset and the full vocabulary."""
    from .llms import llms_text

    return llms_text()


def brief(request: str) -> str:
    """START HERE for a new request: closest example asset with its full source, profile/budget, rules and vocabulary."""
    return _sw("brief", request)


def doc(name: str) -> str:
    """Details and an example for one shape, op, view, render mode, material archetype or issue code."""
    if not re.match(r"^[A-Za-z0-9_\-]{1,64}$", name or ""):
        raise ToolError("doc() takes a single name such as 'chamfer_box', 'array', 'wood' or 'ASM_FLOATING_PARTS'")
    return _sw("doc", name)


def list_assets() -> str:
    """Assets you can open: the project's (editable) and the library examples (read-only; copy with new(..., from_asset))."""
    home = _writable_home().resolve()
    rows, seen = [], set()
    for d in paths.asset_dirs() + [paths.LIB / "assets"]:
        for p in sorted(d.glob("*/asset.yaml")):
            if p.parent.name in seen:
                continue
            seen.add(p.parent.name)
            rows.append(f"{p.parent.name:32s} {'editable' if p.parent.resolve().is_relative_to(home) else 'library'}")
    return "\n".join(rows) or "(no assets)"


def read_source(name: str) -> str:
    """The asset's asset.yaml text."""
    return (_find(name) / "asset.yaml").read_text()


def write_source(name: str, yaml_text: str) -> str:
    """Replace an editable asset's asset.yaml, then validate it. The previous text is kept in .build/previous.yaml."""
    import yaml

    d = _writable(name)
    if len(yaml_text.encode()) > MAX_SOURCE_BYTES:
        raise ToolError(f"source larger than {MAX_SOURCE_BYTES} bytes")
    try:
        yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise ToolError(f"not valid YAML: {e}") from None
    src = d / "asset.yaml"
    (d / ".build").mkdir(exist_ok=True)
    (d / ".build" / "previous.yaml").write_text(src.read_text())
    src.write_text(yaml_text)
    return _sw("validate", name)


def new(name: str, from_asset: str = "") -> str:
    """Create an editable asset in the project: from the template, or as a variant (`extends`) of from_asset."""
    _name(name)
    args = ["new", name]
    if from_asset:
        _find(from_asset)
        args += ["--from", from_asset]
    return _sw(*args)


def set_params(name: str, values: str) -> str:
    """Write param values into the source, keeping comments: values like 'height=0.5,leg=0.07'. Refuses out-of-range values."""
    _writable(name)
    if not PARAM_SETS.match(values or ""):
        raise ToolError("values must look like 'name=value[,name=value]'")
    return _sw("set", name, values)


def validate(name: str, try_values: str = "") -> str:
    """Layered validation. try_values ('a=1,b=2') tries param values without editing the source."""
    _find(name)
    args = ["validate", name, "--verbose"] if False else ["validate", name]
    if try_values:
        if not PARAM_SETS.match(try_values):
            raise ToolError("try_values must look like 'name=value[,name=value]'")
        args += ["--set", try_values]
    return _sw(*args)


def stats(name: str) -> str:
    """Per-part triangles, sizes, centres and materials; sockets; params."""
    _find(name)
    return _sw("stats", name)


def review(name: str) -> tuple[str, Path | None]:
    """Validate + contact sheet (orthographic views with scale bars, 3/4 views, parts, wireframe, UVs) + style checklist.
    Rigged characters return the character sheet (look, reference, UV checker, density, joint weights, poses)."""
    d = _find(name)
    text = _sw("review", name)
    build = paths.out_dir(d) / ".build"
    char = build / "character.png"  # rigged characters: the character sheet (weights, poses) says more
    sheet = char if "character: " in text and char.is_file() else build / "sheet.png"
    return text, sheet if sheet.is_file() else None


def render(name: str, view: View = "front_right", mode: Mode = "textured", part: str = "") -> tuple[str, Path | None]:
    """One inspection image. view: front, back, left, right, top, bottom, front_right, front_left, back_right, back_left,
    low_front. mode: clay, parts, material, wire, normals, silhouette, textured, albedo, roughness, metallic, texel, seams...;
    beauty = presentation render (shadows, ambient occlusion) for showing a finished asset, not for inspection"""
    _find(name)
    if view not in VIEWS or mode not in MODES:
        raise ToolError(f"view must be one of {VIEWS}; mode one of {MODES}")
    args = ["render", name, "--view", view, "--mode", mode]
    if part:
        if not re.match(r"^[A-Za-z0-9_]{1,64}$", part):
            raise ToolError("part must be a part name")
        args += ["--part", part]
    text = _sw(*args)
    return text, _last_png(text)


def snapshot(name: str, message: str, critique: str = "") -> str:
    """Record an iteration: source + metrics + your critique. Do this after each meaningful change."""
    _writable(name)
    args = ["snapshot", name, "-m", message[:500]]
    if critique:
        args += ["--critique", critique[:2000]]
    return _sw(*args)


def compare(name: str, a: str = "1", b: str = "current") -> tuple[str, Path | None]:
    """Compare two iterations (numbers, 'last' or 'current'): side-by-side image, silhouette diff, per-part size changes."""
    _find(name)
    for v in (a, b):
        if not re.match(r"^(\d{1,4}|last|current)$", v):
            raise ToolError("iterations are numbers, 'last' or 'current'")
    text = _sw("compare", name, a, b)
    return text, _last_png(text)


def export(name: str, target: Target = "") -> str:
    """Validate and write the GLB (+ report): Khronos validation and re-import. target: generic, godot, unity, unreal."""
    _find(name)
    args = ["export", name]
    if target:
        if target not in TARGETS:
            raise ToolError(f"target must be one of {TARGETS}")
        args += ["--target", target]
    return _sw(*args)


def pack_review(pack: str) -> tuple[str, Path | None]:
    """Review every asset with `pack: NAME` as one set: common-scale sheet + material/param/density consistency."""
    _name(pack)
    text = _sw("pack", "--pack", pack)
    return text, _last_png(text)


def feedback(name: str) -> tuple[str, list[Path]]:
    """Notes the person pinned on the model in the workbench (click a point, type what is wrong): the part, the point
    (asset coordinates, metres), the view, and a screenshot with the spot marked. Act on each, then resolve_feedback."""
    from . import feedback as fb

    d = _find(name)
    notes = fb.load(d)
    shots = []
    for n in notes:
        if n.get("status") == "open" and n.get("image"):
            img = fb.path_for(d).parent / n["image"]
            if img.is_file() and len(shots) < 4:
                shots.append(img)
    return fb.format_notes(notes), shots


def resolve_feedback(name: str, note_id: int, reply: str = "") -> str:
    """Mark a workbench note resolved after changing the source; reply says what changed (the person sees it)."""
    _find(name)
    return _sw("feedback", name, "resolve", str(int(note_id)), "--reply", reply or "done")


def _last_png(text: str) -> Path | None:
    base = paths.project() or Path.cwd()
    for m in reversed(re.findall(r"([^\s\"']+\.png)", text)):
        p = Path(m) if Path(m).is_absolute() else base / m
        if p.is_file():
            return p
    return None


TOOLS = [guide, brief, doc, list_assets, read_source, write_source, new, set_params, validate, stats, review, render,
         snapshot, compare, export, pack_review, feedback, resolve_feedback]


# ---------------------------------------------------------------- MCP binding


def _server_class():
    try:  # mcp 2.x
        from mcp.server.mcpserver import Image, MCPServer
        return MCPServer, Image
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP, Image
        return FastMCP, Image


def build_server():
    import functools

    try:
        Server, Image = _server_class()
    except ImportError:
        raise SystemExit('the MCP server needs the MCP SDK: pip install "shapewright[mcp]"') from None
    server = Server("shapewright", instructions=INSTRUCTIONS)

    def wrap(fn):
        @functools.wraps(fn)
        def tool(*args, **kwargs):
            try:
                out = fn(*args, **kwargs)
            except ToolError as e:
                return f"error: {e}"
            if isinstance(out, tuple):
                text, img = out
                imgs = img if isinstance(img, list) else [img] if img else []
                return [text, *(Image(path=str(i)) for i in imgs)] if imgs else text
            return out
        hints = typing.get_type_hints(fn)  # real types, not the strings of `from __future__ import annotations`
        tool.__annotations__ = {k: v for k, v in hints.items() if k != "return"}
        del tool.__wrapped__  # the schema comes from the arguments; results are text or [text, image] content
        sig = inspect.signature(fn)
        tool.__signature__ = sig.replace(parameters=[q.replace(annotation=hints.get(q.name, q.annotation)) for q in sig.parameters.values()],
                                         return_annotation=inspect.Signature.empty)
        return tool

    for fn in TOOLS:
        server.tool(name=fn.__name__, description=(fn.__doc__ or "").strip(), structured_output=False)(wrap(fn))
    return server


def main(transport: str = "stdio", project: str | None = None, host: str = "127.0.0.1", port: int = 8000) -> int:
    if project:
        os.environ["SW_PROJECT"] = str(Path(project).resolve())
    server = build_server()
    if transport == "stdio":
        server.run(transport="stdio")
    elif "host" in inspect.signature(server.run_streamable_http_async).parameters:  # mcp 2.x: options go to run()
        server.run(transport=transport, host=host, port=port)
    else:  # mcp 1.x: network options live on the server's settings
        server.settings.host, server.settings.port = host, port
        server.run(transport=transport)
    return 0
