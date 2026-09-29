"""Build pipeline: asset source -> semantic parts with world-space meshes.

    source (YAML) --load/extends/interface--> dict --params--> env
        expand components, drop disabled parts (`enabled:`)
        order parts by dependency (attach targets, measure queries)
        for each part:
            measure (queries on already-built parts) -> part env
            geometry expression -> recentre -> part ops -> rotate
            -> place (position | attach) -> replicate (array, mirror) -> named instances
        sockets, materials, profile, style

A *geometry expression* is recursive and valid everywhere geometry is expected
(part shape, boolean tools, composite generators):

    {type: <generator>, <params>..., ops: [...], material: m, rotate: [...], translate: [...]}

The result (:class:`Asset`) is the in-memory intermediate representation that
validators, the renderer and exporters consume. It keeps semantic names all
the way to the exported file; faces also carry provenance (`origin`), `region`
and optional `material` attributes (docs/MESH_MODEL.md).
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from . import source as S
from . import spatial
from .limits import LIMITS
from .mesh import Mesh, region_by_normal, rotation_matrix
from .registry import SHAPES, load_builtin, suggest
from .report import Issue, SourceError

ROOT = Path(__file__).resolve().parent.parent
AXIS_TOKENS = {"left": (0, -1), "right": (0, 1), "bottom": (1, -1), "top": (1, 1), "back": (2, -1), "front": (2, 1)}
SIDE_NAMES = {0: ("left", "right"), 1: ("bottom", "top"), 2: ("back", "front")}
EXPR_KEYS = {"type", "doc", "ops", "material", "rotate", "translate"}


@dataclass
class Part:
    name: str
    base: str
    mesh: Mesh
    material: str | None = None
    shading: str = "auto"
    smooth_angle: float = 40.0
    parent: str | None = None
    pivot: np.ndarray | None = None
    tags: list = field(default_factory=list)
    doc: str = ""
    instance: dict = field(default_factory=dict)
    component: str | None = None  # component instance this part came from
    source: str = "native"  # native | file (baked/imported geometry)
    uv: dict = field(default_factory=dict)  # per-part UV settings (lock, share)

    @property
    def bounds(self):
        return self.mesh.bounds()


@dataclass
class Socket:
    name: str
    position: np.ndarray
    rotation: list
    doc: str = ""
    part: str | None = None


@dataclass
class Asset:
    name: str
    path: Path
    source: dict
    env: dict
    meta: dict
    parts: list[Part]
    sockets: list[Socket]
    materials: dict
    profile: dict
    style: dict
    budget: dict
    uv: dict
    collision: dict
    checks: list
    issues: list[Issue]
    source_hash: str
    build_ms: float = 0.0
    disabled: list = field(default_factory=list)

    def part(self, name: str) -> Part | None:
        return next((p for p in self.parts if p.name == name), None)

    def parts_named(self, name: str) -> list[Part]:
        """Instances of a source part (or a single instance by its own name)."""
        exact = [p for p in self.parts if p.name == name]
        return exact or [p for p in self.parts if p.base == name]

    @property
    def n_tris(self) -> int:
        return sum(p.mesh.n_tris for p in self.parts)

    def bounds(self) -> np.ndarray:
        b = np.stack([p.bounds for p in self.parts]) if self.parts else np.zeros((1, 2, 3))
        return np.stack([b[:, 0].min(0), b[:, 1].max(0)])

    @property
    def dir(self) -> Path:
        return self.path.parent

    @property
    def build_dir(self) -> Path:
        d = self.dir / ".build"
        d.mkdir(exist_ok=True)
        return d


# --------------------------------------------------------------------------- anchors


def anchor_coeffs(spec: Any, where: str, ctx: S.Ctx) -> np.ndarray | None:
    """'bottom_front_left' -> [-1, -1, 1]; also accepts [cx, cy, cz] in -1..1."""
    if spec is None or spec == "center":
        return np.zeros(3)
    if isinstance(spec, (list, tuple)) and len(spec) == 3:
        return np.asarray([float(v) for v in spec])
    if not isinstance(spec, str):
        ctx.error("SRC_SCHEMA", where, "anchor must be a name like 'top_front_left' or [x, y, z] in -1..1")
        return None
    c = np.zeros(3)
    for tok in spec.split("_"):
        if tok == "center":
            continue
        if tok not in AXIS_TOKENS:
            ctx.error("SRC_SCHEMA", where, f"unknown anchor token '{tok}'",
                      suggest(tok, list(AXIS_TOKENS) + ["center"]).strip() or "tokens: top bottom left right front back center")
            return None
        axis, sign = AXIS_TOKENS[tok]
        c[axis] = sign
    return c


def anchor_point(bounds: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
    center = (bounds[0] + bounds[1]) / 2
    return center + coeffs * (bounds[1] - bounds[0]) / 2


# --------------------------------------------------------------------------- geometry expressions


class BuildCtx:
    """Handed to generators and ops so they can resolve nested definitions."""

    def __init__(self, env: dict, ctx: S.Ctx, where: str, asset_dir: Path | None = None, materials: dict | None = None):
        self.env, self.ctx, self.where = env, ctx, where
        self.asset_dir = asset_dir
        self.materials = materials or {}

    def vec(self, value, n, where):
        out = S.vec(value, n, self.env, f"{self.where}.{where}", self.ctx)
        if out is None:
            raise ValueError(f"invalid vector at {where}")
        return out

    def build_geometry(self, raw, where) -> Mesh:
        mesh = build_geometry(raw, self.env, self.ctx, f"{self.where}.{where}", self.asset_dir, self.materials)
        if mesh is None:
            raise ValueError(f"invalid geometry at {where} (see earlier errors)")
        return mesh.recentered()

    build_shape = build_geometry  # backwards-compatible name for extensions written against v0.1


def _check_mesh(mesh: Mesh, name: str, where: str, ctx: S.Ctx) -> bool:
    if mesh.n_tris == 0:
        ctx.error("GEO_EMPTY", where, f"{name} produced no triangles")
        return False
    if mesh.n_tris > LIMITS.max_triangles_per_part:
        ctx.error("SRC_LIMIT", where, f"{mesh.n_tris} triangles exceeds per-part limit {LIMITS.max_triangles_per_part}")
        return False
    if not np.all(np.isfinite(mesh.V)):
        ctx.error("GEO_NONFINITE", where, f"{name} produced NaN/inf vertices")
        return False
    return True


def build_geometry(raw: Any, env: dict, ctx: S.Ctx, where: str, asset_dir: Path | None = None, materials: dict | None = None) -> Mesh | None:
    """Evaluate a geometry expression: generator -> recentre -> ops -> rotate -> translate."""
    spec = S.shape_spec(raw, where, ctx)
    if spec is None:
        return None
    args = S.resolve_args(spec, raw, env, where, ctx, extra_keys=EXPR_KEYS)
    if args is None:
        return None
    b = BuildCtx(env, ctx, where, asset_dir, materials)
    try:
        mesh = spec.fn(args, b)
    except Exception as e:  # geometry libraries raise many types
        ctx.error("OP_FAILED", where, f"{spec.name} failed: {e}", "check the parameters of this geometry")
        return None
    if not _check_mesh(mesh, spec.name, where, ctx):
        return None
    if "origin" not in mesh.fattr or (mesh.fattr["origin"] < 0).any():
        unset = mesh.fattr["origin"] < 0 if "origin" in mesh.fattr else None
        mesh.set_label("origin", where, unset)
    if "region" not in mesh.fattr:
        mesh = region_by_normal(mesh)
    if raw.get("material") is not None:
        mat = raw["material"]
        if materials is not None and mat not in materials:
            ctx.error("SRC_REF", f"{where}.material", f"unknown material '{mat}'", suggest(mat, materials).strip())
        else:
            unset = mesh.fattr["material"] < 0 if "material" in mesh.fattr else None
            mesh.set_label("material", mat, unset)  # inner expressions keep their own material
    mesh = apply_ops(mesh.recentered(), raw.get("ops"), env, ctx, f"{where}.ops", asset_dir, materials)
    if mesh is None:
        return None
    if raw.get("rotate") is not None:
        rot = S.vec(raw["rotate"], 3, env, f"{where}.rotate", ctx)
        if rot is None:
            return None
        mesh = mesh.transformed(rotation_matrix(rot))
    if raw.get("translate") is not None:
        tr = S.vec(raw["translate"], 3, env, f"{where}.translate", ctx)
        if tr is None:
            return None
        mesh = mesh.translated(tr)
    return mesh


build_shape = build_geometry  # v0.1 name


def apply_ops(mesh: Mesh, ops: Any, env: dict, ctx: S.Ctx, where: str, asset_dir: Path | None = None, materials: dict | None = None) -> Mesh | None:
    if ops is None:
        return mesh
    if not isinstance(ops, list):
        ctx.error("SRC_SCHEMA", where, "ops must be a list")
        return None
    if len(ops) > LIMITS.max_ops_per_part:
        ctx.error("SRC_LIMIT", where, f"more than {LIMITS.max_ops_per_part} ops")
        return None
    for i, raw in enumerate(ops):
        path = f"{where}[{i}]"
        spec = S.op_spec(raw, path, ctx)
        if spec is None:
            return None
        args = S.resolve_args(spec, raw, env, path, ctx)
        if args is None:
            return None
        try:
            mesh = spec.fn(mesh, args, BuildCtx(env, ctx, path, asset_dir, materials))
        except Exception as e:
            ctx.error("OP_FAILED", path, f"{spec.name} failed: {e}")
            return None
        if not _check_mesh(mesh, spec.name, path, ctx):
            return None
    return mesh


# --------------------------------------------------------------------------- profiles, materials


def load_named(kind: str, name: str | None, asset_dir: Path, ctx: S.Ctx) -> dict:
    if not name:
        return {}
    for base in (asset_dir, ROOT):
        p = base / kind / f"{name}.yaml"
        if p.exists():
            data = yaml.safe_load(p.read_text()) or {}
            data.setdefault("name", name)
            return data
    options = sorted(p.stem for p in (ROOT / kind).glob("*.yaml"))
    ctx.error("SRC_REF", kind[:-1], f"unknown {kind[:-1]} '{name}'", suggest(name, options).strip() or f"available: {', '.join(options)}")
    return {}


def parse_color(value: Any, where: str, ctx: S.Ctx) -> list[float]:
    if isinstance(value, str) and value.startswith("#") and len(value) in (7, 9):
        try:
            return [int(value[i:i + 2], 16) / 255 for i in range(1, len(value), 2)][:4]
        except ValueError:
            pass
    if isinstance(value, list) and len(value) in (3, 4) and all(isinstance(v, (int, float)) for v in value):
        return [float(v) for v in value]
    ctx.error("SRC_SCHEMA", where, "colour must be '#rrggbb' or [r, g, b] in 0..1 (sRGB)")
    return [0.8, 0.8, 0.8]


def resolve_materials(raw: dict, env: dict, ctx: S.Ctx) -> dict:
    out = {}
    for name, m in (raw or {}).items():
        where = f"materials.{name}"
        if not isinstance(m, dict):
            ctx.error("SRC_SCHEMA", where, "material must be a mapping")
            continue
        S.check_keys(m, S.MATERIAL_KEYS, where, ctx)
        out[name] = {
            "base_color": parse_color(m.get("base_color", "#cccccc"), f"{where}.base_color", ctx),
            "metallic": S.num(m.get("metallic", 0.0), env, f"{where}.metallic", ctx, 0.0),
            "roughness": S.num(m.get("roughness", 0.8), env, f"{where}.roughness", ctx, 0.8),
            "emissive": parse_color(m["emissive"], f"{where}.emissive", ctx) if "emissive" in m else None,
            "alpha_mode": m.get("alpha_mode", "OPAQUE"),
            "double_sided": bool(m.get("double_sided", False)),
            "doc": m.get("doc", ""),
        }
    return out


# --------------------------------------------------------------------------- units of work


@dataclass
class Unit:
    """A part, or a component instance (a group of parts placed together)."""

    name: str
    raw: dict
    env: dict
    where: str
    members: list = field(default_factory=list)  # component: list[Unit]
    component: str | None = None

    @property
    def is_group(self) -> bool:
        return bool(self.members)


def _refs(raw: dict) -> list[tuple[str, str]]:
    """(field path, referenced part/instance name) for attach and measure."""
    out = []
    at = raw.get("attach")
    if isinstance(at, dict) and at.get("to") not in (None, "origin"):
        out.append(("attach.to", str(at["to"])))
    for q, spec in (raw.get("measure") or {}).items():
        if not isinstance(spec, dict):
            continue
        if isinstance(spec.get("gap"), list):  # in a gap query, `section` is a plane, not a part
            out.extend((f"measure.{q}.gap", str(n)) for n in spec["gap"])
            continue
        for kind in ("section", "bounds", "anchor", "ray"):
            if kind in spec:
                out.append((f"measure.{q}.{kind}", str(spec[kind])))
    return out


def _rename(raw: dict, mapping: dict, materials: dict) -> dict:
    """Prefix component-internal references and remap material names."""
    raw = copy.deepcopy(raw)
    at = raw.get("attach")
    if isinstance(at, dict) and at.get("to") in mapping:
        at["to"] = mapping[at["to"]]
    if raw.get("parent") in mapping:
        raw["parent"] = mapping[raw["parent"]]
    for spec in (raw.get("measure") or {}).values():
        if not isinstance(spec, dict):
            continue
        if isinstance(spec.get("gap"), list):
            spec["gap"] = [mapping.get(n, n) for n in spec["gap"]]
            continue
        for kind in ("section", "bounds", "anchor", "ray"):
            if isinstance(spec.get(kind), str) and spec[kind] in mapping:
                spec[kind] = mapping[spec[kind]]

    def remap_materials(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "material" and isinstance(v, str) and v in materials:
                    node[k] = materials[v]
                else:
                    remap_materials(v)
        elif isinstance(node, list):
            for v in node:
                remap_materials(v)

    if materials:
        remap_materials(raw)
    return raw


def load_component(name: str, asset_dir: Path, ctx: S.Ctx, where: str) -> dict | None:
    for base in (asset_dir, ROOT):
        p = base / "components" / f"{name}.yaml"
        if p.exists():
            data = S.read_yaml(p)
            S.check_keys(data, S.COMPONENT_KEYS, f"components/{name}", ctx)
            return data
    options = sorted(p.stem for p in (ROOT / "components").glob("*.yaml"))
    ctx.error("SRC_REF", f"{where}.component", f"unknown component '{name}'", suggest(name, options).strip() or f"available: {', '.join(options)}")
    return None


def _enabled(raw: dict, env: dict, where: str, ctx: S.Ctx) -> bool:
    v = raw.get("enabled", True)
    if isinstance(v, (bool, int, float)):
        return bool(v)
    from . import expr

    try:
        return bool(expr.evaluate(str(v), env))
    except expr.ExprError as e:
        ctx.error("SRC_EXPR", f"{where}.enabled", str(e))
        return True


def expand_units(raw_parts: dict, env: dict, asset_dir: Path, ctx: S.Ctx) -> tuple[list[Unit], list[str]]:
    units, disabled = [], []
    for name, raw in raw_parts.items():
        where = f"parts.{name}"
        if not isinstance(raw, dict):
            ctx.error("SRC_SCHEMA", where, "part must be a mapping")
            continue
        if not str(name).isidentifier():
            ctx.error("SRC_SCHEMA", where, "part names must be identifiers (letters, digits, _)")
            continue
        if not _enabled(raw, env, where, ctx):
            disabled.append(name)
            continue
        if "component" not in raw:
            units.append(Unit(name, raw, env, where))
            continue
        S.check_keys(raw, S.INSTANCE_KEYS, where, ctx)
        comp = load_component(str(raw["component"]), asset_dir, ctx, where)
        if comp is None:
            continue
        cenv = resolve_component_env(comp, raw.get("with") or {}, env, ctx, where)
        mapping = {p: f"{name}_{p}" for p in (comp.get("parts") or {})}
        members = []
        for p, praw in (comp.get("parts") or {}).items():
            pwhere = f"{where}<{raw['component']}>.parts.{p}"
            if not isinstance(praw, dict):
                ctx.error("SRC_SCHEMA", pwhere, "part must be a mapping")
                continue
            if not _enabled(praw, cenv, pwhere, ctx):
                disabled.append(mapping[p])
                continue
            for path, ref in _refs(praw):
                if _owner_of(ref, mapping) is None:
                    ctx.error("SRC_REF", f"{pwhere}.{path}", f"component parts may only reference parts of the same component; '{ref}' is outside",
                              f"parts: {', '.join(mapping)}")
            members.append(Unit(mapping[p], _rename(praw, mapping, raw.get("materials") or {}), cenv, pwhere, component=name))
        if members:
            units.append(Unit(name, raw, env, where, members, component=str(raw["component"])))
    return units, disabled


def resolve_component_env(comp: dict, given: dict, outer_env: dict, ctx: S.Ctx, where: str) -> dict:
    public = comp.get("params") or {}
    for k in given:
        if k not in public:
            hint = suggest(k, public).strip() or f"public params: {', '.join(public) or 'none'}"
            ctx.error("COMPONENT_PRIVATE", f"{where}.with.{k}", f"'{k}' is not a public parameter of component '{comp.get('component', '?')}'", hint)
    merged = {}
    for k, spec in public.items():
        s = S.param_spec(spec)
        if k in given:
            v = S.num(given[k], outer_env, f"{where}.with.{k}", ctx)
            s = {**s, "value": v}
        merged[k] = s
    cenv = S.resolve_params(merged, ctx, prefix=f"{where}<{comp.get('component', '?')}>.params")
    private = S.resolve_params({**{k: {"value": v} for k, v in cenv.items()}, **(comp.get("private") or {})}, ctx,
                               prefix=f"{where}<{comp.get('component', '?')}>.private")
    return private


# --------------------------------------------------------------------------- ordering


def _owner_of(target: str, names) -> str | None:
    """Map an instance name like 'leg_front_left' or 'slat_2' to its unit/part name."""
    if target in names:
        return target
    candidates = [n for n in names if target.startswith(n + "_")]
    return max(candidates, key=len) if candidates else None


def _order(units: list[Unit], disabled: list[str], ctx: S.Ctx) -> list[Unit]:
    # every addressable name -> the top-level unit that produces it
    owner_unit = {}
    for u in units:
        owner_unit[u.name] = u.name
        for m in u.members:
            owner_unit[m.name] = u.name
    deps = {}
    for u in units:
        d = set()
        for (path, ref), src in [(r, u) for r in _refs(u.raw)] + [(r, m) for m in u.members for r in _refs(m.raw)]:
            owner = _owner_of(ref, owner_unit)
            if owner is None:
                if _owner_of(ref, disabled):
                    ctx.error("SRC_REF", f"{src.where}.{path}", f"'{ref}' is disabled (enabled: false) but still referenced",
                              "give this part the same `enabled:` condition, or reference an enabled part")
                else:
                    ctx.error("SRC_REF", f"{src.where}.{path}", f"unknown part '{ref}'", suggest(ref, owner_unit).strip())
                continue
            top = owner_unit[owner]
            if top == u.name and src is u:
                ctx.error("SRC_CYCLE", f"{src.where}.{path}", "a part cannot depend on itself")
            elif top != u.name:
                d.add(top)
        deps[u.name] = d
    order, done = [], set()
    by_name = {u.name: u for u in units}
    while len(order) < len(units):
        ready = [n for n in deps if n not in done and deps[n] <= done]
        if not ready:
            ctx.error("SRC_CYCLE", "parts", "dependency cycle between: " + ", ".join(sorted(set(deps) - done)))
            break
        for n in ready:
            order.append(by_name[n])
            done.add(n)
    return order


def _member_order(members: list[Unit], ctx: S.Ctx) -> list[Unit]:
    names = {m.name for m in members}
    deps = {m.name: {_owner_of(r, names) for _, r in _refs(m.raw)} - {None, m.name} for m in members}
    order, done = [], set()
    by = {m.name: m for m in members}
    while len(order) < len(members):
        ready = [n for n in deps if n not in done and deps[n] <= done]
        if not ready:
            ctx.error("SRC_CYCLE", members[0].where, "dependency cycle inside component")
            break
        for n in ready:
            order.append(by[n])
            done.add(n)
    return order


# --------------------------------------------------------------------------- measure


class World:
    """Built parts so far, addressable by instance name or source part name."""

    def __init__(self):
        self.parts: list[Part] = []
        self.base_bounds: dict[str, np.ndarray] = {}

    def mesh(self, name: str) -> Mesh | None:
        exact = [p for p in self.parts if p.name == name]
        if exact:
            return exact[0].mesh
        group = [p.mesh for p in self.parts if p.base == name or p.component == name]
        if group:
            from .mesh import concat

            return concat(group)
        return None

    def bounds(self, name: str) -> np.ndarray | None:
        """Instance name -> its bounds; source part or component name -> its placement
        before mirror/array (v0.1 semantics) or the group's bounds."""
        exact = [p for p in self.parts if p.name == name]
        if exact:
            return exact[0].bounds
        return self.base_bounds.get(name)


