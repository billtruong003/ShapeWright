# FRESH_AGENT_08 plan: engine-ready delivery (Phase 12 gate)

## Question

"A generated asset should be capable of entering a normal game-engine pipeline without significant
manual cleanup." Can a fresh agent deliver props that a **real engine** imports cleanly, with physics,
few draw calls, working moving parts and LODs, from a plain request that names engines but no
conventions? Predictions E1–E6 are in [../PRODUCTION.md](../PRODUCTION.md), written before implementation.

## Prompt (task part, verbatim)

> Our studio has two projects: one in **Godot 4** and one in **Unreal Engine 5**. Create three props
> for both: (1) a wooden storage chest whose lid can be opened in-game, (2) a park bench, and (3) a
> wall-mounted iron torch bracket. Each must be ready to drop into the engine: correct scale,
> collision the engine understands, reasonable draw calls, and LODs where the engine needs them.
> Export a Godot version and an Unreal version of each, validated.

## Verification

Every Godot export goes through Godot 4.3's importer (`tools/engine/godot_check.py`): bodies and
shapes, visible meshes, surfaces, the lid node and pivot, textures, size and grounding. The Unreal
exports are checked structurally: `UCX_` collision, LOD files, Khronos. They are not tested in Unreal.
Also recorded: framework changes (the gate expects 0), time and tokens.
