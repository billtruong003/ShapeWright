"""Phase 18: every `# run` block in the docs site's tutorials runs as written (in a fresh project).

Conventions in website/**/*.md:
  ```bash  whose first line is `# run`      -> each following line is one `sw ...` command, run in order;
                                              a line whose comment says `expect-fail` must exit non-zero
  ```yaml  whose first line is `# file: P`  -> written to P (relative to the project) before later blocks
  ```yaml  whose first line is `# append: P` -> appended to P
"""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from shapewright.assemble import ROOT

PAGES = sorted((ROOT / "website").rglob("*.md"))
FENCE = re.compile(r"```(\w+)[^\n]*\n(.*?)```", re.S)


def _runnable(page: Path) -> bool:
    return any(body.lstrip().startswith(("# run", "# file:", "# append:")) for _, body in FENCE.findall(page.read_text()))


@pytest.mark.parametrize("page", [p for p in PAGES if _runnable(p)], ids=lambda p: str(p.relative_to(ROOT / "website")))
def test_tutorial_blocks_run_as_written(page, tmp_path):
    env = {**os.environ, "SW_PROJECT": str(tmp_path), "PYTHONPATH": str(ROOT)}
    (tmp_path / "shapewright.yaml").write_text("shapewright: 0.1\n")
    (tmp_path / "assets").mkdir()
    ran = 0
    for lang, body in FENCE.findall(page.read_text()):
        head, _, rest = body.partition("\n")
        head = head.strip()
        if head.startswith(("# file:", "# append:")):
            target = tmp_path / head.split(":", 1)[1].strip()
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a" if head.startswith("# append:") else "w") as f:
                f.write(rest)
            continue
        if lang != "bash" or head != "# run":
            continue
        for line in rest.splitlines():
            argv = shlex.split(line, comments=True)
            if not argv:
                continue
            assert argv[0] == "sw", f"{page.name}: runnable blocks may only contain sw commands: {line}"
            res = subprocess.run([sys.executable, "-m", "shapewright", *argv[1:]], cwd=tmp_path, env=env,
                                 capture_output=True, text=True, timeout=600)
            if "expect-fail" in line:
                assert res.returncode != 0, f"{page.name}: expected `{line.strip()}` to fail\n{res.stdout[-800:]}"
            else:
                assert res.returncode == 0, f"{page.name}: `{line.strip()}` exited {res.returncode}\n{res.stdout[-1500:]}{res.stderr[-800:]}"
            ran += 1
    assert ran, f"{page.name} has runnable blocks but none ran"
