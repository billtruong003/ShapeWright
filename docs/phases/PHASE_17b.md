# Phase 17b: verify MCP with real clients (track C)

Branch `phase/17b-mcp-verify`, stacked on `phase/15b-web-viewer`. Plan: docs/REMAINING_WORK.md §5 (C1–C3).

**Verdict: PARTIAL.** C2 (MCP Inspector) is done. C1 (a desktop client) and C3 (another vendor's agent) need the
owner's machine and accounts; they are prepared, not run.

## C2: MCP Inspector (done)

`npx @modelcontextprotocol/inspector --cli <server> --method tools/list | tools/call` (Inspector CLI, current
release) against `sw mcp --project <scratch>`:

| call | result |
|---|---|
| `tools/list` | 18 tools, every schema valid JSON Schema |
| `guide` | `['text']`, the llms.txt brief |
| `brief request=a_wooden_signpost` | `['text']`, exit 0 |
| `new name=sign from_asset=crate` | `['text']`, created in the project |
| `review name=sign` | `['text', 'image']`, PASS |
| `render name=sign view=front mode=beauty` | `['text', 'image']` |
| `feedback name=sign` | `['text']`, "no open notes" |

**Finding, fixed:** `view`, `mode` and `target` were free strings in the schemas, so a client could not offer the
choices and a model had to guess them from the description. They are `Literal` types now, so the schemas carry
`enum`s (`test_stdio_server_lists_and_calls_tools` checks it). This needed the wrapper to pass real types to the SDK
(`typing.get_type_hints`), because `from __future__ import annotations` leaves strings that pydantic could not
resolve (`renderArguments is not fully defined`).

How to run it is in docs/MCP.md ("Checking the server with the MCP Inspector").

## C1, C3: for the owner

- **C1:** register `sw mcp --project <folder>` in Claude Desktop or Cursor (docs/MCP.md has the JSON for both, and
  the Windows form `python -m shapewright mcp`), give it the unseen request *"a stylized wooden signpost with two
  arrow signs, mobile, under 800 tris, export for Godot"*, and keep the transcript. Record: tool calls, whether the
  model looked at the review image, friction.
- **C3:** the same request through Codex CLI (config in docs/MCP.md) or ChatGPT with a connector to
  `sw mcp --transport streamable-http` behind an HTTPS tunnel; record it as `docs/experiments/FRESH_AGENT_13.md`.

## Gate

| gate | result |
|---|---|
| C2: Inspector lists and calls the tools, schema warnings fixed | **met** |
| C1: an unseen asset exports PASS through a desktop client, MCP tools only | **not verified** (owner) |
| C3: another vendor's agent does one prop | **not verified** (owner) |
