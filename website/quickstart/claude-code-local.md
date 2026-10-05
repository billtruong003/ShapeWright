# Claude Code (local)

```bash
git clone https://github.com/billtruong003/ShapeWright && cd shapewright
pip install -r requirements.txt          # or: pip install -e ".[dev,mcp]"
./sw doctor
claude                                   # CLAUDE.md -> AGENTS.md, and the shapewright skill, load automatically
```

For your own project instead of the Shapewright repository:

```bash
pip install "git+https://github.com/billtruong003/ShapeWright"
cd my_game && sw init art && cd art
claude mcp add shapewright -- sw mcp --project "$PWD"   # optional: tools instead of shell commands
```

!!! note "On Windows"
    - Activate a venv with `.venv\Scripts\activate` (PowerShell: `.venv\Scripts\Activate.ps1`).
    - In a clone, use `sw.cmd doctor` (the same launcher as `./sw`); after `pip install -e .` the command is `sw`,
      and `python -m shapewright ...` always works.
    - For `claude mcp add`, pass the full path to the project: `sw mcp --project "C:\path\to\art"`.

Optional: `cd tools/gltf-validator && npm install` (in a clone) enables the Khronos glTF validator during `sw export`. Installed copies can point `SW_GLTF_VALIDATOR` at any folder that has it.

To see results in your engine, export with a target (`sw export NAME --target godot|unity|unreal`) and import the GLB. The export report lists triangles, draw calls, collision and LODs.
