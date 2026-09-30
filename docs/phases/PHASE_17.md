# Phase 17: MCP server

**Verdict: PARTIAL.** The server and the protocol are verified end to end with a scripted client over stdio and HTTP, on two SDK major versions. Two gate items were not verified here:
- "the same task through MCP only in two agent clients": no desktop MCP client can run in this container, and a subagent cannot attach a new MCP server;
- the MCP Inspector: it was not run.

Branch `phase/17-mcp`, stacked on `phase/16-packaging`. It is not merged.

## What shipped

| change | class | why it is generic |
|---|---|---|
| `shapewright/mcp_server.py` + `sw mcp [--transport stdio\|streamable-http\|sse] [--project] [--host] [--port]` | CAPABILITY GAP | Clients without a shell (Claude Desktop, Cursor, ChatGPT connectors) could not use Shapewright at all. |
| 16 tools mapping 1:1 to `sw` commands | — | `guide`, `brief`, `doc`, `list_assets`, `read_source`, `write_source`, `new`, `set_params`, `validate`, `stats`, `review` (+image), `render` (+image), `snapshot`, `compare` (+image), `export`, `pack_review` (+image). |
| Sandbox | — | Names, never paths. Param strings are pattern-checked. Commands run from an argument list, never a shell. Writes go only into the project's `assets/`, and library examples are read-only. Sources are capped at 512 KB and YAML is parsed before writing. The previous source is kept. Each call runs as a subprocess with the CLI time limit. |
| SDK compatibility | — | MCP Python SDK 2.x (`MCPServer`) and 1.x (`FastMCP`, ≥ 1.10). Tools are registered unstructured, so results are text plus image content. |
| `docs/MCP.md` | — | Tools, safety model, client setup (Claude Code, Claude Desktop / Cursor JSON, Codex TOML, remote clients over HTTPS). |

## Evidence

- **`tests/test_mcp.py` (5 tests):**
  - path and metacharacter refusals;
  - library examples are read-only until copied with `new(..., from_asset)`;
  - `write_source` rejects bad YAML, validates, and keeps `.build/previous.yaml`;
  - `review` and `render` return image files;
  - a **real stdio client session** running `initialize` → `list_tools` → `new` → `review` (image content) → path refusal → `read_source` → `write_source` → `export --target godot`, which leaves a GLB on disk.
- **SDK 1.30.0** in a separate venv: `list_tools` returned 16 tools; `guide` and `review` returned `['text', 'image']`.
- **Streamable HTTP:** `sw mcp --transport streamable-http --port 8765` answered `initialize` with the server instructions and tool capability (HTTP 200, `Mcp-Session-Id` issued).

## Gate

| gate item | result |
|---|---|
| the same task through MCP only, in two clients | **not verified**: a scripted client covered the whole loop over stdio (SDK 2.x) and the tool surface over SDK 1.x; there was no agent client |
| tool schemas pass MCP Inspector | **not verified**: the Inspector was not run; both SDKs' clients accepted the schemas |
| path-escape tests refused | **met** |

## Known limitations

- Reviewing or rendering a *library* example writes `.build/` next to that example. In a wheel install that folder is inside site-packages. Copy the example first; `new(from_asset=...)` is the documented path.
- The server has no authentication. HTTP binds to localhost by default, and docs/MCP.md says to use an authenticating proxy before exposing it.