def measure(raw: dict, env: dict, world: World, ctx: S.Ctx, where: str) -> dict | None:
    out = {}
    for q, spec in (raw.get("measure") or {}).items():
        path = f"{where}.measure.{q}"
        if not str(q).isidentifier() or q in env:
            ctx.error("SRC_SCHEMA", path, f"measure name '{q}' must be an identifier and not shadow a param")
            return None
        kinds = ["gap"] if isinstance(spec, dict) and "gap" in spec else [k for k in spatial.QUERY_KINDS if isinstance(spec, dict) and k in spec]
        if len(kinds) != 1:
            ctx.error("SRC_SCHEMA", path, "a measure needs exactly one query kind", f"kinds: {', '.join(spatial.QUERY_KINDS)}")
            return None
        kind = kinds[0]
        allowed = {kind, "axis", "at", "section", "from", "dir", "doc"}
        S.check_keys(spec, allowed, path, ctx)
        local = {**env, **out}
        try:
            if kind == "gap":
                a, b = spec["gap"]
                ma, mb = world.mesh(str(a)), world.mesh(str(b))
                sec = None
                if spec.get("section"):
                    s = spec["section"]
                    sec = (s.get("axis", "y"), S.num(s.get("at"), local, f"{path}.section.at", ctx))
                out[q] = spatial.gap(ma, mb, spec.get("axis", "x"), (str(a), str(b)), sec)
            elif kind == "section":
                m = world.mesh(str(spec["section"]))
                out[q] = spatial.section(m, spec.get("axis", "y"), S.num(spec.get("at"), local, f"{path}.at", ctx), str(spec["section"]))
            elif kind == "bounds":
                out[q] = spatial.box_ns(world.bounds(str(spec["bounds"])), str(spec["bounds"]))
            elif kind == "anchor":
                c = anchor_coeffs(spec.get("at"), f"{path}.at", ctx)
                out[q] = spatial.vec_ns(anchor_point(world.bounds(str(spec["anchor"])), c), str(spec["anchor"]))
            elif kind == "ray":
                o = S.vec(spec.get("from"), 3, local, f"{path}.from", ctx)
                d = S.vec(spec.get("dir"), 3, local, f"{path}.dir", ctx)
                out[q] = spatial.ray(world.mesh(str(spec["ray"])), o, d, str(spec["ray"]))
        except spatial.QueryError as e:
            ctx.error("MEASURE_FAILED", path, str(e), "check the query plane/ray against `sw stats` sizes")
            return None
        except (TypeError, ValueError) as e:
            ctx.error("SRC_SCHEMA", path, f"invalid {kind} query: {e}")
            return None
    return out


