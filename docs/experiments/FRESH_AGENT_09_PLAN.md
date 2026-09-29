# FRESH_AGENT_09 plan: a substantially different agent (Phase 13, written before the run)

## Question

Is Shapewright **agent-native** or merely **Claude-native**? Phase 13's gate: "at least one
substantially different coding agent should successfully use the repository without
Shapewright-specific coaching."

## What is available (stated honestly)

This container has no other agent CLI (`codex`, `gemini`, `aider`, `opencode`, `goose`, `qwen`, …
are absent) and no API keys for other vendors. A **cross-vendor** run is therefore **blocked by the
environment**; it needs a person to provide another agent or key. The substitute used here:
- **Claude Haiku 4.5**, a much smaller model from a different capability tier than the model used in
  FA-01–08;
- the same harness;
- a prompt comparable to FA-01/FA-04, with no Shapewright-specific words.

This tests whether the repository depends on a frontier model's ability to compensate (reading source
code, recovering from vague errors, inventing workarounds). It does **not** test vendor-specific habits.

Documentation check: README, AGENTS.md, CONTRIBUTING and the format docs contain no Claude-specific
instructions. `CLAUDE.md` only points to the vendor-neutral `AGENTS.md`.

## Prompt (task part, verbatim)

> Use this repository to create a game-ready textured prop: "A weathered wooden signpost for a
> fantasy village: a post with two arrow-shaped signs pointing in different directions and a small
> lantern hook. Mobile game, under 800 triangles, the surface detail in textures." Inspect it,
> critique it, improve it, and export a validated GLB.

## Metrics (compared with FA-01 and FA-04)

Success (valid, exported, requirements met), time, tool calls, tokens, iterations, validation failures
and recoveries, whether it looks at renders, whether it reads framework code, framework modifications,
and the discovery path.

## Predictions

| # | Prediction |
|---|---|
| X1 | Succeeds: a valid textured GLB under 800 tris |
| X2 | More validation failures than FA-01/FA-04 (YAML flow-style traps, expression quoting); recovers via the error hints |
| X3 | Uses `sw review` images, but critiques are less specific |
| X4 | Reads less framework code than the larger model; relies on AGENTS.md and `sw doc` |
| X5 | Fewer iterations (1–2) |
| X6 | 0 framework changes |
