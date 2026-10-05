"""Metrics for MODULAR_HOUSE_PACK_01: pack-level reuse, parameterization and runtime numbers.

Usage: python tools/experiments/mhp_metrics.py OUT.json

Built on analyze_source.py / analyze_pack.py (the existing experiment methodology) plus the export
reports. Descriptive, not a score.
  parameterization ratio  = (derived + measured) / (literal + constant-expr + derived + measured) spatial numbers
  abstraction escape rate = (parts whose profile is `literal` or `mesh_escape`) / all parts, per the FA-02
                            escape profile; framework modifications are reported separately
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "experiments"))

HOUSES = ["house_cottage", "house_townhouse", "house_workshop"]
FRAMEWORK_CHANGES = [
    {"change": "component instances accept `origin: keep` (the component's own origin is its pivot)", "class": "ABSTRACTION GAP",
     "why generic": "bounding-box anchoring moved roof pieces 2-10 cm with optional trim; affects every kit piece with optional or asymmetric sub-parts"},
    {"change": "a malformed components/*.yaml no longer crashes `sw caps` / `sw doc`", "class": "BUG", "why generic": "any broken file broke every doc lookup"},
    {"change": "per-part UV charting at the scale of the part's atlas region", "class": "PERFORMANCE (CAPABILITY GAP)",
     "why generic": "a 571-part house took 95 s to lay out (the CLI's 120 s limit killed `sw review`); every many-part assembly"},
]


def main(out: Path):
    from analyze_pack import analyze
    from analyze_source import analyze as analyze_src

    assets = sorted(p.parent.name for p in (ROOT / "assets").glob("house_*/asset.yaml"))
    modules = [a for a in assets if a not in HOUSES]
    comps = sorted(p.stem for p in (ROOT / "components").glob("house_*.yaml"))

    # component reuse: instances (array/mirror counted once per instance line) across kit sources
    use_lines, use_assets = Counter(), {}
    mod_lines, mod_assets = Counter(), {}
    for a in assets:
        raw = yaml.safe_load((ROOT / "assets" / a / "asset.yaml").read_text())
        for part in (raw.get("parts") or {}).values():
            if isinstance(part, dict) and "component" in part:
                use_lines[part["component"]] += 1
                use_assets.setdefault(part["component"], set()).add(a)
            if isinstance(part, dict) and "asset" in part:  # Phase 19: houses instance module assets
                mod_lines[part["asset"]] += 1
                mod_assets.setdefault(part["asset"], set()).add(a)
    source_lines = {a: sum(1 for ln in (ROOT / "assets" / a / "asset.yaml").read_text().splitlines()
                           if ln.strip() and not ln.strip().startswith("#")) for a in HOUSES}

    src = {a: analyze_src(ROOT / "assets" / a / "asset.yaml") for a in assets}
    comp_src = {}
    for c in comps:
        try:
            comp_src[c] = analyze_src(ROOT / "components" / f"{c}.yaml")
        except Exception as e:  # components are not assets; record and continue
            comp_src[c] = {"error": str(e)}

    def totals(rows):
        t = Counter()
        prof = Counter()
        nparts = 0
        for r in rows:
            if "spatial_numbers" not in r:
                continue
            t.update(r["spatial_numbers"])
            prof.update(r.get("escape_profile", {}))
            nparts += len(r.get("parts", {}))
        denom = t["literal"] + t["constant_expr"] + t["derived"] + t["measured"]
        return {"spatial_numbers": dict(t), "parameterization_ratio": round((t["derived"] + t["measured"]) / denom, 3) if denom else None,
                "parts": nparts, "escape_profile": dict(prof),
                "abstraction_escape_rate": round((prof["literal"] + prof["mesh_escape"]) / nparts, 3) if nparts else None,
                "measure_queries": sum(r.get("counts", {}).get("measure_queries", 0) for r in rows if "counts" in r),
                "attach": sum(r.get("counts", {}).get("attach", 0) for r in rows if "counts" in r)}

    pack = analyze(ROOT, assets)
    reports = {}
    for a in assets:
        f = ROOT / "assets" / a / "export" / f"{a}.report.json"
        if f.exists():
            r = json.loads(f.read_text())
            reports[a] = {"status": r["status"], "triangles": r["metrics"]["triangles"], "materials": r["metrics"]["materials"],
                          "draw_calls": r["metrics"].get("draw_calls"), "parts": r["metrics"]["parts"],
                          "texel_px_m": r["metrics"].get("texel_density_px_m"), "warnings": r["counts"]["warning"],
                          "glb_bytes": r["export"]["bytes"], "khronos": r["metrics"].get("gltf_validator")}
    mod_tris = [reports[m]["triangles"] for m in modules if m in reports]
    dens = {a: pack["assets"][a]["tris_per_m2"] for a in modules}
    pack_src = yaml.safe_load((ROOT / "packs" / "cozy_house.yaml").read_text())
    asset_level_materials = {a: list((yaml.safe_load((ROOT / "assets" / a / "asset.yaml").read_text()).get("materials") or {}))
                             for a in assets}
    result = {
        "experiment": "MODULAR_HOUSE_PACK_01",
        "counts": {"assets": len(assets), "modules": len(modules), "demo_houses": len(HOUSES), "kit_components": len(comps),
                   "reused_foreign_components": sorted(set(use_lines) - set(comps)), "pack_params": len(pack_src["params"]),
                   "pack_materials": len(pack_src["materials"])},
        "component_reuse": {c: {"instance_lines": use_lines[c], "assets": len(use_assets.get(c, ()))} for c in sorted(use_lines)},
        "module_asset_reuse": {m: {"instance_lines": mod_lines[m], "houses": len(mod_assets.get(m, ()))} for m in sorted(mod_lines)},
        "house_source_lines": source_lines,
        "duplicated_structural_definitions": {
            "exact_duplicate_inline_parts_across_assets": len(pack["exact_duplicate_parts"]),
            "structural_duplicates_(same_shape+ops_in_3+_assets)": {k: len(v) for k, v in pack["structural_duplicates"].items()},
        },
        "materials": {"defined_once_in_pack": sorted(pack_src["materials"]),
                      "asset_level_material_definitions": {a: m for a, m in asset_level_materials.items() if m},
                      "material_drift": "0 by construction: pack materials are read-only in members (PACK_OVERRIDE)"},
        "detail_density_tris_per_m2": {"modules": dens, "spread_max_over_min": round(max(dens.values()) / min(dens.values()), 2)},
        "parameterization": {"modules": totals([src[m] for m in modules]), "demo_houses": totals([src[h] for h in HOUSES]),
                             "components": totals(list(comp_src.values())),
                             "per_house": {h: {"parameterization_ratio": src[h]["parameterization_ratio"],
                                               "literal_numbers": src[h]["spatial_numbers"]["literal"],
                                               "derived_numbers": src[h]["spatial_numbers"]["derived"],
                                               "component_instances": src[h]["counts"]["components"],
                                               "arrays": src[h]["counts"]["arrays"]} for h in HOUSES}},
        "runtime": {"module_triangles": {"min": min(mod_tris), "max": max(mod_tris), "median": sorted(mod_tris)[len(mod_tris) // 2]},
                    "demo_house_triangles": {h: reports[h]["triangles"] for h in HOUSES if h in reports},
                    "per_asset": reports},
        "framework_modifications": FRAMEWORK_CHANGES,
    }
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: result[k] for k in ("counts", "component_reuse", "duplicated_structural_definitions")}, indent=1))
    print(json.dumps(result["parameterization"]["modules"], indent=0)[:400])
    print(json.dumps(result["parameterization"]["demo_houses"], indent=0)[:400])
    print(json.dumps(result["runtime"]["module_triangles"]), json.dumps(result["runtime"]["demo_house_triangles"]))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
