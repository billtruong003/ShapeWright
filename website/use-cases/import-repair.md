# Import and repair an existing model

```bash
sw import path/to/model.glb crate_imported --split      # one part per connected piece; materials and textures kept
sw review crate_imported
```

The import writes a normal asset source: `mesh_file` parts plus `authored` materials that reference the extracted textures. From there:

- **Repair**: add `ops: [{type: clean, fill_holes: true}]` to a part. It welds coincident vertices, drops zero-area and duplicate faces, fixes winding and fills holes.
- **Reduce**: `{type: decimate, ratio: 0.5}` keeps the UVs.
- **Replace**: delete a piece and add a native part in its place (anchors and `measure:` work on imported parts too).
- **Rescale**: `--scale 0.01` for centimetre files, and `--z-up` for Z-up files.

The import tutorial blocks are not run by the documentation tests, because they need a file of yours. The same flow is tested in `tests/test_import.py` on real CC0 files (FA-07).
