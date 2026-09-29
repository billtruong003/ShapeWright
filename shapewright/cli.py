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
from pathlib import Path

import numpy as np

from .limits import LIMITS
from .report import SourceError, compact_json


def _rel(p: Path) -> str:
    try:
        return os.path.relpath(p)
    except ValueError:
        return str(p)


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

    data = yaml.safe_load(path.read_text())
    params = dict(data.get("params") or {})
    for k, v in overrides.items():
        if k not in params:
            from .registry import suggest

            raise ValueError(f"--set: '{k}' is not a param of this asset.{suggest(k, params)}")
        params[k] = {**params[k], "value": v} if isinstance(params[k], dict) else v
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

    print(json.dumps(manifest(), indent=1) if a.json else summary_text())
    return 0


def cmd_doc(a):
    from .caps import manifest

    m = manifest()
    for fam in ("shapes", "ops"):
        if a.name in m[fam]:
            print(compact_json({fam[:-1]: a.name, **m[fam][a.name]}))
            return 0
    if a.name in m["views"] or a.name in m["modes"]:
        print(m["views"].get(a.name) or m["modes"].get(a.name))
        return 0
    for v in m["validators"]:
        if a.name in v["codes"] or a.name == v["name"]:
            print(compact_json(v))
            print("See docs/VALIDATION.md for the meaning and fixes of each code.")
            return 0
    from .registry import suggest

    names = list(m["shapes"]) + list(m["ops"]) + list(m["views"]) + list(m["modes"])
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
    if a.sheet:
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
                    img = render(asset, surface, v, m, size, focus=focus, isolate=a.isolate)
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

    res = snapshot(resolve_asset_path(a.asset), a.message or "", a.critique or "")
    if res.get("unchanged"):
        print(f"unchanged since iteration {res['iteration']} (source hash identical); nothing recorded")
    else:
        print(f"iteration {res['iteration']} recorded ({res['status']}) -> {_rel(Path(res['path']))}")
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
    from .assemble import resolve_asset_path
    from .history import compare

    path = resolve_asset_path(a.asset)
    metrics, img = compare(path, a.a, a.b, size=a.size)
    out = path.parent / ".build" / f"compare_{a.a}_{a.b}.png"
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
    from .validate.run import dump, format_text, run_validation

    asset, surface = _load(a.asset)
    report = run_validation(asset, surface)
    if report["status"] == "FAIL" and not a.force:
        print(format_text(report))
        print("\nexport refused: fix the errors above (or pass --force for a debug export)")
        return 1
    out = Path(a.out) if a.out else asset.dir / "export" / f"{asset.name}.glb"
    info = write_glb(asset, surface, out, report["status"])
    issues, extra = khronos_validate(out)
    issues += roundtrip(asset, out)
    final = run_validation(asset, surface, issues, exported=True)
    final["metrics"].update(extra)
    final["export"] = {**info, "path": _rel(out)}
    (out.with_suffix(".report.json")).write_text(dump(final))
    if a.json:
        print(dump(final))
    else:
        print(format_text(final))
        print(f"exported {_rel(out)} ({info['bytes']} bytes, {info['meshes']} meshes, {info['materials']} materials)")
        print(f"report   {_rel(out.with_suffix('.report.json'))}")
    return 1 if final["status"] == "FAIL" else 0


def cmd_new(a):
    from .assemble import ROOT

    base = Path(a.dir) if a.dir else (Path.cwd() / "assets" if (Path.cwd() / "assets").exists() else ROOT / "assets")
    d = base / a.name
    if (d / "asset.yaml").exists():
        print(f"{_rel(d / 'asset.yaml')} already exists")
        return 2
    d.mkdir(parents=True, exist_ok=True)
    if a.from_:
        from .assemble import resolve_asset_path

        src = resolve_asset_path(a.from_)
        rel = os.path.relpath(src.parent, d)
        text = f"shapewright: 0.1\nextends: {rel}\nasset: {{name: {a.name}}}\n\n# Override only what differs from the base asset.\nparams: {{}}\n"
    else:
        text = (ROOT / "templates" / "asset.yaml").read_text().replace("NAME", a.name)
    (d / "asset.yaml").write_text(text)
    print(f"created {_rel(d / 'asset.yaml')}  next: edit it, then `sw review {_rel(d)}`")
    return 0