# --------------------------------------------------------------------------- replication


def _replicate(name: str, mesh: Mesh, raw: dict, env: dict, ctx: S.Ctx, where: str) -> list[tuple[str, Mesh, dict]]:
    items = [(name, mesh, {})]
    arr = raw.get("array")
    if arr is not None:
        if not isinstance(arr, dict):
            ctx.error("SRC_SCHEMA", f"{where}.array", "array must be a mapping")
            return items
        S.check_keys(arr, {"count", "offset", "radial", "angle", "center"}, f"{where}.array", ctx)
        count = int(S.num(arr.get("count", 1), env, f"{where}.array.count", ctx, 1))
        if count < 1 or count > LIMITS.max_array_count:
            ctx.error("SRC_LIMIT", f"{where}.array.count", f"count must be 1..{LIMITS.max_array_count}")
            return items
        out = []
        for i in range(count):
            if "radial" in arr:
                axis = arr["radial"]
                angle = S.num(arr.get("angle", 360), env, f"{where}.array.angle", ctx, 360)
                step = angle / count if abs(angle - 360) < 1e-9 else angle / max(count - 1, 1)
                center = np.asarray(S.vec(arr.get("center", [0, 0, 0]), 3, env, f"{where}.array.center", ctx) or [0, 0, 0])
                rot = [0.0, 0.0, 0.0]
                rot["xyz".index(axis)] = step * i
                m = mesh.translated(-center).transformed(rotation_matrix(rot)).translated(center)
            else:
                off = S.vec(arr.get("offset", [0, 0, 0]), 3, env, f"{where}.array.offset", ctx) or [0, 0, 0]
                m = mesh.translated(np.asarray(off) * i)
            out.append((f"{name}_{i}" if count > 1 else name, m, {"array_index": i, "instance_of": name} if count > 1 else {}))
        items = out
    mirror = raw.get("mirror")
    if mirror is not None:
        planes = {}  # axis -> plane coordinate
        entries = mirror if isinstance(mirror, list) else [mirror]
        for ent in entries:
            if isinstance(ent, dict):
                S.check_keys(ent, {"axis", "at"}, f"{where}.mirror", ctx)
                ax, at = ent.get("axis"), S.num(ent.get("at", 0), env, f"{where}.mirror.at", ctx, 0.0)
            else:
                ax, at = ent, 0.0
            if ax not in ("x", "y", "z"):
                ctx.error("SRC_SCHEMA", f"{where}.mirror", "mirror must be x | y | z, {axis, at}, or a list of those")
                return items
            planes[ax] = at
        for ax in sorted(planes, key=lambda a: {"z": 0, "y": 1, "x": 2}[a]):  # name order: front_left
            i, at = "xyz".index(ax), planes[ax]
            new = []
            for nm, m, info in items:
                c = m.center()[i] - at
                if abs(c) < 1e-6:
                    ctx.error("ASM_MIRROR_ON_PLANE", f"{where}.mirror", f"'{nm}' is centred on the {ax}={at:g} mirror plane; its twin would overlap",
                              f"place the part off-centre along {ax} or remove mirror")
                    return items
                M = np.eye(4)
                M[i, i] = -1
                M[i, 3] = 2 * at
                twin = m.transformed(M)
                neg, pos = SIDE_NAMES[i]
                own, other = (pos, neg) if c > 0 else (neg, pos)
                new.append((f"{nm}_{own}", m, {**info, "mirror_" + ax: own}))
                new.append((f"{nm}_{other}", twin, {**info, "mirror_" + ax: other, "mirror_of": f"{nm}_{own}",
                                                      "reflected": 1 - info.get("reflected", 0)}))
            items = new
    return items


