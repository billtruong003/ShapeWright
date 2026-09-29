"""Rebuild and validate an asset under parameter overrides (experiment harness).

Usage: python tools/experiments/perturb.py ASSET_DIR 'steps=5' 'steps=14,rise=0.2' ...

Each setting is applied to a temporary copy of the source placed in the asset
directory (so relative files, components and profiles resolve), built,
validated, and removed. Reports status, error codes, triangles and size.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shapewright.assemble import build  # noqa: E402
from shapewright.report import SourceError  # noqa: E402
from shapewright.surface import build_surface  # noqa: E402
from shapewright.validate.run import run_validation  # noqa: E402


def with_overrides(data: dict, overrides: dict) -> dict:
    params = dict(data.get("params") or {})
    for k, v in overrides.items():
        if k not in params:
            raise KeyError(f"param '{k}' not in source (have: {', '.join(params)})")
        params[k] = {**params[k], "value": v} if isinstance(params[k], dict) else v
    return {**data, "params": params}


def run(asset_dir: Path, settings: list[dict]) -> list[dict]:
    src = asset_dir / "asset.yaml"
    data = yaml.safe_load(src.read_text())
    tmp = asset_dir / ".perturb.yaml"
    out = []
    try:
        for s in settings:
            tmp.write_text(yaml.safe_dump(with_overrides(data, s), sort_keys=False))
            try:
                a = build(tmp)
                r = run_validation(a, build_surface(a))
                out.append({"setting": s, "status": r["status"], "tris": a.n_tris,
                            "size": [round(float(v), 3) for v in a.bounds()[1] - a.bounds()[0]],
                            "errors": sorted({i["code"] + (f"[{i['where']}]" if i.get("where") else "") for i in r["issues"] if i["severity"] == "error"}),
                            "warnings": sorted({i["code"] for i in r["issues"] if i["severity"] == "warning"})})
            except SourceError as e:
                out.append({"setting": s, "status": "BUILD_FAIL", "errors": [i.code + f"[{i.where}]" for i in e.issues if i.severity == "error"][:6]})
    finally:
        tmp.unlink(missing_ok=True)
    return out


def parse(arg: str) -> dict:
    out = {}
    for kv in arg.split(","):
        k, v = kv.split("=")
        out[k.strip()] = yaml.safe_load(v)
    return out


if __name__ == "__main__":
    res = run(Path(sys.argv[1]), [parse(a) for a in sys.argv[2:]])
    for r in res:
        print(json.dumps(r))