def cmd_variants(a):
    import yaml

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
        d = path.parent.parent / name
        d.mkdir(exist_ok=True)
        params = {}
        for k, (lo, hi) in vary.items():
            v = rng.uniform(lo, hi)
            params[k] = int(round(v)) if k == "seed" or isinstance(specs[k]["value"], int) and float(lo).is_integer() and float(hi).is_integer() else round(float(v), 4)
        doc = {"shapewright": 0.1, "extends": f"../{path.parent.name}", "asset": {"name": name}, "params": params}
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
    from .assemble import ROOT
    from .importer import import_file

    base = Path(a.dir) if a.dir else (Path.cwd() / "assets" if (Path.cwd() / "assets").exists() else ROOT / "assets")
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
    from .assemble import ROOT, build
    from .surface import build_surface
    from .validate.run import run_validation

    base = Path(a.dir) if a.dir else ROOT / "assets"
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
    node = shutil.which("node")
    kv = (VALIDATOR_DIR / "node_modules" / "gltf-validator").exists()
    print(f"{'ok  ' if node and kv else 'opt '} khronos gltf-validator  {'installed' if kv else 'optional: cd tools/gltf-validator && npm install'}")
    return 0 if ok else 1


# ------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sw", description="Shapewright: agent-native 3D modelling. Start with `sw caps` and AGENTS.md.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, asset=True):
        p = sub.add_parser(name, help=help_)
        if asset:
            p.add_argument("asset", help="asset directory, asset.yaml path, or name under assets/")
            if name in ("stats", "validate", "render", "review"):
                p.add_argument("--set", action="append", metavar="PARAM=VALUE[,..]",
                               help="try param values without editing the source (e.g. --set steps=14,rise=0.2)")
        p.set_defaults(fn=fn)
        return p

    p = add("caps", cmd_caps, "capability manifest", asset=False)
    p.add_argument("--json", action="store_true")
    p = add("doc", cmd_doc, "details for a shape/op/view/mode/issue code", asset=False)
    p.add_argument("name")
    p = add("stats", cmd_stats, "per-part numbers")
    p.add_argument("--json", action="store_true")
    p = add("validate", cmd_validate, "layered validation")
    p.add_argument("--json", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p = add("render", cmd_render, "inspection images")
    p.add_argument("--view", action="append", help="front back left right top bottom front_right front_left back_right back_left low_front uv")
    p.add_argument("--mode", action="append", help="clay parts material wire normals silhouette")
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
    p.add_argument("--out")
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
    p = add("uv", cmd_uv, "UV regions: `sw uv ASSET lock` writes uv.lock.yaml; `show` lists regions")
    p.add_argument("action", choices=("lock", "show"))
    p = add("family", cmd_family, "validate a base asset and all its variants")
    p = add("bench", cmd_bench, "validate all assets", asset=False)
    p.add_argument("--dir")
    p = add("pack", cmd_pack, "review several assets as one set (common-scale sheet + consistency report)", asset=False)
    p.add_argument("assets", nargs="*", help="asset names/paths (or use --tag)")
    p.add_argument("--pack", help="select every asset whose source says `pack: NAME`")
    p.add_argument("--tag", help="select every asset under assets/ whose asset.tags contains TAG")
    p.add_argument("--out", help="sheet path (default: .build/packs/<tag>.png)")
    p.add_argument("--size", type=int, default=300, help="tile size")
    p.add_argument("--json", action="store_true")
    add("doctor", cmd_doctor, "environment check", asset=False)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(signal, "SIGALRM"):
        def _timeout(*_):
            raise TimeoutError(f"command exceeded {LIMITS.build_timeout_s}s (see shapewright/limits.py)")

        signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(LIMITS.build_timeout_s * (4 if args.cmd in ("bench", "variants", "compare") else 1))
    try:
        return args.fn(args)
    except SourceError as e:
        return _print_source_error(e, getattr(args, "json", False))
    except (FileNotFoundError, FileExistsError, TimeoutError, ValueError) as e:
        print(f"error: {e}")
        return 2
    except BrokenPipeError:  # output piped into head etc.
        return 0


if __name__ == "__main__":
    sys.exit(main())
