"""Loading, schema-checking and parameter resolution for asset sources.

An asset source (``asset.yaml``) is declarative data. This module turns it
into a normalized dictionary plus a resolved parameter environment, reporting
every problem with a source path such as ``parts.backrest.shape.size[0]``.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import yaml

from . import expr
from .limits import LIMITS
from .registry import OPS, REQUIRED, SHAPES, OpSpec, suggest
from .report import Issue, SourceError

FORMAT_VERSION = "0.1"

TOP_KEYS = {
    "shapewright": "format version",
    "extends": "path of a base asset whose source this one overrides",
    "asset": "name, kind, description, tags",
    "profile": "production profile name (profiles/*.yaml)",
    "style": "style profile name (styles/*.yaml)",
    "budget": "overrides of profile budgets, e.g. {triangles: 700}",
    "params": "named numeric parameters (value or expression)",
    "materials": "named PBR materials",
    "parts": "semantic parts: shape + ops + placement",
    "sockets": "named attachment points exported as empty nodes",
    "checks": "design-intent assertions evaluated after build",
    "uv": "UV generation settings",
    "collision": "collision proxies: {mode: none | single_box | single_hull | box | hull, parts: [...]}",
    "export": "engine packaging: {target: generic | godot | unity | unreal, merge: none | by_material, lods: [0.5, 0.25]}",
    "notes": "free text for humans and agents",
    "interface": "family contract for variants: {params: [public names], doc} (see docs/FAMILIES.md)",
    "pack": "shared pack vocabulary: name (packs/NAME.yaml) or relative .yaml path; its params/materials are read-only here",
}

PACK_KEYS = {
    "shapewright": "format version", "pack": "pack name", "doc": "what the set is",
    "params": "shared construction language and scale (read-only in member assets)",
    "materials": "shared palette (read-only in member assets)",
    "profile": "production profile for every member", "style": "style for every member",
    "budget": "default budget (members may tighten or override individual keys)", "notes": "free text",
}

PART_KEYS = {
    "shape": "geometry expression {type: ..., <params>, ops, material, rotate, translate} (recursive)",
    "ops": "ordered list of modifiers applied in part-local space (after the shape's own ops)",
    "measure": "named spatial queries on already-built parts: {name: {section|gap|bounds|anchor|ray: ...}}",
    "enabled": "true | false | expression; disabled parts are not built",
    "uv": "per-part UV settings: {share_instances: true}",
    "rotate": "[rx, ry, rz] degrees, applied about the part centre before placement (or about its anchor: rotate_about)",
    "rotate_about": "center (default) | anchor: rotate about the unrotated shape's anchor point, which is then the point placed",
    "origin": "center (default) | keep: keep the shape's own coordinates (tube paths, strut ends) instead of centring; position is then an offset",
    "position": "[x, y, z] world position of the part's anchor",
    "anchor": "which point of this part is placed (default: center)",
    "attach": "{to: part, at: anchor, offset: [x,y,z]} places this part relative to another",
    "mirror": "x | y | z | [x, z] | {axis: y, at: 0.45}: add mirrored twins across a world-axis plane (default through the origin)",
    "array": "{count, offset: [x,y,z]} or {count, radial: y, angle: 360}",
    "material": "material name",
    "shading": "flat | smooth | auto (auto-smooth by angle)",
    "smooth_angle": "degrees for auto shading (default 40)",
    "parent": "semantic parent part (export hierarchy)",
    "pivot": "anchor used as the exported node origin (default: asset origin)",
    "tags": "free semantic tags",
    "doc": "one-line purpose of the part",
}

INSTANCE_KEYS = {
    "component": "component name (components/NAME.yaml)",
    "with": "values for the component's public params",
    "materials": "map component material names to asset materials, e.g. {wood: oak}",
    "enabled": "true | false | expression",
    "anchor": "anchor of the whole component group", "position": "world position of the group anchor",
    "attach": "place the group relative to another part", "rotate": "rotate the group (degrees)",
    "origin": "center (default: the group is placed by its bounding-box anchor) | keep: the component's own origin is its pivot; "
              "`position` puts that origin, `rotate` turns about it (modular kit pieces whose extents vary with options)",
    "parent": "semantic parent for the component's root parts", "tags": "tags added to every component part",
    "doc": "purpose", "array": "repeat the whole group (names: <instance>_0.., parts <instance>_0_<part>)",
    "mirror": "mirror the whole group (names: <instance>_left/_right, parts <instance>_left_<part>)",
    "measure": "spatial queries on parts built before this instance; results are usable in with/position/rotate/enabled",
    "pivot": "hinge the whole group: an anchor name, [x, y, z] box coefficients or {at: [x, y, z]}; its first root part "
             "carries the pivot and the other parts become its children (one animatable node)",
}

COMPONENT_KEYS = {
    "shapewright": "format version", "component": "component name", "doc": "what it is",
    "params": "PUBLIC parameters (the component's interface) with defaults",
    "private": "internal derived values; not settable by users",
    "parts": "parts, as in assets; may reference only parts of the same component", "notes": "free text",
}

MATERIAL_KEYS = {"base_color", "metallic", "roughness", "emissive", "alpha", "alpha_mode", "double_sided", "doc",
                 "archetype", "use", "layers"}  # + the archetype's own parameters (see `sw caps`, `sw doc wood`)


class Ctx:
    """Collects issues while resolving a source."""

    def __init__(self):
        self.issues: list[Issue] = []

    def _add(self, issue: Issue):
        # the same problem evaluated once per array instance is reported once (FRESH_AGENT_05 gate: 15 copies)
        if not any(i.code == issue.code and i.where == issue.where and i.message == issue.message for i in self.issues[-64:]):
            self.issues.append(issue)

    def error(self, code, where, message, hint=""):
        self._add(Issue(code, "error", message, where, "source", hint))

    def warn(self, code, where, message, hint=""):
        self._add(Issue(code, "warning", message, where, "source", hint))

    def raise_if_errors(self):
        if any(i.severity == "error" for i in self.issues):
            raise SourceError(self.issues)


def _deep_merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            if v is None:
                out.pop(k, None)  # `key: null` deletes an inherited entry
            else:
                out[k] = _deep_merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def read_yaml(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) > LIMITS.max_source_bytes:
        raise SourceError([Issue("SRC_LIMIT", "error", f"source larger than {LIMITS.max_source_bytes} bytes", str(path), "source")])
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        msg = str(e)
        hint = ""
        if "flow" in msg or "expected ',' or" in msg or "mapping values are not allowed" in msg:
            hint = ("inside {...} or [...] YAML splits at commas and colons: quote text and expressions that contain them, "
                    'e.g. doc: "legs, rails: dark wood" or ["atan2(a, b)", 0, 0]')
        raise SourceError([Issue("SRC_PARSE", "error", f"YAML parse error: {msg}", str(path), "source", hint)]) from None
    if not isinstance(data, dict):
        raise SourceError([Issue("SRC_PARSE", "error", "top level must be a mapping", str(path), "source")])
    return _rejoin_mapping_splits(data)


def _rejoin_mapping_splits(node):
    """Undo YAML's split of a flow mapping at commas inside an expression: {amount: max(a, b)} parses
    as {amount: "max(a", "b)": None}. Keys with no value that continue an unbalanced value are joined
    back into it. Lists are handled where numbers are read (rejoin_split_exprs)."""
    if isinstance(node, list):
        return [_rejoin_mapping_splits(v) for v in node]
    if not isinstance(node, dict):
        return node
    out: dict = {}
    open_key = None
    for k, v in node.items():
        if open_key is not None and v is None and isinstance(k, str):
            out[open_key] += ", " + k
            if out[open_key].count("(") <= out[open_key].count(")"):
                open_key = None
            continue
        open_key = None
        out[k] = _rejoin_mapping_splits(v)
        if isinstance(v, str) and v.count("(") > v.count(")"):
            open_key = k
    return out


FAMILY_OPEN_KEYS = {"shapewright", "extends", "asset", "params", "budget", "profile", "style", "materials", "checks", "notes", "uv", "collision", "pack"}


def load_source(path: Path, _depth: int = 0, ctx: Ctx | None = None) -> dict:
    """Read a source file and apply `extends` inheritance.

    If the base declares an `interface`, the variant may only set the base's
    public params (plus metadata, budgets, materials) and its `checks` are
    ADDED to the base's checks. Structural overrides are refused with a hint.
    """
    path = Path(path).resolve()
    data = read_yaml(path)
    if "extends" in data:
        if _depth >= LIMITS.max_extends_depth:
            raise SourceError([Issue("SRC_LIMIT", "error", "extends chain too deep (cycle?)", str(path), "source")])
        base_path = (path.parent / str(data["extends"])).resolve()
        if base_path.is_dir():
            base_path = base_path / "asset.yaml"
        if not base_path.exists():
            raise SourceError([Issue("SRC_REF", "error", f"extends target not found: {data['extends']}", "extends", "source")])
        base = load_source(base_path, _depth + 1, ctx)
        iface = base.get("interface")
        child = {k: v for k, v in data.items() if k != "extends"}
        if isinstance(iface, dict):
            errors = []
            public = set(iface.get("params") or [])
            for k in child:
                if k not in FAMILY_OPEN_KEYS:
                    errors.append(Issue("FAMILY_PRIVATE", "error", f"variant overrides '{k}', which is private to the base asset", k, "source",
                                        "ask the base to expose it: add a public param or an `enabled:` switch to its interface"))
            for k in (child.get("params") or {}):
                if k not in public:
                    errors.append(Issue("FAMILY_PRIVATE", "error", f"param '{k}' is not in the base's interface", f"params.{k}", "source",
                                        (suggest(k, public).strip() or f"public params: {', '.join(sorted(public))}")))
            if errors:
                raise SourceError(errors)
            extra_checks = child.pop("checks", None)
            data = _deep_merge(base, child)
            if extra_checks:
                data["checks"] = list(base.get("checks") or []) + list(extra_checks)
        else:
            if ctx is not None:
                ctx.issues.append(Issue("FAMILY_NO_INTERFACE", "info", "base asset declares no `interface`; the variant depends on its internals",
                                        "extends", "source", "declare interface: {params: [...]} in the base"))
            data = _deep_merge(base, child)
        data["_extends"] = str(base_path)
        # a variant reads its base's files (mesh_file, textures) from the base's folder (FRESH_AGENT_07)
        data["_file_roots"] = [str(base_path.parent)] + [r for r in (base.get("_file_roots") or []) if r != str(base_path.parent)]
    if "pack" in data and "_pack" not in data:
        data = apply_pack(data, path)
    return data


def resolve_pack_path(ref: str, asset_path: Path) -> Path:
    from . import paths

    ref = str(ref)
    p = (asset_path.parent / ref).resolve() if ref.endswith(".yaml") else (paths.find("packs", ref) or paths.LIB / "packs" / f"{ref}.yaml")
    if not p.exists():
        options = paths.names("packs")
        raise SourceError([Issue("SRC_REF", "error", f"pack not found: {ref}", "pack", "source",
                                 suggest(ref, options).strip() or f"packs: {', '.join(options) or 'none'} (packs/NAME.yaml)")])
    return p


def apply_pack(data: dict, asset_path: Path) -> dict:
    """Merge a pack's shared vocabulary into an asset source.

    A pack is not a base asset: it has no parts and nothing is inherited
    structurally. Its params and materials are read-only in members, so the set
    cannot drift; profile/style are the pack's; budget keys are defaults.
    """
    pack_path = resolve_pack_path(data["pack"], asset_path)
    pack = read_yaml(pack_path)
    errors = []
    for k in pack:
        if k not in PACK_KEYS:
            errors.append(Issue("SRC_SCHEMA", "error", f"unknown key '{k}' in pack", f"pack:{pack_path.name}.{k}", "source",
                                suggest(k, PACK_KEYS).strip() or f"allowed: {', '.join(PACK_KEYS)}"))
    for section in ("params", "materials"):
        for k in (data.get(section) or {}):
            if k in (pack.get(section) or {}):
                errors.append(Issue("PACK_OVERRIDE", "error", f"{section[:-1]} '{k}' is defined by pack '{pack.get('pack', pack_path.stem)}' and is read-only",
                                    f"{section}.{k}", "source",
                                    "use a new name for an asset-specific value, or change it in the pack for every member"))
    for k in ("profile", "style"):
        if k in data and k in pack and data[k] != pack[k]:
            errors.append(Issue("PACK_OVERRIDE", "error", f"{k} '{data[k]}' differs from the pack's '{pack[k]}'", k, "source",
                                "members share the pack's profile and style"))
    if errors:
        raise SourceError(errors)
    out = dict(data)
    out["params"] = {**(pack.get("params") or {}), **(data.get("params") or {})}
    out["materials"] = {**(pack.get("materials") or {}), **(data.get("materials") or {})}
    for k in ("profile", "style"):
        if k in pack:
            out[k] = pack[k]
    out["budget"] = {**(pack.get("budget") or {}), **(data.get("budget") or {})}
    out["_pack"] = str(pack.get("pack") or pack_path.stem)
    return out


def source_hash(data: dict) -> str:
    text = yaml.safe_dump({k: v for k, v in data.items() if not k.startswith("_")}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- params


def param_spec(raw: Any) -> dict:
    """Normalize a param entry to {value, min, max, doc, vary}."""
    if isinstance(raw, dict):
        return {"value": raw.get("value"), "min": raw.get("min"), "max": raw.get("max"), "doc": raw.get("doc", ""), "vary": raw.get("vary")}
    return {"value": raw, "min": None, "max": None, "doc": "", "vary": None}


def resolve_params(params: dict, ctx: Ctx, prefix: str = "params") -> dict[str, float]:
    specs = {k: param_spec(v) for k, v in (params or {}).items()}
    env: dict[str, float] = {}
    pending = dict(specs)
    for name in specs:
        if not name.isidentifier() or name.startswith("_"):
            ctx.error("SRC_SCHEMA", f"{prefix}.{name}", "parameter names must be identifiers")
    while pending:
        progressed = False
        for name, spec in list(pending.items()):
            value = spec["value"]
            if isinstance(value, str):
                try:
                    deps = expr.names_in(value)
                except expr.ExprError as e:
                    ctx.error("SRC_EXPR", f"{prefix}.{name}", str(e))
                    pending.pop(name)
                    continue
                unknown = deps - set(specs)
                if unknown:
                    u = sorted(unknown)[0]
                    ctx.error("SRC_EXPR", f"{prefix}.{name}", f"unknown name '{u}'", suggest(u, specs).strip())
                    pending.pop(name)
                    continue
                if deps - set(env):
                    continue
                try:
                    value = expr.evaluate(value, env)
                except expr.ExprError as e:
                    ctx.error("SRC_EXPR", f"{prefix}.{name}", str(e))
                    pending.pop(name)
                    continue
            if isinstance(value, bool):
                value = float(value)  # switches: true/false are 1/0
            if not isinstance(value, (int, float)):
                ctx.error("SRC_SCHEMA", f"{prefix}.{name}", f"value must be a number or expression, got {value!r}")
                pending.pop(name)
                continue
            env[name] = float(value)
            lo, hi = spec["min"], spec["max"]
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                ctx.issues.append(
                    Issue("PARAM_OUT_OF_RANGE", "warning", f"{value:g} outside declared range [{lo}, {hi}]", f"{prefix}.{name}", "source",
                          "keep the value in range or widen the range deliberately")
                )
            pending.pop(name)
            progressed = True
        if not progressed and pending:
            names = ", ".join(sorted(pending))
            ctx.error("SRC_CYCLE", prefix, f"circular parameter references: {names}")
            break
    return env


# --------------------------------------------------------------------------- values


def num(value: Any, env: dict, where: str, ctx: Ctx, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        ctx.error("SRC_SCHEMA", where, "expected a number, got a boolean")
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            out = expr.evaluate(value, env)
        except expr.ExprError as e:
            name = str(e).split("'")[1] if "unknown name" in str(e) else ""
            hint = suggest(name, env).strip() if name else ""
            if name and f"{name}." in value:
                hint = (f"part metrics such as {name}.size.x exist only in checks; inside parts measure the part first: "
                        f"measure: {{m: {{bounds: {name}}}}} then m.size.x, m.max.y ... (docs/RELATIONSHIPS.md)")
            elif name in ("i", "n"):
                hint = "i and n exist only inside array `each:` expressions (sw doc array)"
            ctx.error("SRC_EXPR", where, str(e), hint)
            return default
        if isinstance(out, bool) or not isinstance(out, (int, float)):
            ctx.error("SRC_EXPR", where, f"'{value}' did not produce a number")
            return default
        return float(out)
    ctx.error("SRC_SCHEMA", where, f"expected a number or expression, got {type(value).__name__}")
    return default


def rejoin_split_exprs(value: list) -> list:
    """Undo YAML's split of a flow list at commas inside an expression: [atan2(a, b), 0] parses as
    ["atan2(a", "b)", 0]. A string with unbalanced parentheses is never a valid expression, so the
    pieces are joined back until they balance (FRESH_AGENT_05-09: 15 failed builds from this trap)."""
    out, buf = [], None
    for v in value:
        if buf is not None:
            buf += ", " + str(v)
            if buf.count("(") <= buf.count(")"):
                out.append(buf)
                buf = None
        elif isinstance(v, str) and v.count("(") > v.count(")"):
            buf = v
        else:
            out.append(v)
    return out if buf is None else out + [buf]


def vec(value: Any, n: int, env: dict, where: str, ctx: Ctx) -> list[float] | None:
    if isinstance(value, (int, float, str)) and n == 3:
        v = num(value, env, where, ctx)
        return None if v is None else [v, v, v]
    if isinstance(value, (list, tuple)) and len(value) > n:
        value = rejoin_split_exprs(list(value))
    if not isinstance(value, (list, tuple)) or len(value) != n:
        hint = ""
        if isinstance(value, (list, tuple)) and any(isinstance(v, str) and v.count("(") != v.count(")") for v in value):
            hint = "an expression with a comma, e.g. atan2(a, b), was split by YAML: quote it: [\"atan2(a, b)\", 0, 0]"
        ctx.error("SRC_SCHEMA", where, f"expected a list of {n} numbers", hint)
        return None
    out = [num(v, env, f"{where}[{i}]", ctx) for i, v in enumerate(value)]
    return None if any(v is None for v in out) else out


def resolve_args(spec: OpSpec, raw: dict, env: dict, where: str, ctx: Ctx, extra_keys=frozenset()) -> dict | None:
    """Validate and evaluate the fields of a shape/op definition against its spec."""
    args: dict[str, Any] = {}
    known = {p.name for p in spec.params}
    for key in raw:
        if key in ("type", "doc") or key in extra_keys:
            continue
        if key not in known:
            ctx.error("SRC_SCHEMA", f"{where}.{key}", f"'{spec.name}' has no parameter '{key}'",
                      (suggest(key, known).strip() or f"parameters: {', '.join(sorted(known))}"))
    before = len(ctx.issues)
    for p in spec.params:
        path = f"{where}.{p.name}"
        if p.name not in raw:
            if p.required:
                ctx.error("SRC_SCHEMA", path, f"'{spec.name}' requires '{p.name}' ({p.doc})")
            else:
                args[p.name] = parse_color_value(p.default) if p.kind == "color" else copy.deepcopy(p.default)
            continue
        value = raw[p.name]
        if p.kind in ("num", "int"):
            v = num(value, env, path, ctx)
            if v is not None and p.kind == "int":
                v = int(round(v))
            if v is not None and ((p.min is not None and v < p.min) or (p.max is not None and v > p.max)):
                ctx.error("SRC_RANGE", path, f"{v:g} outside allowed range [{p.min}, {p.max}]")
            args[p.name] = v
        elif p.kind == "vec2":
            args[p.name] = vec(value, 2, env, path, ctx)
        elif p.kind == "vec3":
            args[p.name] = vec(value, 3, env, path, ctx)
        elif p.kind == "num|vec3":
            args[p.name] = vec(value, 3, env, path, ctx) if isinstance(value, (list, tuple)) else num(value, env, path, ctx)
        elif p.kind in ("points2", "points3"):
            from .curves import expand_points

            n = 2 if p.kind == "points2" else 3
            pts = expand_points(value, n, env, path, ctx)
            if pts is not None and len(pts) < 2:
                ctx.error("SRC_SCHEMA", path, f"expected at least 2 points {KIND_HINT[p.kind]} (items may be arc/helix/line generators)")
            args[p.name] = pts
        elif p.kind == "axis":
            if value not in ("x", "y", "z"):
                ctx.error("SRC_SCHEMA", path, "axis must be x, y or z")
            args[p.name] = value
        elif p.kind == "str":
            if p.choices and value not in p.choices:
                ctx.error("SRC_SCHEMA", path, f"must be one of {', '.join(p.choices)}", suggest(value, p.choices).strip())
            args[p.name] = value
        elif p.kind == "color":
            c = parse_color_value(value)
            if c is None:
                ctx.error("SRC_SCHEMA", path, "colour must be '#rrggbb' or [r, g, b] in 0..1 (sRGB)")
            args[p.name] = c
        elif p.kind == "bool":
            if not isinstance(value, bool):
                ctx.error("SRC_SCHEMA", path, "expected true or false")
            args[p.name] = bool(value)
        elif p.kind == "geometry":
            if not isinstance(value, dict) or "type" not in value:
                ctx.error("SRC_SCHEMA", path, "expected a geometry expression {type: ..., ...}")
            args[p.name] = value  # built lazily by the op via BuildCtx.build_geometry
        elif p.kind == "geometry_list":
            if not isinstance(value, list) or not value or not all(isinstance(v, dict) and "type" in v for v in value):
                ctx.error("SRC_SCHEMA", path, "expected a non-empty list of geometry expressions")
            args[p.name] = value
        else:
            args[p.name] = value
    return None if len(ctx.issues) > before and any(i.severity == "error" for i in ctx.issues[before:]) else args


KIND_HINT = {"points2": "[[x, y], ...]", "points3": "[[x, y, z], ...]"}


def parse_color_value(value) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("#") and len(value) in (7, 9):
        try:
            return [int(value[i:i + 2], 16) / 255 for i in range(1, len(value), 2)][:4]
        except ValueError:
            return None
    if isinstance(value, list) and len(value) in (3, 4) and all(isinstance(v, (int, float)) for v in value):
        return [float(v) for v in value]
    return None


def check_keys(raw: dict, allowed: dict | set, where: str, ctx: Ctx):
    for key in raw:
        if str(key).startswith("_"):
            continue
        if key not in allowed:
            hint = suggest(key, allowed).strip() or f"allowed: {', '.join(sorted(allowed))}"
            if isinstance(raw.get("doc"), str):  # `{doc: legs, rails: dark}` silently becomes two keys in YAML flow style
                hint += "; if this key came from text after a comma or colon inside {...}, quote that text: doc: \"legs, rails: dark\""
            ctx.error("SRC_SCHEMA", f"{where}.{key}" if where else str(key), f"unknown key '{key}'", hint)


def lookup_spec(table: dict, kind: str, raw: Any, where: str, ctx: Ctx) -> OpSpec | None:
    if not isinstance(raw, dict) or "type" not in raw:
        ctx.error("SRC_SCHEMA", where, f"{kind} must be a mapping with a 'type'")
        return None
    spec = table.get(raw["type"])
    if spec is None:
        ctx.error("SRC_SCHEMA", f"{where}.type", f"unknown {kind} type '{raw['type']}'",
                  suggest(raw["type"], table).strip() or f"run `sw caps` to list {kind}s")
    return spec


def shape_spec(raw, where, ctx):
    return lookup_spec(SHAPES, "shape", raw, where, ctx)


def op_spec(raw, where, ctx):
    return lookup_spec(OPS, "op", raw, where, ctx)


__all__ = [
    "Ctx", "load_source", "resolve_params", "resolve_args", "num", "vec", "check_keys", "shape_spec", "op_spec",
    "TOP_KEYS", "PART_KEYS", "MATERIAL_KEYS", "INSTANCE_KEYS", "COMPONENT_KEYS", "read_yaml", "REQUIRED", "source_hash", "FORMAT_VERSION", "param_spec",
]
