"""Iteration history and revision comparison.

A snapshot stores only what cannot be regenerated: the resolved source, the
agent's note/critique and a metrics summary. Renders are never stored; they
are reproduced deterministically from the snapshot source when compared.

    assets/<name>/history/003/source.yaml    the source file exactly as written (comments kept; used by restore)
    assets/<name>/history/003/resolved.yaml  flattened source (extends applied; used to rebuild for compare)
    assets/<name>/history/003/summary.json   status, metrics, note, critique
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw

from .assemble import Asset, build
from .render.views import _font, render
from .surface import build_surface
from .validate.run import run_validation


def history_dir(asset_path: Path) -> Path:
    from . import paths

    return paths.out_dir(asset_path.parent) / "history"


def iterations(asset_path: Path) -> list[Path]:
    d = history_dir(asset_path)
    return sorted(p for p in d.glob("[0-9][0-9][0-9]") if p.is_dir()) if d.exists() else []


def snapshot(asset_path: Path, note: str = "", critique: str = "") -> dict:
    asset = build(asset_path)
    report = run_validation(asset, build_surface(asset))
    its = iterations(asset_path)
    if its:
        last = json.loads((its[-1] / "summary.json").read_text())
        if last.get("source_hash") == asset.source_hash and not critique:
            return {"iteration": last["iteration"], "unchanged": True, "path": str(its[-1])}
    n = int(its[-1].name) + 1 if its else 1
    d = history_dir(asset_path) / f"{n:03d}"
    d.mkdir(parents=True)
    src = {k: v for k, v in asset.source.items() if not k.startswith("_")}
    shutil.copy(asset_path, d / "source.yaml")
    (d / "resolved.yaml").write_text(yaml.safe_dump(src, sort_keys=False, width=120))
    summary = {
        "iteration": n, "note": note, "critique": critique, "source_hash": asset.source_hash, "status": report["status"],
        "counts": report["counts"], "metrics": {k: report["metrics"].get(k) for k in ("triangles", "parts", "size_m", "materials", "uv_overlap", "checks") if k in report["metrics"]},
        "errors": [i["code"] + (f"[{i['where']}]" if i.get("where") else "") for i in report["issues"] if i["severity"] == "error"],
        "params": {k: round(v, 5) for k, v in asset.env.items()},
    }
    (d / "summary.json").write_text(json.dumps(summary, indent=1))
    return {"iteration": n, "path": str(d), "status": report["status"]}


def log(asset_path: Path) -> list[dict]:
    return [json.loads((d / "summary.json").read_text()) for d in iterations(asset_path)]


def restore(asset_path: Path, n: int) -> Path:
    d = history_dir(asset_path) / f"{n:03d}"
    if not d.exists():
        raise FileNotFoundError(f"iteration {n} not found")
    backup = asset_path.parent / ".build" / "asset.before_restore.yaml"  # restore edits the source: it is never a library example
    backup.parent.mkdir(exist_ok=True)
    shutil.copy(asset_path, backup)
    shutil.copy(d / "source.yaml", asset_path)
    return backup


def load_ref(asset_path: Path, ref: str) -> tuple[str, Asset]:
    if ref in ("current", "cur", "now"):
        return "current", build(asset_path)
    n = len(iterations(asset_path)) if ref in ("last", "latest") else int(ref)
    d = history_dir(asset_path) / f"{n:03d}"
    if not d.exists():
        raise FileNotFoundError(f"iteration {ref} not found (have {[int(p.name) for p in iterations(asset_path)]})")
    # build from the asset's own folder so asset-local profiles and relative files (mesh_file, textures)
    # resolve as they did (a copy under .build/ broke imported assets: FRESH_AGENT_07)
    tmp = asset_path.parent / f".iter_{n:03d}.yaml"
    shutil.copy(d / "resolved.yaml", tmp)
    try:
        a = build(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    a.path = asset_path
    return f"#{n}", a


def _recorded(asset_path: Path, label: str) -> str | None:
    """Status stored in the snapshot's summary (FA-10: compare re-validated #1 as WARN against a later uv.lock)."""
    if not label.startswith("#"):
        return None
    f = history_dir(asset_path) / f"{int(label[1:]):03d}" / "summary.json"
    return json.loads(f.read_text()).get("status") if f.exists() else None


