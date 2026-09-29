"""Run all validators and assemble a compact, agent-friendly report."""

from __future__ import annotations

import json

from ..assemble import Asset
from ..report import Issue, status_of
from ..surface import Surface
from . import LAYERS, VALIDATORS, load_builtin

SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


def run_validation(asset: Asset, surface: Surface, extra: list[Issue] | None = None, exported: bool = False) -> dict:
    issues, metrics = collect(asset, surface)
    return make_report(asset, issues, metrics, extra, exported)


def collect(asset: Asset, surface: Surface) -> tuple[list[Issue], dict]:
    """Run every validator once; make_report can then be called again with export issues added."""
    load_builtin()
    issues: list[Issue] = list(asset.issues)
    metrics: dict = {"triangles": asset.n_tris, "parts": len(asset.parts)}
    for v in VALIDATORS:
        try:
            issues.extend(v.fn(asset, surface, metrics))
        except Exception as e:  # a crashing validator must not hide the others
            issues.append(Issue("VALIDATOR_CRASHED", "error", f"{v.name}: {e}", "", v.layer))
    return issues, metrics


def make_report(asset: Asset, issues: list[Issue], metrics: dict, extra: list[Issue] | None = None, exported: bool = False) -> dict:
    issues = list(issues) + list(extra or [])
    metrics = dict(metrics)
    issues.sort(key=lambda i: (SEV_ORDER[i.severity], LAYERS.index(i.layer) if i.layer in LAYERS else 99, i.code, i.where))
    layers = {}
    for layer in LAYERS:
        li = [i for i in issues if i.layer == layer]
        ran = layer != "export" or li or exported
        if ran:
            layers[layer] = status_of(li)
    counts = {s: sum(1 for i in issues if i.severity == s) for s in ("error", "warning", "info")}
    return {
        "asset": asset.name,
        "status": status_of(issues),
        "source_hash": asset.source_hash,
        "counts": counts,
        "layers": layers,
        "metrics": metrics,
        "issues": [i.to_dict() for i in issues],
    }


def format_text(report: dict, verbose: bool = False) -> str:
    m = report["metrics"]
    budget = f"/{m['budget_triangles']}" if "budget_triangles" in m else ""
    size = "x".join(f"{v:.3f}" for v in m.get("size_m", []))
    lines = [
        f"{report['status']} {report['asset']}  tris {m.get('triangles')}{budget}  parts {m.get('parts')}  size {size} m  "
        f"materials {m.get('materials', '?')}  uv_overlap {m.get('uv_overlap', '-')}  texel {m.get('texel_density_px_m', '-')} px/m (median part)",
        "layers: " + " ".join(f"{k}={v}" for k, v in report["layers"].items()),
    ]
    if m.get("texture"):
        t = m["texture"]
        lines.append(f"texture: {t['resolution']}px atlas, {t['achieved_px_m']} px/m area-average (target {t['target_px_m']:g}), ~{t['memory_kb']} KB, lifecycle {t.get('lifecycle')}")
    if m.get("checks"):
        lines.append("checks: " + ", ".join(f"{k}={v}" for k, v in m["checks"].items()))
    for i in report["issues"]:
        if i["severity"] == "info" and not verbose:
            continue
        where = f" [{i['where']}]" if i.get("where") else ""
        hint = f"  -> {i['hint']}" if i.get("hint") else ""
        lines.append(f"  {i['severity'].upper():7} {i['code']}{where}: {i['msg']}{hint}")
    hidden = sum(1 for i in report["issues"] if i["severity"] == "info")
    if hidden and not verbose:
        lines.append(f"  ({hidden} info items hidden; --verbose to show)")
    return "\n".join(lines)


def dump(report: dict) -> str:
    return json.dumps(report, indent=1, sort_keys=False)
