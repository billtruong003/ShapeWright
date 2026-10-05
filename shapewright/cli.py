"""`sw` command-line interface. Every command is a thin wrapper over library calls.

Exit codes: 0 = ok (PASS/WARN), 1 = validation errors, 2 = source/usage error.
Text output is compact by default; `--json` gives the full structure.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

import numpy as np

from .limits import LIMITS
from .report import SourceError, compact_json


def _rel(p: Path) -> str:
    try:
        return os.path.relpath(p)
    except ValueError:
        return str(p)


def _extends_path(base: Path, start: Path) -> str:
    """`extends:` value from a new asset directory to its base: relative with forward slashes, so the source works
    on every OS; absolute when the two are on different Windows drives (relpath cannot cross drives)."""
    try:
        return Path(os.path.relpath(base, start)).as_posix()
    except ValueError:
        return Path(base).resolve().as_posix()


def _parse_sets(sets) -> dict:
    import yaml

    out = {}
    for item in sets or []:
        for kv in item.split(","):
            if "=" not in kv:
                raise ValueError(f"--set expects name=value, got '{kv}'")
            k, v = kv.split("=", 1)
            out[k.strip()] = yaml.safe_load(v)
    return out


def _load(ref: str, sets=None):
    from .assemble import build, resolve_asset_path
    from .surface import build_surface

    path = resolve_asset_path(ref)
    overrides = _parse_sets(sets)
    if not overrides:
        asset = build(path)
        return asset, build_surface(asset)
    import yaml

    from .source import load_source

    data = yaml.safe_load(path.read_text())
    params = dict(data.get("params") or {})
    known = load_source(path).get("params") or {}  # a variant's inherited params and a pack's are params too (Phase 18 docs test)
    for k, v in overrides.items():
        if k not in known:
            from .registry import suggest

            raise ValueError(f"--set: '{k}' is not a param of this asset.{suggest(k, known)}")
        spec = params.get(k, known[k])
        params[k] = {**spec, "value": v} if isinstance(spec, dict) else v
    tmp = path.parent / ".set_override.yaml"  # same directory: relative files, components, profiles still resolve
    tmp.write_text(yaml.safe_dump({**data, "params": params}, sort_keys=False))
    try:
        asset = build(tmp)
        surface = build_surface(asset)
    finally:
        tmp.unlink(missing_ok=True)
    asset.path = path
    print(f"(with --set {', '.join(f'{k}={v}' for k, v in overrides.items())}; the source file is unchanged)")
    return asset, surface


def _print_source_error(e: SourceError, as_json: bool):
    if as_json:
        print(json.dumps({"status": "FAIL", "stage": "source", "issues": [i.to_dict() for i in e.issues]}, indent=1))
    else:
        print("FAIL (asset source could not be built)")
        for i in e.issues:
            print("  " + i.line())
    return 2


# ------------------------------------------------------------------ commands


def cmd_caps(a):
    from .caps import manifest, summary_text

    if a.llms:
        from .llms import llms_text

        print(llms_text(), end="")
        return 0
    print(json.dumps(manifest(), indent=1) if a.json else summary_text())
    return 0


def cmd_set(a):
    from .assemble import build, resolve_asset_path
    from .source_edit import set_params

    path = resolve_asset_path(a.asset)
    before = path.read_text()
    changes = set_params(path, _parse_sets(a.values))
    try:
        build(path)
    except SourceError:
        path.write_text(before)  # a value that breaks the build is not kept
        print("the new values do not build; the source was restored")
        raise
    for c in changes:
        print(f"set {c}")
    print(f"wrote {_rel(path)} (comments and layout kept); `sw review {a.asset}` to look at it")
    return 0


def cmd_workbench(a):
    from .workbench.server import serve

    serve(a.port, a.open, a.assets)
    return 0


def cmd_brief(a):
    from .brief import brief

    print(brief(" ".join(a.request)))
    return 0


def _code_row(doc: Path, code: str) -> str:
    """The row of an issue code in docs/VALIDATION.md's tables, as 'severity | meaning | fix' text."""
    if not doc.exists():
        return ""
    for line in doc.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == f"`{code}`":
            return "  |  ".join(c for c in cells[1:] if c)
    return ""


