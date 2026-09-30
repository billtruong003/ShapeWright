# Claude Code (cloud)

Claude Code on the web runs in a container with your repository cloned. Shapewright needs nothing but Python packages, so it works there as-is.

1. **Put Shapewright in the repository you give the session.** Either work in a fork or clone of `shapewright`, or add it to your game repo:

    ```bash
    pip install "git+https://github.com/billtruong003/shapewright"   # in the environment's setup script
    sw init art                                                       # once; commit art/shapewright.yaml
    ```

2. **Let the agent find the manual.**
    - In a Shapewright clone, `CLAUDE.md` points to `AGENTS.md` and the `.claude/skills/shapewright` skill loads automatically.
    - In your own repo, copy `.claude/skills/shapewright/` from Shapewright, or add one line to your `CLAUDE.md`: *"3D assets: read `llms.txt` (from `sw caps --llms`) and use `sw`"*.

3. **Ask for assets as you would ask a person:**

    > Make a stylized wooden mailbox on a post for a cozy mobile game, under 900 triangles. Review it, improve it once, export for Godot, and commit the source and the GLB.

**Tips**
- Ask the agent to **look at the review sheet image** after each change. That is where proportion mistakes show.
- Commit `asset.yaml`, `uv.lock.yaml` and `history/`, but not `.build/` (renders and caches).
- Big kits: ask for a pack first (`packs/NAME.yaml`), then the modules, then the buildings. See [modular kit](../use-cases/modular-kit.md).
