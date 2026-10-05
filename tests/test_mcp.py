"""Phase 17: the MCP server's tools (sandbox, library read-only, images) and the stdio protocol end to end."""

import asyncio
import os
import sys

import pytest

from shapewright import mcp_server as M
from shapewright.assemble import ROOT
from shapewright.cli import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    monkeypatch.setenv("SW_PROJECT", str(tmp_path))
    return tmp_path


def test_names_never_become_paths(project):
    for bad in ("../x", "/etc/passwd", "a/b", "", ".hidden", "x" * 80):
        with pytest.raises(M.ToolError):
            M.read_source(bad)
    with pytest.raises(M.ToolError):
        M.set_params("barrel", "h=1; rm -rf /")


def test_library_examples_are_read_only_until_copied(project):
    assert "chamfer_box" in M.read_source("barrel") or "barrel" in M.read_source("barrel")
    with pytest.raises(M.ToolError, match="library example"):
        M.write_source("barrel", "shapewright: 0.1\n")
    out = M.new("my_barrel", from_asset="barrel")
    assert "exit 0" in out and (project / "assets" / "my_barrel" / "asset.yaml").exists()
    assert "my_barrel" in M.list_assets() and "editable" in M.list_assets()


def test_write_source_validates_and_keeps_the_previous_text(project):
    M.new("box")
    src = (project / "assets" / "box" / "asset.yaml").read_text()
    with pytest.raises(M.ToolError, match="YAML"):
        M.write_source("box", "parts: [unclosed")
    out = M.write_source("box", src.replace("width: {value: 0.5", "width: {value: 0.6"))
    assert "PASS" in out
    assert (project / "assets" / "box" / ".build" / "previous.yaml").read_text() == src


def test_review_and_render_return_images(project):
    M.new("box")
    text, img = M.review("box")
    assert "PASS" in text and img is not None and img.name == "sheet.png" and img.is_file()
    text, img = M.render("box", view="front", mode="clay")
    assert img is not None and img.suffix == ".png"
    with pytest.raises(M.ToolError):
        M.render("box", view="sideways")


def test_stdio_server_lists_and_calls_tools(project):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        env = {**os.environ, "PYTHONPATH": str(ROOT)}  # the checkout, as an installed package would be on the path
        params = StdioServerParameters(command=sys.executable, args=["-m", "shapewright", "mcp", "--project", str(project)], env=env)
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            assert {"brief", "new", "write_source", "review", "render", "export", "feedback", "resolve_feedback"} <= set(tools)
            # choices are enums in the schema (Phase 17b, MCP Inspector finding)
            def schema(t):  # mcp 1.x: inputSchema, 2.x: input_schema
                return getattr(t, "inputSchema", None) or getattr(t, "input_schema")
            assert "beauty" in schema(tools["render"])["properties"]["mode"]["enum"]
            assert "godot" in schema(tools["export"])["properties"]["target"]["enum"]
            res = await s.call_tool("new", {"name": "crate2", "from_asset": "crate"})
            assert "exit 0" in res.content[0].text
            res = await s.call_tool("review", {"name": "crate2"})
            kinds = [c.type for c in res.content]
            assert "image" in kinds, kinds
            res = await s.call_tool("read_source", {"name": "../../etc/passwd"})
            assert "invalid asset name" in res.content[0].text
            src = (await s.call_tool("read_source", {"name": "crate2"})).content[0].text
            res = await s.call_tool("write_source", {"name": "crate2", "yaml_text": src + "\n# edited over MCP\n"})
            assert "exit 0" in res.content[0].text
            res = await s.call_tool("export", {"name": "crate2", "target": "godot"})
            assert "exported" in res.content[0].text and (project / "assets" / "crate2" / "export" / "crate2_godot.glb").is_file()

    asyncio.run(asyncio.wait_for(run(), 240))