# --------------------------------------------------------------------------- parts


def _placement(raw: dict, mesh_bounds: np.ndarray, env: dict, world: World, ctx: S.Ctx, where: str) -> np.ndarray | None:
    """Translation that puts this unit's `anchor` where `position`/`attach` says."""
    self_anchor = anchor_coeffs(raw.get("anchor"), f"{where}.anchor", ctx)
    if self_anchor is None:
        return None
    own = anchor_point(mesh_bounds, self_anchor)
    if "attach" in raw and "position" in raw:
        ctx.error("SRC_SCHEMA", where, "use either 'position' or 'attach', not both")
        return None
    if "attach" in raw:
        at = raw["attach"]
        if not isinstance(at, dict) or "to" not in at:
            ctx.error("SRC_SCHEMA", f"{where}.attach", "attach needs {to: part, at: anchor}")
            return None
        S.check_keys(at, {"to", "at", "offset"}, f"{where}.attach", ctx)
        target = str(at["to"])
        if target == "origin":
            tpoint = np.zeros(3)
        else:
            tb = world.bounds(target)
            if tb is None:
                ctx.error("SRC_REF", f"{where}.attach.to", f"'{target}' was not built (see earlier errors)")
                return None
            coeff = anchor_coeffs(at.get("at"), f"{where}.attach.at", ctx)
            if coeff is None:
                return None
            tpoint = anchor_point(tb, coeff)
        off = S.vec(at.get("offset", [0, 0, 0]), 3, env, f"{where}.attach.offset", ctx) or [0, 0, 0]
        target_pos = tpoint + np.asarray(off)
    else:
        target_pos = np.asarray(S.vec(raw.get("position", [0, 0, 0]), 3, env, f"{where}.position", ctx) or [0, 0, 0])
    return target_pos - own


