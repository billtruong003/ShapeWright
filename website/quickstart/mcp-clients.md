# Claude Desktop, Cursor, Codex and other MCP clients

```bash
pip install "shapewright[mcp]"
sw init ~/my_assets
```

Register the server command `sw mcp --project /ABS/PATH/my_assets`. For example, in `claude_desktop_config.json` or `.cursor/mcp.json`:

```json
{ "mcpServers": { "shapewright": { "command": "sw", "args": ["mcp", "--project", "/ABS/PATH/my_assets"] } } }
```

For Codex, in `~/.codex/config.toml`:

```toml
[mcp_servers.shapewright]
command = "sw"
args = ["mcp", "--project", "/ABS/PATH/my_assets"]
```

The client gets 18 tools: `guide`, `brief`, `doc`, `list_assets`, `read_source`, `write_source`, `new`, `set_params`, `validate`, `stats`, `review`, `render`, `snapshot`, `compare`, `export`, `pack_review`, and `feedback` / `resolve_feedback` (notes a person pinned on the model in the workbench, with screenshots).
- `review`, `render`, `compare` and `pack_review` return **images**, so the model sees what it made.
- Tools take asset names, never paths. Writes stay in the project's `assets/`, and library examples are read-only until copied.

Remote-only clients connect over HTTPS: run `sw mcp --transport streamable-http --port 8000` behind an authenticating tunnel or proxy. Full details are in [docs/MCP.md](https://github.com/billtruong003/ShapeWright/blob/main/docs/MCP.md).
