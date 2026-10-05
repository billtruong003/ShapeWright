# Releasing

1. On the release branch: bump `version` in `pyproject.toml` and `__version__` in `shapewright/__init__.py`
   (the source format version `shapewright: 0.1` changes only with a migration: docs/ASSET_FORMAT.md).
2. Add the release record (`docs/phases/RELEASE_X.Y.md`) and its row in the status table of
   `docs/PHASE_PLAN_16.md`, then `python tools/site/changelog.py` (CHANGELOG.md; a test checks it).
3. `python -m pytest -q`, `ruff check .`, and CI green on the branch (Linux, Windows, Godot import job).
4. Fast-forward `main`: the `release` workflow sees a version with no tag yet and tags it, or push the tag yourself, or run the workflow from the
   Actions tab (workflow_dispatch): it tags the commit with `v<package version>` itself.
   `.github/workflows/release.yml` runs the tests again, checks the tag matches the package version, builds the
   wheel, the sdist and `modular_house_pack-vX.Y.Z.zip`, and publishes a GitHub release with the top changelog
   entry as notes.

## PyPI (owner)

Needs the owner's PyPI account and an API token; the name `shapewright` must be free.

```bash
pip install build twine
python -m build --wheel --sdist --outdir dist
twine upload dist/*            # username __token__, password: the API token
```

Until then the documented install is `pip install "git+https://github.com/billtruong003/ShapeWright@vX.Y.Z"`.