def build_part(u: Unit, world: World, materials: dict, style: dict, asset_dir: Path, ctx: S.Ctx) -> list[Part]:
    raw, where = u.raw, u.where
    S.check_keys(raw, S.PART_KEYS, where, ctx)
    if "shape" not in raw:
        ctx.error("SRC_SCHEMA", where, "part needs a 'shape' (a geometry expression) or a 'component'", f"shapes: {', '.join(sorted(SHAPES))}")
        return []
    mvals = measure(raw, u.env, world, ctx, where)
    if mvals is None:
        return []
    env = {**u.env, **mvals}
    mesh = build_geometry(raw["shape"], env, ctx, f"{where}.shape", asset_dir, materials)
    if mesh is None:
        return []
    mesh = apply_ops(mesh.recentered(), raw.get("ops"), env, ctx, f"{where}.ops", asset_dir, materials)
    if mesh is None:
        return []
    if "rotate" in raw:
        rot = S.vec(raw["rotate"], 3, env, f"{where}.rotate", ctx)
        if rot:
            mesh = mesh.transformed(rotation_matrix(rot))
    shift = _placement(raw, mesh.bounds(), env, world, ctx, where)
    if shift is None:
        return []
    mesh = mesh.translated(shift)
    world.base_bounds[u.name] = mesh.bounds()

    shading = raw.get("shading", (style.get("shading") or {}).get("default", "auto"))
    if shading not in ("flat", "smooth", "auto"):
        ctx.error("SRC_SCHEMA", f"{where}.shading", "shading must be flat, smooth or auto")
    smooth_angle = S.num(raw.get("smooth_angle", (style.get("shading") or {}).get("smooth_angle", 40)), env, f"{where}.smooth_angle", ctx, 40.0)
    material = raw.get("material")
    if material is not None and material not in materials:
        ctx.error("SRC_REF", f"{where}.material", f"unknown material '{material}'", suggest(material, materials).strip())
    uv = raw.get("uv") or {}
    if not isinstance(uv, dict):
        ctx.error("SRC_SCHEMA", f"{where}.uv", "part uv must be a mapping, e.g. {share_instances: true}")
        uv = {}
    source_kind = "file" if isinstance(raw["shape"], dict) and raw["shape"].get("type") == "mesh_file" else "native"
    out = []
    for iname, imesh, info in _replicate(u.name, mesh, raw, env, ctx, where):
        piv = None
        if raw.get("pivot") is not None:
            c = anchor_coeffs(raw["pivot"], f"{where}.pivot", ctx)
            piv = anchor_point(imesh.bounds(), c) if c is not None else None
        out.append(Part(iname, u.name, imesh, material, shading, smooth_angle, raw.get("parent"), piv,
                        list(raw.get("tags") or []), str(raw.get("doc", "")), info, u.component, source_kind, uv))
    return out


