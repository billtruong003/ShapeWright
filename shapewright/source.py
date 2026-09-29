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
    "collision": "collision proxy settings",
    "notes": "free text for humans and agents",
}

PART_KEYS = {
    "shape": "generator definition {type: ..., ...}",
    "ops": "ordered list of modifiers applied in part-local space",
    "rotate": "[rx, ry, rz] degrees, applied about the part centre before placement",
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

MATERIAL_KEYS = {"base_color", "metallic", "roughness", "emissive", "alpha", "alpha_mode", "double_sided", "doc"}


class Ctx:
    """Collects issues while resolving a source."""

    def __init__(self):
        self.issues: list[Issue] = []

    def error(self, code, where, message, hint=""):
        self.issues.append(Issue(code, "error", message, where, "source", hint))

    def warn(self, code, where, message, hint=""):
        self.issues.append(Issue(code, "warning", message, where, "source", hint))

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
        raise SourceError([Issue("SRC_PARSE", "error", f"YAML parse error: {e}", str(path), "source")]) from None
    if not isinstance(data, dict):
        raise SourceError([Issue("SRC_PARSE", "error", "top level must be a mapping", str(path), "source")])
    return data


def load_source(path: Path, _depth: int = 0) -> dict:
    """Read a source file and apply `extends` inheritance."""
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
        base = load_source(base_path, _depth + 1)
        data = _deep_merge(base, {k: v for k, v in data.items() if k != "extends"})
        data["_extends"] = str(base_path)
    return data


def source_hash(data: dict) -> str:
    text = yaml.safe_dump({k: v for k, v in data.items() if not k.startswith("_")}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- params


def param_spec(raw: Any) -> dict:
    """Normalize a param entry to {value, min, max, doc, vary}."""
    if isinstance(raw, dict):
        return {"value": raw.get("value"), "min": raw.get("min"), "max": raw.get("max"), "doc": raw.get("doc", ""), "vary": raw.get("vary")}
    return {"value": raw, "min": None, "max": None, "doc": "", "vary": None}


def resolve_params(params: dict, ctx: Ctx) -> dict[str, float]:
    specs = {k: param_spec(v) for k, v in (params or {}).items()}
    env: dict[str, float] = {}
    pending = dict(specs)
    for name in specs:
        if not name.isidentifier() or name.startswith("_"):
            ctx.error("SRC_SCHEMA", f"params.{name}", "parameter names must be identifiers")
    while pending:
        progressed = False
        for name, spec in list(pending.items()):
            value = spec["value"]
            if isinstance(value, str):
                try:
                    deps = expr.names_in(value)
                except expr.ExprError as e:
                    ctx.error("SRC_EXPR", f"params.{name}", str(e))
                    pending.pop(name)
                    continue
                unknown = deps - set(specs)
                if unknown:
                    u = sorted(unknown)[0]
                    ctx.error("SRC_EXPR", f"params.{name}", f"unknown name '{u}'", suggest(u, specs).strip())
                    pending.pop(name)
                    continue
                if deps - set(env):
                    continue
                try:
                    value = expr.evaluate(value, env)
                except expr.ExprError as e:
                    ctx.error("SRC_EXPR", f"params.{name}", str(e))
                    pending.pop(name)
                    continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                ctx.error("SRC_SCHEMA", f"params.{name}", f"value must be a number or expression, got {value!r}")
                pending.pop(name)
                continue
            env[name] = float(value)
            lo, hi = spec["min"], spec["max"]
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                ctx.issues.append(
                    Issue("PARAM_OUT_OF_RANGE", "warning", f"{value:g} outside declared range [{lo}, {hi}]", f"params.{name}", "source",
                          "keep the value in range or widen the range deliberately")
                )
            pending.pop(name)
            progressed = True
        if not progressed and pending:
            names = ", ".join(sorted(pending))
            ctx.error("SRC_CYCLE", "params", f"circular parameter references: {names}")
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
            ctx.error("SRC_EXPR", where, str(e), suggest(name, env).strip() if name else "")
            return default
        if isinstance(out, bool) or not isinstance(out, (int, float)):
            ctx.error("SRC_EXPR", where, f"'{value}' did not produce a number")
            return default
        return float(out)
    ctx.error("SRC_SCHEMA", where, f"expected a number or expression, got {type(value).__name__}")
    return default


def vec(value: Any, n: int, env: dict, where: str, ctx: Ctx) -> list[float] | None:
    if isinstance(value, (int, float, str)) and n == 3:
        v = num(value, env, where, ctx)
        return None if v is None else [v, v, v]
    if not isinstance(value, (list, tuple)) or len(value) != n:
        ctx.error("SRC_SCHEMA", where, f"expected a list of {n} numbers")
        return None
    out = [num(v, env, f"{where}[{i}]", ctx) for i, v in enumerate(value)]
    return None if any(v is None for v in out) else out


def resolve_args(spec: OpSpec, raw: dict, env: dict, where: str, ctx: Ctx) -> dict | None:
    """Validate and evaluate the fields of a shape/op definition against its spec."""
    args: dict[str, Any] = {}
    known = {p.name for p in spec.params}
    for key in raw:
        if key in ("type", "doc"):
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
                args[p.name] = copy.deepcopy(p.default)
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
            n = 2 if p.kind == "points2" else 3
            if not isinstance(value, list) or len(value) < 2:
                ctx.error("SRC_SCHEMA", path, f"expected a list of at least 2 points {KIND_HINT[p.kind]}")
                continue
            args[p.name] = [vec(pt, n, env, f"{path}[{i}]", ctx) for i, pt in enumerate(value)]
        elif p.kind == "axis":
            if value not in ("x", "y", "z"):
                ctx.error("SRC_SCHEMA", path, "axis must be x, y or z")
            args[p.name] = value
        elif p.kind == "str":
            if p.choices and value not in p.choices:
                ctx.error("SRC_SCHEMA", path, f"must be one of {', '.join(p.choices)}", suggest(value, p.choices).strip())
            args[p.name] = value
        elif p.kind == "bool":
            if not isinstance(value, bool):
                ctx.error("SRC_SCHEMA", path, "expected true or false")
            args[p.name] = bool(value)
        elif p.kind == "shape":
            args[p.name] = value  # resolved lazily by the op itself via build_shape
        else:
            args[p.name] = value
    return None if len(ctx.issues) > before and any(i.severity == "error" for i in ctx.issues[before:]) else args


KIND_HINT = {"points2": "[[x, y], ...]", "points3": "[[x, y, z], ...]"}


def check_keys(raw: dict, allowed: dict | set, where: str, ctx: Ctx):
    for key in raw:
        if str(key).startswith("_"):
            continue
        if key not in allowed:
            ctx.error("SRC_SCHEMA", f"{where}.{key}" if where else str(key), f"unknown key '{key}'",
                      suggest(key, allowed).strip() or f"allowed: {', '.join(sorted(allowed))}")


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
    "TOP_KEYS", "PART_KEYS", "MATERIAL_KEYS", "REQUIRED", "source_hash", "FORMAT_VERSION", "param_spec",
]
