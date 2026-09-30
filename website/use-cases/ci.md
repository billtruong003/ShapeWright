# Assets in CI

Assets are text, so they get code review. Validation is deterministic, so it can gate merges.

```bash
# run
sw bench --dir assets
```

`sw bench` validates every asset under a folder and exits non-zero on errors. A GitHub Actions job:

```yaml
name: assets
on: [pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install "git+https://github.com/billtruong003/shapewright"
      - run: sw bench --dir assets
      - run: for a in assets/*/; do sw review "$(basename "$a")" > /dev/null; done   # sheets as build artifacts
      - uses: actions/upload-artifact@v4
        with: {name: review-sheets, path: "assets/*/.build/sheet.png"}
```

Reviewers look at the sheet for each changed asset, the same image the agent critiqued.