def build_group(u: Unit, world: World, materials: dict, style: dict, asset_dir: Path, ctx: S.Ctx) -> list[Part]:
    """Build a component instance in its own space, then place it as one group."""
    for k in ("array", "mirror"):
        if k in u.raw:
            ctx.error("SRC_SCHEMA", f"{u.where}.{k}", f"component instances do not support '{k}' yet",
                      "instantiate the component several times with different positions")
    local = World()
    local.parts = []
    built: list[Part] = []
    for m in _member_order(u.members, ctx):
        # members see only their own component's parts
        ps = build_part(m, local, materials, style, asset_dir, ctx)
        local.parts.extend(ps)
        built.extend(ps)
    if not built:
        return []
    group_bounds = np.stack([np.min([p.bounds[0] for p in built], 0), np.max([p.bounds[1] for p in built], 0)])
    center = (group_bounds[0] + group_bounds[1]) / 2
    if "rotate" in u.raw:
        rot = S.vec(u.raw["rotate"], 3, u.env, f"{u.where}.rotate", ctx)
        if rot:
            R = rotation_matrix(rot)
            for p in built:
                p.mesh = p.mesh.translated(-center).transformed(R).translated(center)
                if p.pivot is not None:
                    p.pivot = (R[:3, :3] @ (p.pivot - center)) + center
            group_bounds = np.stack([np.min([p.bounds[0] for p in built], 0), np.max([p.bounds[1] for p in built], 0)])
    shift = _placement(u.raw, group_bounds, u.env, world, ctx, u.where)
    if shift is None:
        return []
    for p in built:
        p.mesh = p.mesh.translated(shift)
        if p.pivot is not None:
            p.pivot = p.pivot + shift
        if p.parent is None and u.raw.get("parent"):
            p.parent = u.raw["parent"]
        p.tags = list(dict.fromkeys(p.tags + list(u.raw.get("tags") or [])))
    for name, b in local.base_bounds.items():
        world.base_bounds[name] = b + shift
    world.base_bounds[u.name] = group_bounds + shift
    return built


