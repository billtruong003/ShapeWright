# Claude Code (local)

```bash
git clone https://github.com/billtruong003/shapewright && cd shapewright
pip install -r requirements.txt          # or: pip install -e ".[dev,mcp]"
./sw doctor
claude                                   # CLAUDE.md -> AGENTS.md, and the shapewright skill, load automatically
```

For your own project instead of the Shapewright repository:

```bash
pip install "git+https://github.com/billtruong003/shapewright"
cd my_game && sw init art && cd art
claude mcp add shapewright -- sw mcp --project "$PWD"   # optional: tools instead of shell commands
```

Optional: `cd tools/gltf-validator && npm install` (in a clone) enables the Khronos glTF validator during `sw export`. Installed copies can point `SW_GLTF_VALIDATOR` at any folder that has it.

To see results in your engine, export with a target (`sw export NAME --target godot|unity|unreal`) and import the GLB. The export report lists triangles, draw calls, collision and LODs.