def cmd_doc(a):
    from .caps import manifest

    m = manifest()
    for fam, label in (("shapes", "shape"), ("ops", "op"), ("material_archetypes", "archetype"), ("point_generators", "point_generator"),
                       ("part_features", "part_feature")):
        if a.name in m[fam]:
            print(compact_json({label: a.name, **m[fam][a.name]}))
            return 0
    if a.name in m["views"] or a.name in m["modes"]:
        print(m["views"].get(a.name) or m["modes"].get(a.name))
        return 0
    from . import paths

    for v in m["validators"]:
        if a.name in v["codes"] or a.name == v["name"]:
            row = _code_row(paths.LIB / "docs" / "VALIDATION.md", a.name)
            if row:  # FRESH_AGENT_12: point at the meaning and the fix, not at a file an installed copy may not have
                print(f"{a.name}: {row}")
            print(compact_json(v))
            return 0
    from .source import INSTANCE_KEYS, PART_KEYS, TOP_KEYS

    for label, keys in (("part key", PART_KEYS), ("instance key", INSTANCE_KEYS), ("top-level key", TOP_KEYS)):
        if a.name in keys and isinstance(keys, dict):
            print(f"{label} `{a.name}`: {keys[a.name]}")
            print("Full reference: docs/ASSET_FORMAT.md" + (f" (installed copy: {paths.LIB / 'docs' / 'ASSET_FORMAT.md'})"
                                                            if (paths.LIB / "docs" / "ASSET_FORMAT.md").exists() else ""))
            return 0

    for kind in ("profiles", "styles", "packs", "components"):
        f = paths.find(kind, a.name)
        if f is not None:  # the file itself is the documentation: budgets, review questions, params, parts
            print(f"# {kind[:-1]} {a.name}: {f}")
            print(f.read_text().rstrip())
            return 0
    from .registry import suggest

    names = list(m["shapes"]) + list(m["ops"]) + list(m["views"]) + list(m["modes"]) + list(m["point_generators"]) + list(m["part_features"])
    names += [n for k in ("profiles", "styles", "packs", "components") for n in paths.names(k)]
    print(f"unknown name '{a.name}'.{suggest(a.name, names)}")
    return 2


def cmd_stats(a):
    asset, surface = _load(a.asset, a.set)
    b = asset.bounds()
    budget = asset.budget.get("triangles")
    if a.json:
        print(json.dumps({
            "asset": asset.name, "triangles": asset.n_tris, "budget": budget, "bounds": b.round(4).tolist(),
            "parts": [{"name": p.name, "part": p.base, "tris": p.mesh.n_tris, "size": p.mesh.size().round(4).tolist(),
                       "center": p.mesh.center().round(4).tolist(), "material": p.material, "parent": p.parent} for p in asset.parts],
            "sockets": {s.name: s.position.round(4).tolist() for s in asset.sockets}, "params": asset.env}, indent=1))
        return 0
    size = b[1] - b[0]
    print(f"{asset.name}  tris {asset.n_tris}{'/' + str(budget) if budget else ''}  size {size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f} m (x w, y h, z d)  "
          f"build {asset.build_ms:.0f} ms")
    print(f"{'part':24} {'tris':>5}  {'size x y z (m)':22} {'center x y z (m)':24} material")
    for p in asset.parts:
        s, c = p.mesh.size(), p.mesh.center()
        print(f"{p.name:24} {p.mesh.n_tris:5}  {s[0]:6.3f} {s[1]:6.3f} {s[2]:6.3f}   {c[0]:7.3f} {c[1]:7.3f} {c[2]:7.3f}   {p.material or '-'}")
    if asset.sockets:
        print("sockets: " + ", ".join(f"{s.name}@({s.position[0]:.2f},{s.position[1]:.2f},{s.position[2]:.2f})" for s in asset.sockets))
    print("params: " + ", ".join(f"{k}={v:g}" for k, v in asset.env.items()))
    return 0


def cmd_validate(a):
    from .validate.run import dump, format_text, run_validation

    asset, surface = _load(a.asset, a.set)
    report = run_validation(asset, surface)
    (asset.build_dir / "report.json").write_text(dump(report))
    print(dump(report) if a.json else format_text(report, a.verbose))
    return 1 if report["status"] == "FAIL" else 0