# --------------------------------------------------------------------------- main build


def build(path: str | Path) -> Asset:
    t0 = time.perf_counter()
    load_builtin()
    path = Path(path)
    if path.is_dir():
        path = path / "asset.yaml"
    if not path.exists():
        raise SourceError([Issue("SRC_REF", "error", f"no asset source at {path}", str(path), "source")])
    ctx = S.Ctx()
    data = S.load_source(path, ctx=ctx)
    S.check_keys(data, S.TOP_KEYS, "", ctx)
    env = S.resolve_params(data.get("params") or {}, ctx)
    meta = data.get("asset") or {}
    name = str(meta.get("name") or path.parent.name)
    materials = resolve_materials(data.get("materials") or {}, env, ctx)
    profile = load_named("profiles", data.get("profile"), path.parent, ctx)
    style = load_named("styles", data.get("style"), path.parent, ctx)
    budget = {**(profile.get("budget") or {}), **(data.get("budget") or {})}

    raw_parts = data.get("parts") or {}
    if not isinstance(raw_parts, dict) or not raw_parts:
        ctx.error("SRC_SCHEMA", "parts", "an asset needs at least one part (mapping name -> definition)")
        raise SourceError(ctx.issues)
    if len(raw_parts) > LIMITS.max_parts:
        ctx.error("SRC_LIMIT", "parts", f"more than {LIMITS.max_parts} parts")
    units, disabled = expand_units(raw_parts, env, path.parent, ctx)
    order = _order(units, disabled, ctx)
    ctx.raise_if_errors()

    world = World()
    for u in order:
        built = (build_group if u.is_group else build_part)(u, world, materials, style, path.parent, ctx)
        world.parts.extend(built)
    parts = world.parts
    if len(parts) > LIMITS.max_instances:
        ctx.error("SRC_LIMIT", "parts", f"{len(parts)} instances exceeds limit {LIMITS.max_instances}")
    total = sum(p.mesh.n_tris for p in parts)
    if total > LIMITS.max_triangles_total:
        ctx.error("SRC_LIMIT", "parts", f"{total} triangles exceeds hard limit {LIMITS.max_triangles_total}")

    names = {p.name for p in parts}
    bases = {p.base for p in parts} | {p.component for p in parts if p.component}
    for p in parts:  # resolve semantic parents onto instances (mirror/array aware)
        if p.parent is None:
            continue
        if p.parent not in bases and p.parent not in names:
            ctx.error("SRC_REF", f"parts.{p.base}.parent", f"unknown parent '{p.parent}'", suggest(p.parent, bases).strip())
            p.parent = None
            continue
        suffix = p.name[len(p.base):]
        candidates = [p.parent + suffix, p.parent]
        p.parent = next((c for c in candidates if c in names), next((q.name for q in parts if q.base == p.parent), None))

    sockets = []
    for sname, raw in (data.get("sockets") or {}).items():
        where = f"sockets.{sname}"
        if not isinstance(raw, dict):
            ctx.error("SRC_SCHEMA", where, "socket must be a mapping")
            continue
        S.check_keys(raw, {"attach", "position", "rotate", "doc"}, where, ctx)
        pos, owner = np.zeros(3), None
        if "attach" in raw:
            at = raw["attach"]
            tb = np.zeros((2, 3)) if str(at.get("to")) == "origin" else world.bounds(str(at.get("to")))
            if tb is None:
                ctx.error("SRC_REF", f"{where}.attach.to", f"unknown part '{at.get('to')}'", suggest(str(at.get("to")), names).strip())
                continue
            c = anchor_coeffs(at.get("at"), f"{where}.attach.at", ctx)
            off = S.vec(at.get("offset", [0, 0, 0]), 3, env, f"{where}.attach.offset", ctx) or [0, 0, 0]
            pos = anchor_point(tb, c if c is not None else np.zeros(3)) + np.asarray(off)
            owner = str(at.get("to"))
        elif "position" in raw:
            pos = np.asarray(S.vec(raw["position"], 3, env, f"{where}.position", ctx) or [0, 0, 0])
        rot = S.vec(raw.get("rotate", [0, 0, 0]), 3, env, f"{where}.rotate", ctx) or [0, 0, 0]
        sockets.append(Socket(sname, pos, rot, str(raw.get("doc", "")), owner))

    checks = data.get("checks") or []
    if not isinstance(checks, list):
        ctx.error("SRC_SCHEMA", "checks", "checks must be a list of {expr, min, max}")
        checks = []
    ctx.raise_if_errors()
    return Asset(name, path, data, env, meta, parts, sockets, materials, profile, style, budget,
                 data.get("uv") or {}, data.get("collision") or {}, checks, ctx.issues, S.source_hash(data),
                 (time.perf_counter() - t0) * 1000, disabled)


def resolve_asset_path(ref: str) -> Path:
    """Accept a directory, an asset.yaml path or a bare asset name under assets/."""
    p = Path(ref)
    if p.exists():
        return p / "asset.yaml" if p.is_dir() else p
    for base in (Path.cwd() / "assets", ROOT / "assets"):
        if (base / ref / "asset.yaml").exists():
            return base / ref / "asset.yaml"
    raise SourceError([Issue("SRC_REF", "error", f"cannot find asset '{ref}'", ref, "source",
                             "pass a directory containing asset.yaml, a .yaml path, or a name under assets/")])
