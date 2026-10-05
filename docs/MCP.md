# Shapewright over MCP

`sw mcp` exposes the whole Shapewright loop as MCP tools. Any MCP client can model, review and export assets with no shell access: Claude Code, Claude Desktop, Cursor, Codex, ChatGPT connectors and others.

```bash
pip install "shapewright[mcp]"      # or, in a clone: pip install -r requirements.txt "mcp>=1.10"
sw init ~/my_assets                 # optional: a project folder for your assets
sw mcp --project ~/my_assets        # stdio server (what desktop clients launch)
sw mcp --transport streamable-http --port 8000 --project ~/my_assets   # HTTP server at http://127.0.0.1:8000/mcp
```

## Tools

| tool | wraps | returns |
|---|---|---|
| `guide` | `sw caps --llms` | the one-page manual (loop, rules, profiles, full vocabulary) |
| `brief(request)` | `sw brief` | closest example with full source, profile/budget, rules |
| `doc(name)` | `sw doc` | a shape, op, archetype, issue code, profile, style, pack or component |
| `list_assets()` | — | project assets (editable) and library examples (read-only) |
| `read_source(name)` / `write_source(name, yaml_text)` | — / `sw validate` | the asset.yaml text / replaces it and validates (previous text kept in `.build/previous.yaml`) |
| `new(name, from_asset?)` | `sw new` | a new editable asset, optionally a variant of an example |
| `set_params(name, values)` | `sw set` | writes `a=1,b=2` into the source, keeping comments |
| `validate(name, try_values?)`, `stats(name)` | `sw validate`, `sw stats` | text |
| `review(name)` | `sw review` | text **+ the contact sheet image** |
| `render(name, view, mode, part?)` | `sw render` | text **+ image** |
| `snapshot(name, message, critique?)`, `compare(name, a, b)` | `sw snapshot`, `sw compare` | text (+ comparison image) |
| `export(name, target?)` | `sw export` | GLB path + validation summary |
| `pack_review(pack)` | `sw pack --pack` | consistency report + pack sheet image |
| `feedback(name)` | `sw feedback NAME` | notes a person pinned on the model in the workbench (part, point, view) + their screenshots |
| `resolve_feedback(name, note_id, reply)` | `sw feedback NAME resolve ID --reply ...` | marks a note done after the source changed |

Every tool runs the matching `sw` command as a subprocess, under the CLI's own time limit (`TIMEOUT_S` = 600 s). The answer always starts with the exact command (`$ sw review crate   (exit 0)`), so a person can repeat any step in a terminal.

## Safety model

- **No paths.** Tools take asset names: letters, digits, `_` and `-`. `../x`, `/etc/passwd` and `a/b` are refused. Param values are checked against `name=value[,...]` and may not contain shell metacharacters. Commands are run with an argument list, never through a shell.
- **Where writes go.** Writes go only into the project's `assets/` folder. The project is `--project`, else `$SW_PROJECT`, else the nearest `shapewright.yaml`, else the working directory.
- **Library examples are read-only.** Copy one first with `new("my_barrel", from_asset="barrel")`.
- **Size limit.** Sources larger than 512 KB are refused. YAML is parsed before it is written.
- **HTTP binds to localhost.** Only `--host 0.0.0.0` exposes it on a network. The server has no authentication, so put an authenticating proxy in front of it before exposing it anywhere.

## Client setup

The server command is `sw` with arguments `mcp --project /ABS/PATH/TO/PROJECT`. From a clone without installing, use the absolute path of `./sw` as the command. Check your client's current documentation for where its configuration lives; the shapes below are the common ones.

**Claude Code**

```bash
claude mcp add shapewright -- sw mcp --project "$PWD"
```

In a clone of this repository you don't need MCP at all: Claude Code reads `CLAUDE.md` / `AGENTS.md`, uses `./sw` directly, and loads the `.claude/skills/shapewright` skill.

**Claude Desktop** (`claude_desktop_config.json`), **Cursor** (`.cursor/mcp.json`) and most JSON-configured clients:

```json
{
  "mcpServers": {
    "shapewright": { "command": "sw", "args": ["mcp", "--project", "/ABS/PATH/TO/my_assets"] }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.shapewright]
command = "sw"
args = ["mcp", "--project", "/ABS/PATH/TO/my_assets"]
```

**ChatGPT and other remote-only clients.** These connect to an HTTPS MCP endpoint, not to a local command. Run `sw mcp --transport streamable-http --port 8000`, publish `http://127.0.0.1:8000/mcp` through an authenticated HTTPS tunnel or reverse proxy, and add that URL as a custom connector. Images come back as MCP image content; whether the client shows them to the model depends on the client.

## Verified

- **Tests** (`tests/test_mcp.py`):
  - the sandbox refusals;
  - library examples are read-only until copied;
  - `write_source` validates and backs up the previous text;
  - `review` and `render` return images;
  - a real stdio client session: `initialize` → `list_tools` → `new` → `review` (image content) → `read_source` → `write_source` → `export` (Godot GLB on disk).
- **Streamable HTTP:** checked by hand with an `initialize` request (Phase 17 record).
- **Supported SDK versions:** works with MCP Python SDK 2.x (`MCPServer`) and 1.x (`FastMCP`).

## Checking the server with the MCP Inspector

```bash
npx -y @modelcontextprotocol/inspector --cli sw mcp --project my_project --method tools/list
npx -y @modelcontextprotocol/inspector --cli sw mcp --project my_project --method tools/call --tool-name review --tool-arg name=crate
```

(From a source checkout without installing, wrap `PYTHONPATH=<checkout> python3 -m shapewright mcp --project ...` in a
small script and pass the script.) Phase 17b ran it on all 18 tools: schemas are valid, `view`, `mode` and `target`
are enums, `review` and `render` return `['text', 'image']` (docs/phases/PHASE_17b.md).