def cmd_render(a):
    from .render.views import VIEWS, contact_sheet, render, render_uv

    asset, surface = _load(a.asset, a.set)
    out_dir = asset.build_dir / "renders"
    out_dir.mkdir(exist_ok=True)
    size = min(a.size, LIMITS.max_render_size)
    focus = [x.strip() for p in (a.part or []) for x in p.split(",") if x.strip()] or None
    for f in focus or []:
        if not asset.parts_named(f):
            from .registry import suggest

            print(f"unknown part '{f}'.{suggest(f, {p.name for p in asset.parts} | {p.base for p in asset.parts})}")
            return 2
    paths = []
    suffix = ("_" + "_".join(focus)) if focus else ""
    if a.turntable or a.present:
        from .render import beauty

        if a.turntable:
            paths += beauty.save_turntable(beauty.turntable(asset, surface, max(4, min(a.turntable, 72)), min(size, 512)),
                                           out_dir / "turntable.gif")
        if a.present:
            p = out_dir / "present.png"
            beauty.present_sheet(asset, surface, max(size // 2, 256), focus).save(p)
            paths.append(p)
    elif a.sheet:
        p = out_dir / f"sheet{suffix}.png"
        contact_sheet(asset, surface, tile=max(size // 2, 192), focus=focus).save(p)
        paths.append(p)
    else:
        views = a.view or ["front_right"]
        modes = a.mode or ["clay"]
        for v in views:
            if v not in VIEWS and v != "uv":
                from .registry import suggest

                print(f"unknown view '{v}'.{suggest(v, VIEWS)}")
                return 2
            for m in modes:
                if v == "uv" or m == "uv":
                    img, p = render_uv(asset, surface, size, focus), out_dir / f"uv{suffix}.png"
                else:
                    img = render(asset, surface, v, m, size, focus=focus, isolate=a.isolate, scale_ref=a.scale_ref)
                    p = out_dir / f"{v}_{m}{suffix}{'_iso' if a.isolate else ''}.png"
                img.save(p)
                paths.append(p)
    for p in dict.fromkeys(paths):
        print(_rel(p))
    return 0


def cmd_review(a):
    from .render.views import contact_sheet
    from .validate.run import dump, format_text, run_validation

    asset, surface = _load(a.asset, a.set)
    report = run_validation(asset, surface)
    (asset.build_dir / "report.json").write_text(dump(report))
    sheet = asset.build_dir / "sheet.png"
    contact_sheet(asset, surface, tile=a.size).save(sheet)
    print(format_text(report, a.verbose))
    print(f"\nsheet: {_rel(sheet)}   (front/right/top ortho clay, 3/4 clay, parts, back 3/4, wire, UV)")
    style = asset.style or {}
    if style:
        print(f"\nSTYLE '{style.get('name')}': {' '.join(str(style.get('description', '')).split())}")
    questions = list(style.get("review") or []) + list((asset.source.get("review") or []))
    base_q = [
        "Is the object instantly recognizable from the front_right view and the silhouette?",
        "Are proportions between named parts plausible (compare sizes in `sw stats`)?",
        "Is there wasted density (wire view) or missing detail at the primary forms?",
    ]
    print("\nLOOK AT THE SHEET AND ANSWER (write findings as: part.param -> change, reason):")
    for q in base_q + questions:
        print(f"  - {q}")
    print("\nThen: edit asset.yaml, `sw review` again, `sw snapshot -m ... --critique ...`, `sw compare A B`.")
    return 1 if report["status"] == "FAIL" else 0


def cmd_snapshot(a):
    from .assemble import resolve_asset_path
    from .history import snapshot

    try:
        res = snapshot(resolve_asset_path(a.asset), a.message or "", a.critique or "")
    except SourceError as e:
        _print_source_error(e, False)
        print("nothing recorded: the source does not build (fix it, then snapshot)")
        return 2
    if res.get("unchanged"):
        print(f"unchanged since iteration {res['iteration']} (source hash identical); nothing recorded")
    else:
        print(f"iteration {res['iteration']} recorded ({res['status']}) -> {_rel(Path(res['path']))}")
    return 0


def cmd_feedback(a):
    from . import feedback
    from .assemble import resolve_asset_path

    d = resolve_asset_path(a.asset).parent
    try:
        if a.action == "add":
            n = feedback.add(d, " ".join(a.text), a.part, a.at, a.normal, a.view, a.image)
            print(f"note #{n['id']} added -> {_rel(feedback.path_for(d))}")
        elif a.action == "resolve":
            if not a.text or not a.text[0].isdigit():
                print("usage: sw feedback ASSET resolve ID [--reply TEXT]")
                return 2
            n = feedback.resolve(d, int(a.text[0]), a.reply or "")
            print(f"note #{n['id']} resolved")
        else:
            notes = feedback.load(d)
            print(json.dumps(notes, indent=1) if a.json else feedback.format_notes(notes, a.all))
    except ValueError as e:
        print(str(e))
        return 2
    return 0


def cmd_log(a):
    from .assemble import resolve_asset_path
    from .history import log

    entries = log(resolve_asset_path(a.asset))
    if a.json:
        print(json.dumps(entries, indent=1))
        return 0
    if not entries:
        print("no iterations yet (sw snapshot ASSET -m 'note')")
    for e in entries:
        m = e.get("metrics", {})
        print(f"#{e['iteration']:<3} {e['status']:4} tris {m.get('triangles')}  {e.get('note', '')}")
        if e.get("critique"):
            print(f"      critique: {e['critique']}")
    return 0


def cmd_compare(a):
    from . import paths
    from .assemble import resolve_asset_path
    from .history import compare

    path = resolve_asset_path(a.asset)
    metrics, img = compare(path, a.a, a.b, size=a.size)
    out = paths.out_dir(path.parent) / ".build" / f"compare_{a.a}_{a.b}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    metrics["image"] = _rel(out)
    print(compact_json(metrics))
    return 0


def cmd_restore(a):
    from .assemble import resolve_asset_path
    from .history import restore

    backup = restore(resolve_asset_path(a.asset), a.n)
    print(f"restored iteration {a.n}; previous source saved to {_rel(backup)}")
    return 0


def cmd_export(a):
    from .export.gltf import write_glb
    from .export.verify import khronos_validate, roundtrip
    from .validate.run import collect, dump, format_text, make_report

    asset, surface = _load(a.asset, a.set)
    if a.target:  # one asset, several engines (FRESH_AGENT_08 needed a variant per engine)
        asset._export_target = a.target
    found, metrics = collect(asset, surface)  # validators run once (Phase 10: export used to run them twice)
    report = make_report(asset, found, metrics)
    if report["status"] == "FAIL" and not a.force:
        print(format_text(report))
        print("\nexport refused: fix the errors above (or pass --force for a debug export)")
        return 1
    suffix = f"_{a.target}" if a.target else ""
    suffix += "_preview" if a.preview else ""
    out = Path(a.out) if a.out else asset.out_dir / "export" / f"{asset.name}{suffix}.glb"
    from .export.gltf import collision_proxies

    proxies = [] if a.preview else collision_proxies(asset)  # computed once: LOD files reuse LOD0's collision
    info = write_glb(asset, surface, out, report["status"], collision=proxies)
    issues, extra = khronos_validate(out)
    issues += roundtrip(asset, out)
    from .export.targets import export_settings

    settings = export_settings(asset)
    lods = []
    if settings["lods"] and settings["target"].lod_files and not a.preview:
        from .export.lod import write_lods
        from .report import Issue

        lods = write_lods(asset, surface, out, settings["lods"], report["status"], proxies)
        for lod in lods:
            if lod["silhouette_iou"] < (0.95 if lod["lod"] == 1 else 0.9):  # Phase 21 gate: LOD1 >= 0.95, further LODs >= 0.90
                issues.append(Issue("LOD_SILHOUETTE", "warning", f"LOD{lod['lod']} ({lod['triangles']} tris) keeps only "
                                    f"{lod['silhouette_iou']:.0%} of LOD0's silhouette in its worst view", f"export.lods[{lod['lod'] - 1}]",
                                    "export", "use a milder ratio for this LOD"))
            lod["path"] = _rel(Path(lod["path"]))
    final = make_report(asset, found, metrics, issues, exported=True)
    final["metrics"].update(extra)
    final["export"] = {**info, "path": _rel(out), "target": settings["target"].name, "merge": settings["merge"], "lods": lods}
    (out.with_suffix(".report.json")).write_text(dump(final))
    if a.json:
        print(dump(final))
    else:
        print(format_text(final))
        print(f"exported {_rel(out)} ({info['bytes']} bytes, {info['meshes']} meshes, {info['materials']} materials)")
        print(f"report   {_rel(out.with_suffix('.report.json'))}")
    return 1 if final["status"] == "FAIL" else 0


def cmd_new(a):
    from . import paths
    from .assemble import ROOT

    base = Path(a.dir) if a.dir else paths.assets_home()
    d = base / a.name
    if (d / "asset.yaml").exists():
        print(f"{_rel(d / 'asset.yaml')} already exists")
        return 2
    d.mkdir(parents=True, exist_ok=True)
    if a.from_:
        from .assemble import resolve_asset_path

        src = resolve_asset_path(a.from_)
        rel = _extends_path(src.parent, d)
        text = f"shapewright: 0.1\nextends: {rel}\nasset: {{name: {a.name}}}\n\n# Override only what differs from the base asset.\nparams: {{}}\n"
    else:
        text = (ROOT / "templates" / "asset.yaml").read_text().replace("NAME", a.name)
    (d / "asset.yaml").write_text(text)
    name = a.name if d.parent.resolve() == paths.assets_home().resolve() else _rel(d)  # a name where a name works
    print(f"created {_rel(d / 'asset.yaml')}  next: edit it, then `sw review {name}`")
    return 0


def cmd_variants(a):
    import yaml

    from . import paths
    from .assemble import build, resolve_asset_path
    from .source import param_spec

    path = resolve_asset_path(a.asset)
    asset = build(path)
    specs = {k: param_spec(v) for k, v in (asset.source.get("params") or {}).items()}
    vary = {k: s["vary"] for k, s in specs.items() if s.get("vary")}
    if not vary:
        print("no params declare `vary: [min, max]`; add some to generate variants")
        return 2
    rng = np.random.default_rng(a.seed)
    created = []
    for i in range(1, a.count + 1):
        name = f"{asset.name}_v{i:02d}"
        d = paths.assets_home() / name  # the project's assets/ (Phase 18 doc test: they were written into the library)
        d.mkdir(parents=True, exist_ok=True)
        params = {}
        for k, (lo, hi) in vary.items():
            v = rng.uniform(lo, hi)
            params[k] = int(round(v)) if k == "seed" or isinstance(specs[k]["value"], int) and float(lo).is_integer() and float(hi).is_integer() else round(float(v), 4)
        doc = {"shapewright": 0.1, "extends": _extends_path(path.parent, d), "asset": {"name": name}, "params": params}
        (d / "asset.yaml").write_text(f"# generated by `sw variants {asset.name} --seed {a.seed}`\n" + yaml.safe_dump(doc, sort_keys=False))
        created.append(d)
    for d in created:
        try:
            v = build(d / "asset.yaml")
            print(f"{_rel(d)}  tris {v.n_tris}")
        except SourceError as e:
            print(f"{_rel(d)}  FAILED: {e.issues[0].line()}")
    return 0


def cmd_import(a):
    from . import paths
    from .importer import import_file

    base = Path(a.dir) if a.dir else paths.assets_home()
    res = import_file(Path(a.file), base / a.name, a.name, split=a.split, scale=a.scale, z_up=a.z_up)
    print(f"created {_rel(Path(res['asset']))} with {len(res['parts'])} part(s):")
    for r in res["parts"][:40]:
        print(f"  {r['part']:24} tris {r['triangles']:6}  {'closed' if r['closed'] else 'OPEN (tagged open_ok)'}  node '{r['node']}'")
    if res["skipped_collision"]:
        print(f"skipped {len(res['skipped_collision'])} collision proxy node(s) (UCX_/-colonly); set `collision:` to regenerate them")
    print(f"next: sw render {a.name} --mode parts --view front_right, then rename parts in asset.yaml")
    return 0


def cmd_uv(a):
    from .assemble import build, resolve_asset_path
    from .surface import build_surface, write_lock

    asset = build(resolve_asset_path(a.asset))
    if a.action == "lock":
        p = write_lock(asset)
        print(f"wrote {_rel(p)} ({len(build_surface(asset).regions)} UV regions); commit it")
    else:
        s = build_surface(asset)
        print(f"method {s.uv_method}  lock {s.lock}  owners {len(s.regions)}")
        for o, r in sorted(s.regions.items()):
            print(f"  {o:28} [{r[0]:.3f}, {r[1]:.3f}] - [{r[2]:.3f}, {r[3]:.3f}]")
        if s.lock_notes:
            print("  changed since lock / mismatched: " + ", ".join(s.lock_notes))
    return 0


def cmd_family(a):
    """Validate a base asset and every asset that extends it (directly or transitively)."""
    from .assemble import build, resolve_asset_path
    from .source import read_yaml
    from .surface import build_surface
    from .validate.run import run_validation

    base = resolve_asset_path(a.asset).resolve()
    members = [base]
    changed = True
    while changed:
        changed = False
        for p in sorted(base.parent.parent.glob("*/asset.yaml")):
            p = p.resolve()
            if p in members:
                continue
            ext = read_yaml(p).get("extends")
            if ext and ((p.parent / ext).resolve() / "asset.yaml" in members or (p.parent / ext).resolve() in members):
                members.append(p)
                changed = True
    worst = 0
    for p in members:
        try:
            asset = build(p)
            r = run_validation(asset, build_surface(asset))
            errs = [i["code"] for i in r["issues"] if i["severity"] == "error"]
            print(f"{r['status']:4} {asset.name:28} tris {asset.n_tris:5}  {' '.join(errs)}")
            worst = max(worst, 1 if r["status"] == "FAIL" else 0)
        except SourceError as e:
            print(f"FAIL {p.parent.name:28} {e.issues[0].code}: {e.issues[0].message}")
            worst = 2
    iface = read_yaml(base).get("interface")
    print(f"{len(members)} member(s); interface: {', '.join((iface or {}).get('params', [])) or 'NONE (variants depend on internals)'}")
    return worst


def cmd_bench(a):
    from . import paths
    from .assemble import build
    from .surface import build_surface
    from .validate.run import run_validation

    base = Path(a.dir) if a.dir else paths.assets_home()
    worst = 0
    for p in sorted(base.glob("*/asset.yaml")):
        try:
            asset = build(p)
            r = run_validation(asset, build_surface(asset))
            m = r["metrics"]
            errs = [i["code"] for i in r["issues"] if i["severity"] == "error"]
            print(f"{r['status']:4} {asset.name:28} tris {m['triangles']:5}/{m.get('budget_triangles', '-')!s:5} {' '.join(errs)}")
            worst = max(worst, 1 if r["status"] == "FAIL" else 0)
        except SourceError as e:
            print(f"FAIL {p.parent.name:28} source: {e.issues[0].code}")
            worst = 2
    return worst


def cmd_pack(a):
    from .pack import format_pack, pack_sheet, run_pack, select, sheet_path

    paths = select(a.assets or [], a.tag, pack=a.pack)
    if len(paths) < 2:
        print("a pack needs at least two assets: name them, select members with --pack NAME (their `pack:`), or --tag TAG")
        return 2
    assets, surfaces, reports, rep = run_pack(paths)
    if a.json:
        print(json.dumps(rep, indent=1))
    else:
        print(format_pack(rep))
    out = Path(a.out) if a.out else sheet_path(a.pack or a.tag or "_".join(x.name for x in assets[:3]))
    pack_sheet(assets, surfaces, tile=a.size).save(out)
    print(f"\npack sheet: {_rel(out)}   (rows: front ortho clay, 3/4 material, 3/4 silhouette; one common scale)")
    print("LOOK AT IT: same scale and ground? same plank / leg / band language? same palette? similar detail density?")
    return 1 if any(r["status"] == "FAIL" for r in reports) else 0


def cmd_materials(a):
    from .preview import material_sheet

    asset, _ = _load(a.asset, a.set)
    out = asset.build_dir / "materials.png"
    img, notes = material_sheet(asset, tile=a.size)
    img.save(out)
    for n in notes:
        print(n)
    print(f"material sheet: {_rel(out)}   (top: lit textured on reference shapes, bottom: unlit albedo)")
    return 0


def cmd_mcp(a):
    from .mcp_server import main as mcp_main

    return mcp_main(transport=a.transport, project=a.project, host=a.host, port=a.port)


def cmd_init(a):
    from . import paths

    d = Path(a.dir).resolve()
    marker = d / paths.MARKER
    if marker.exists():
        print(f"{_rel(marker)} already exists: this is a Shapewright project")
        return 0
    for sub_ in ("assets", "packs", "components", "styles", "profiles"):
        (d / sub_).mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "# Shapewright project marker. `sw` run anywhere inside this folder uses it as the project:\n"
        "# assets/ holds your assets; packs/, components/, styles/, profiles/ shadow the library's files of the same name.\n"
        "shapewright: 0.1\n")
    print(f"initialised Shapewright project in {_rel(d)}")
    print("next: sw brief \"what you want to make\"   then   sw new NAME   (library examples stay usable by name)")
    return 0


def cmd_doctor(a):
    import importlib
    import shutil

    from .export.verify import VALIDATOR_DIR

    ok = True
    for mod, why in [("numpy", "core"), ("yaml", "sources"), ("trimesh", "hulls, checks"), ("manifold3d", "booleans, contact tests"),
                     ("xatlas", "UV unwrapping"), ("PIL", "rendering"), ("scipy", "hulls"), ("fast_simplification", "decimate op")]:
        try:
            m = importlib.import_module(mod)
            print(f"ok   {mod:20} {getattr(m, '__version__', '')}  ({why})")
        except ImportError:
            ok = False
            print(f"MISS {mod:20} ({why})  -> pip install -r requirements.txt")
    from . import paths

    print(f"lib  {paths.LIB}")
    print(f"proj {paths.project() or '(none: run `sw init` to make the current folder a project)'}")
    node = shutil.which("node")
    kv = (VALIDATOR_DIR / "node_modules" / "gltf-validator").exists()
    print(f"{'ok  ' if node and kv else 'opt '} khronos gltf-validator  {'installed' if kv else 'optional: cd tools/gltf-validator && npm install'}")
    return 0 if ok else 1


# ------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sw", description="Shapewright: agent-native 3D modelling. Start with `sw brief REQUEST` and AGENTS.md.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, asset=True):
        p = sub.add_parser(name, help=help_)
        if asset:
            p.add_argument("asset", help="asset directory, asset.yaml path, or name under assets/")
            if name in ("stats", "validate", "render", "review", "materials", "export"):
                p.add_argument("--set", action="append", metavar="PARAM=VALUE[,..]",
                               help="try param values without editing the source (e.g. --set steps=14,rise=0.2)")
        p.set_defaults(fn=fn)
        return p

    p = add("brief", cmd_brief, "start here: closest example asset, profile, rules and vocabulary for a request", asset=False)
    p.add_argument("request", nargs="+", help="the request in words, e.g. \"a hanging tavern sign, mobile, under 1200 triangles\"")
    p = add("set", cmd_set, "write param values into the source (keeps comments): sw set ASSET name=value[,name=value]")
    p.add_argument("values", nargs="+", metavar="NAME=VALUE")
    p = add("workbench", cmd_workbench, "local browser workbench for people: every button runs (and shows) an sw command", asset=False)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true", help="open it in the default browser")
    p.add_argument("--assets", help="folder of assets to work on (default: assets/)")
    p = add("caps", cmd_caps, "capability manifest", asset=False)
    p.add_argument("--json", action="store_true")
    p.add_argument("--llms", action="store_true", help="print llms.txt: a one-page brief for AI agents")
    p = add("doc", cmd_doc, "details for a shape/op/view/mode/issue code", asset=False)
    p.add_argument("name")
    p = add("stats", cmd_stats, "per-part numbers")
    p.add_argument("--json", action="store_true")
    p = add("validate", cmd_validate, "layered validation")
    p.add_argument("--json", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p = add("render", cmd_render, "inspection images")
    p.add_argument("--view", action="append", help="front back left right top bottom front_right front_left back_right back_left low_front uv")
    p.add_argument("--mode", action="append", help="clay parts material wire normals silhouette provenance regions textured albedo roughness metallic texel seams; "
                   "beauty = presentation render (shadows, AO; for README/portfolio images)")
    p.add_argument("--turntable", type=int, metavar="N", help="N beauty frames around the asset -> renders/turntable.gif (+ .mp4 with imageio-ffmpeg)")
    p.add_argument("--present", action="store_true", help="presentation sheet -> renders/present.png (beauty views, details: --part, wireframe, palette)")
    p.add_argument("--scale-ref", action="store_true", help="orthographic side views: a 1.75 m human figure and overall dimension lines")
    p.add_argument("--part", action="append", help="highlight part(s): source or instance names; repeat or comma-separate")
    p.add_argument("--isolate", action="store_true", help="render only the --part parts")
    p.add_argument("--sheet", action="store_true", help="contact sheet of standard views")
    p.add_argument("--size", type=int, default=512)
    p = add("review", cmd_review, "validate + sheet + checklist")
    p.add_argument("--size", type=int, default=320, help="tile size of the sheet")
    p.add_argument("--verbose", "-v", action="store_true", help="also show info items")
    p = add("snapshot", cmd_snapshot, "record an iteration")
    p.add_argument("-m", "--message")
    p.add_argument("--critique")
    p = add("log", cmd_log, "list iterations")
    p.add_argument("--json", action="store_true")
    p = add("compare", cmd_compare, "compare two iterations")
    p.add_argument("a", help="iteration number, 'last' or 'current'")
    p.add_argument("b", help="iteration number, 'last' or 'current'")
    p.add_argument("--size", type=int, default=320)
    p = add("restore", cmd_restore, "restore an iteration's source")
    p.add_argument("n", type=int)
    p = add("export", cmd_export, "export GLB")
    p.add_argument("--target", choices=["generic", "godot", "unity", "unreal"],
                   help="engine packaging for this export (default: the profile's); writes export/NAME_TARGET.glb")
    p.add_argument("--out")
    p.add_argument("--preview", action="store_true",
                   help="a file for web viewers: no collision proxies, no LOD files; writes export/NAME_preview.glb")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("new", help="scaffold a new asset")
    p.add_argument("name")
    p.add_argument("--from", dest="from_", help="create a variant that extends this asset")
    p.add_argument("--dir", help="parent directory (default: ./assets)")
    p.set_defaults(fn=cmd_new)
    p = add("variants", cmd_variants, "seeded variants")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p = sub.add_parser("import", help="create an asset from a GLB/OBJ/STL/PLY file")
    p.add_argument("file")
    p.add_argument("name")
    p.add_argument("--split", action="store_true", help="one part per connected piece")
    p.add_argument("--scale", type=float, default=1.0, help="unit conversion (0.01 for cm files)")
    p.add_argument("--z-up", action="store_true", help="file is Z-up")
    p.add_argument("--dir", help="parent directory (default: ./assets)")
    p.set_defaults(fn=cmd_import)
    p = add("feedback", cmd_feedback, "notes a person pinned on the model (workbench): list, add, resolve")
    p.add_argument("action", nargs="?", default="list", choices=["list", "add", "resolve"])
    p.add_argument("text", nargs="*", help="add: the note; resolve: the note id")
    p.add_argument("--part", help="add: the part the note is about")
    p.add_argument("--at", help="add: the point x,y,z (metres, asset coordinates)")
    p.add_argument("--normal", help="add: the surface normal at the point x,y,z")
    p.add_argument("--view", help="add: where it was seen from (a view name or 'orbit')")
    p.add_argument("--image", help="add: a screenshot path (relative to the asset's .build/)")
    p.add_argument("--reply", help="resolve: what was changed")
    p.add_argument("--all", action="store_true", help="list resolved notes too")
    p.add_argument("--json", action="store_true")
    p = add("uv", cmd_uv, "UV regions: `sw uv ASSET lock` writes uv.lock.yaml; `show` lists regions")
    p.add_argument("action", choices=("lock", "show"))
    p = add("family", cmd_family, "validate a base asset and all its variants")
    p = add("materials", cmd_materials, "material sheet (each material on reference shapes)")
    p.add_argument("--size", type=int, default=256)
    p = add("bench", cmd_bench, "validate all assets", asset=False)
    p.add_argument("--dir")
    p = add("pack", cmd_pack, "review several assets as one set (common-scale sheet + consistency report)", asset=False)
    p.add_argument("assets", nargs="*", help="asset names/paths (or use --tag)")
    p.add_argument("--pack", help="select every asset whose source says `pack: NAME`")
    p.add_argument("--tag", help="select every asset under assets/ whose asset.tags contains TAG")
    p.add_argument("--out", help="sheet path (default: .build/packs/<tag>.png)")
    p.add_argument("--size", type=int, default=300, help="tile size")
    p.add_argument("--json", action="store_true")
    p = add("mcp", cmd_mcp, "run the MCP server (tools: brief, new, write_source, review, render, export, ...)", asset=False)
    p.add_argument("--transport", choices=("stdio", "streamable-http", "sse"), default="stdio")
    p.add_argument("--project", help="project folder (default: $SW_PROJECT, a shapewright.yaml above cwd, or cwd)")
    p.add_argument("--host", default="127.0.0.1", help="HTTP transports only (default: localhost)")
    p.add_argument("--port", type=int, default=8000, help="HTTP transports only")
    p = add("init", cmd_init, "make a folder a Shapewright project (assets/, packs/, components/ + marker)", asset=False)
    p.add_argument("dir", nargs="?", default=".")
    add("doctor", cmd_doctor, "environment check", asset=False)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(signal, "SIGALRM") and args.cmd not in ("workbench", "mcp"):  # the server runs until stopped; each command it runs has its own
        def _timeout(*_):
            raise TimeoutError(f"command exceeded {LIMITS.build_timeout_s}s (see shapewright/limits.py)")

        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(LIMITS.build_timeout_s * (4 if args.cmd in ("bench", "variants", "compare") else 1))
    t0 = time.perf_counter()
    try:
        rc = args.fn(args)
        if not getattr(args, "json", False) and args.cmd not in ("caps", "doc", "mcp"):
            print(f"({args.cmd}: {time.perf_counter() - t0:.1f} s)", file=sys.stderr)
        return rc
    except SourceError as e:
        return _print_source_error(e, getattr(args, "json", False))
    except (FileNotFoundError, FileExistsError, TimeoutError, ValueError) as e:
        print(f"error: {e}")
        return 2
    except BrokenPipeError:  # output piped into head etc.
        return 0
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)  # a long-lived caller (sw workbench) must not get a stale alarm


if __name__ == "__main__":
    sys.exit(main())
