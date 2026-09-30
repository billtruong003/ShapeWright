# Pick your setup

| You use | Go to | What the agent gets |
|---|---|---|
| Claude Code on the web / in the cloud | [Claude Code (cloud)](claude-code-cloud.md) | the repository, `AGENTS.md`, a skill, the `sw` CLI |
| Claude Code on your machine | [Claude Code (local)](claude-code-local.md) | the same, plus your own files and engine |
| Claude Desktop, Cursor, Codex, other MCP clients | [MCP clients](mcp-clients.md) | 16 tools; review sheets come back as images |
| ChatGPT or any chat without tools | [Chat](chat.md) | `llms.txt`; the chat writes sources, you run `sw` |
| Nobody: you do it | [By hand](cli.md) | the CLI and a local workbench page |

Every setup runs the same loop:

```
brief -> write asset.yaml -> review (look at the sheet) -> critique -> revise -> ... -> export
```