def _mask(asset, surface, view, frame, size):
    im = render(asset, surface, view, "silhouette", size, frame=frame, annotate=False)
    return np.asarray(im.convert("L")) < 128


def compare(asset_path: Path, ref_a: str, ref_b: str, views=("front", "right", "top", "front_right"), size: int = 320) -> tuple[dict, Image.Image]:
    la, a = load_ref(asset_path, ref_a)
    lb, b = load_ref(asset_path, ref_b)
    sa, sb = build_surface(a), build_surface(b)
    ba, bb = a.bounds(), b.bounds()
    frame = np.stack([np.minimum(ba[0], bb[0]), np.maximum(ba[1], bb[1])])
    sheet = Image.new("RGB", (3 * size, len(views) * size), (255, 255, 255))
    ious = {}
    for r, v in enumerate(views):
        ia = render(a, sa, v, "clay", size, frame=frame, label=f"{la} | {v}")
        ib = render(b, sb, v, "clay", size, frame=frame, label=f"{lb} | {v}")
        ma, mb = _mask(a, sa, v, frame, size), _mask(b, sb, v, frame, size)
        diff = np.full((size, size, 3), 255, np.uint8)
        diff[ma & mb] = (170, 170, 170)
        diff[ma & ~mb] = (220, 60, 50)
        diff[~ma & mb] = (40, 170, 70)
        di = Image.fromarray(diff)
        ImageDraw.Draw(di).text((6, 4), f"{v}: red = only {la}, green = only {lb}", fill=(40, 40, 40), font=_font(max(11, size // 30)))
        union = (ma | mb).sum()
        ious[v] = round(float((ma & mb).sum() / union), 4) if union else 1.0
        for c, im in enumerate((ia, ib, di)):
            sheet.paste(im, (c * size, r * size))

    def sizes(asset):
        out = {}
        for p in asset.parts:
            bb_ = out.get(p.base)
            pb = p.bounds
            out[p.base] = pb if bb_ is None else np.stack([np.minimum(bb_[0], pb[0]), np.maximum(bb_[1], pb[1])])
        return {k: v[1] - v[0] for k, v in out.items()}

    pa, pb_ = sizes(a), sizes(b)
    part_changes = {}
    for k in sorted(set(pa) & set(pb_)):
        rel = (pb_[k] - pa[k]) / np.maximum(pa[k], 1e-9)
        if np.abs(rel).max() > 0.005:
            part_changes[k] = {ax: f"{v:+.1%}" for ax, v in zip("xyz", rel) if abs(v) > 0.005}
    r4 = lambda v: None if v is None else round(v, 4)  # noqa: E731
    params = {k: [r4(a.env.get(k)), r4(b.env.get(k))] for k in sorted(set(a.env) | set(b.env)) if a.env.get(k) != b.env.get(k)}
    ra, rb = run_validation(a, sa), run_validation(b, sb)
    metrics = {
        "a": la, "b": lb,
        "status": [ra["status"], rb["status"]],  # re-validated now (an old iteration meets today's uv.lock)
        "status_recorded": [_recorded(asset_path, la) or ra["status"], _recorded(asset_path, lb) or rb["status"]],
        "triangles": [a.n_tris, b.n_tris],
        "size_m": [[round(float(v), 4) for v in ba[1] - ba[0]], [round(float(v), 4) for v in bb[1] - bb[0]]],
        "silhouette_iou": ious,
        "params_changed": params,
        "parts_added": sorted(set(pb_) - set(pa)),
        "parts_removed": sorted(set(pa) - set(pb_)),
        "part_size_changes": part_changes,
    }
    return metrics, sheet
