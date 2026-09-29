"""Build pipeline: asset source -> semantic parts with world-space meshes.

    source (YAML) --load/extends--> dict --params--> env
        for each part in dependency order:
            shape -> recentre -> ops -> rotate -> place (position | attach)
            -> replicate (array, mirror) -> named instances
        sockets, materials, profile, style

The result (:class:`Asset`) is the in-memory intermediate representation that
validators, the renderer and exporters consume. It keeps semantic names all
the way to the exported file.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from . import source as S
from .limits import LIMITS
from .mesh import Mesh, rotation_matrix
from .registry import SHAPES, load_builtin, suggest
from .report import Issue, SourceError

ROOT = Path(__file__).resolve().parent.parent
AXIS_TOKENS = {"left": (0, -1), "right": (0, 1), "bottom": (1, -1), "top": (1, 1), "back": (2, -1), "front": (2, 1)}
SIDE_NAMES = {0: ("left", "right"), 1: ("bottom", "top"), 2: ("back", "front")}


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


# --------------------------------------------------------------------------- build context


class BuildCtx:
    """Handed to shape/op functions so they can resolve nested definitions."""

    def __init__(self, env: dict, ctx: S.Ctx, where: str):
        self.env, self.ctx, self.where = env, ctx, where

    def vec(self, value, n, where):
        out = S.vec(value, n, self.env, f"{self.where}.{where}", self.ctx)
        if out is None:
            raise ValueError(f"invalid vector at {where}")
        return out

    def build_shape(self, raw, where) -> Mesh:
        mesh = build_shape(raw, self.env, self.ctx, f"{self.where}.{where}")
        if mesh is None:
            raise ValueError(f"invalid shape at {where}")
        return mesh.recentered()


def build_shape(raw: Any, env: dict, ctx: S.Ctx, where: str) -> Mesh | None:
    spec = S.shape_spec(raw, where, ctx)
    if spec is None:
        return None
    args = S.resolve_args(spec, raw, env, where, ctx)
    if args is None:
        return None
    try:
        mesh = spec.fn(args, BuildCtx(env, ctx, where))
    except Exception as e:  # geometry libraries raise many types
        ctx.error("OP_FAILED", where, f"{spec.name} failed: {e}", "check the parameters of this shape")
        return None
    if mesh.n_tris == 0:
        ctx.error("GEO_EMPTY", where, f"{spec.name} produced no triangles")
        return None
    if mesh.n_tris > LIMITS.max_triangles_per_part:
        ctx.error("SRC_LIMIT", where, f"{mesh.n_tris} triangles exceeds per-part limit {LIMITS.max_triangles_per_part}")
        return None
    return mesh


def apply_ops(mesh: Mesh, ops: Any, env: dict, ctx: S.Ctx, where: str) -> Mesh | None:
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
            mesh = spec.fn(mesh, args, BuildCtx(env, ctx, path))
        except Exception as e:
            ctx.error("OP_FAILED", path, f"{spec.name} failed: {e}")
            return None
        if mesh.n_tris == 0:
            ctx.error("GEO_EMPTY", path, f"{spec.name} removed all geometry")
            return None
        if mesh.n_tris > LIMITS.max_triangles_per_part:
            ctx.error("SRC_LIMIT", path, f"{mesh.n_tris} triangles exceeds per-part limit")
            return None
        if not np.all(np.isfinite(mesh.V)):
            ctx.error("GEO_NONFINITE", path, f"{spec.name} produced NaN/inf vertices")
            return None
    return mesh


# --------------------------------------------------------------------------- profiles


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


# --------------------------------------------------------------------------- main build


def _dependency_order(parts: dict, ctx: S.Ctx) -> list[str]:
    deps = {}
    for name, p in parts.items():
        d = set()
        if isinstance(p, dict) and isinstance(p.get("attach"), dict):
            target = str(p["attach"].get("to", ""))
            owner = _owner_of(target, parts)
            if owner is None and target not in ("origin", ""):
                ctx.error("SRC_REF", f"parts.{name}.attach.to", f"unknown part '{target}'", suggest(target, parts).strip())
            elif owner and owner != name:
                d.add(owner)
            elif owner == name:
                ctx.error("SRC_CYCLE", f"parts.{name}.attach.to", "a part cannot attach to itself")
        deps[name] = d
    order, done = [], set()
    while len(order) < len(deps):
        ready = [n for n in deps if n not in done and deps[n] <= done]
        if not ready:
            ctx.error("SRC_CYCLE", "parts", "attachment cycle between: " + ", ".join(sorted(set(deps) - done)))
            break
        for n in ready:  # keep source order among ready parts
            order.append(n)
            done.add(n)
    return order


def _owner_of(target: str, parts: dict) -> str | None:
    """Map an instance name like 'leg_front_left' or 'slat_2' to its source part."""
    if target in parts:
        return target
    candidates = [n for n in parts if target.startswith(n + "_")]
    return max(candidates, key=len) if candidates else None


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
            out.append((f"{name}_{i}" if count > 1 else name, m, {"array_index": i} if count > 1 else {}))
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
                new.append((f"{nm}_{other}", twin, {**info, "mirror_" + ax: other, "mirror_of": f"{nm}_{own}"}))
            items = new
    return items


def build(path: str | Path) -> Asset:
    t0 = time.perf_counter()
    load_builtin()
    path = Path(path)
    if path.is_dir():
        path = path / "asset.yaml"
    if not path.exists():
        raise SourceError([Issue("SRC_REF", "error", f"no asset source at {path}", str(path), "source")])
    data = S.load_source(path)
    ctx = S.Ctx()
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
    order = _dependency_order(raw_parts, ctx)
    ctx.raise_if_errors()

    parts: list[Part] = []
    base_bounds: dict[str, np.ndarray] = {}
    for pname in order:
        raw = raw_parts[pname]
        where = f"parts.{pname}"
        if not isinstance(raw, dict):
            ctx.error("SRC_SCHEMA", where, "part must be a mapping")
            continue
        if not str(pname).isidentifier():
            ctx.error("SRC_SCHEMA", where, "part names must be identifiers (letters, digits, _)")
        S.check_keys(raw, S.PART_KEYS, where, ctx)
        if "shape" not in raw:
            ctx.error("SRC_SCHEMA", where, "part needs a 'shape'", f"shapes: {', '.join(sorted(SHAPES))}")
            continue
        mesh = build_shape(raw["shape"], env, ctx, f"{where}.shape")
        if mesh is None:
            continue
        mesh = apply_ops(mesh.recentered(), raw.get("ops"), env, ctx, f"{where}.ops")
        if mesh is None:
            continue
        if "rotate" in raw:
            rot = S.vec(raw["rotate"], 3, env, f"{where}.rotate", ctx)
            if rot:
                mesh = mesh.transformed(rotation_matrix(rot))
        self_anchor = anchor_coeffs(raw.get("anchor"), f"{where}.anchor", ctx)
        if self_anchor is None:
            continue
        own = anchor_point(mesh.bounds(), self_anchor)
        if "attach" in raw and "position" in raw:
            ctx.error("SRC_SCHEMA", where, "use either 'position' or 'attach', not both")
            continue
        if "attach" in raw:
            at = raw["attach"]
            if not isinstance(at, dict) or "to" not in at:
                ctx.error("SRC_SCHEMA", f"{where}.attach", "attach needs {to: part, at: anchor}")
                continue
            S.check_keys(at, {"to", "at", "offset"}, f"{where}.attach", ctx)
            target = str(at["to"])
            if target == "origin":
                tpoint = np.zeros(3)
            else:
                tb = next((p.bounds for p in parts if p.name == target), None)
                tb = base_bounds.get(target) if tb is None else tb
                if tb is None:
                    ctx.error("SRC_REF", f"{where}.attach.to", f"'{target}' was not built (see earlier errors)")
                    continue
                coeff = anchor_coeffs(at.get("at"), f"{where}.attach.at", ctx)
                if coeff is None:
                    continue
                tpoint = anchor_point(tb, coeff)
            off = S.vec(at.get("offset", [0, 0, 0]), 3, env, f"{where}.attach.offset", ctx) or [0, 0, 0]
            target_pos = tpoint + np.asarray(off)
        else:
            target_pos = np.asarray(S.vec(raw.get("position", [0, 0, 0]), 3, env, f"{where}.position", ctx) or [0, 0, 0])
        mesh = mesh.translated(target_pos - own)
        base_bounds[pname] = mesh.bounds()

        shading = raw.get("shading", (style.get("shading") or {}).get("default", "auto"))
        if shading not in ("flat", "smooth", "auto"):
            ctx.error("SRC_SCHEMA", f"{where}.shading", "shading must be flat, smooth or auto")
        smooth_angle = S.num(raw.get("smooth_angle", (style.get("shading") or {}).get("smooth_angle", 40)), env, f"{where}.smooth_angle", ctx, 40.0)
        material = raw.get("material")
        if material is not None and material not in materials:
            ctx.error("SRC_REF", f"{where}.material", f"unknown material '{material}'", suggest(material, materials).strip())
        pivot = raw.get("pivot")
        for iname, imesh, info in _replicate(pname, mesh, raw, env, ctx, where):
            piv = None
            if pivot is not None:
                c = anchor_coeffs(pivot, f"{where}.pivot", ctx)
                piv = anchor_point(imesh.bounds(), c) if c is not None else None
            parts.append(Part(iname, pname, imesh, material, shading, smooth_angle, raw.get("parent"), piv,
                              list(raw.get("tags") or []), str(raw.get("doc", "")), info))
    if len(parts) > LIMITS.max_instances:
        ctx.error("SRC_LIMIT", "parts", f"{len(parts)} instances exceeds limit {LIMITS.max_instances}")
    total = sum(p.mesh.n_tris for p in parts)
    if total > LIMITS.max_triangles_total:
        ctx.error("SRC_LIMIT", "parts", f"{total} triangles exceeds hard limit {LIMITS.max_triangles_total}")

    names = {p.name for p in parts}
    for p in parts:  # resolve semantic parents onto instances (mirror/array aware)
        if p.parent is None:
            continue
        if p.parent not in raw_parts:
            ctx.error("SRC_REF", f"parts.{p.base}.parent", f"unknown parent '{p.parent}'", suggest(p.parent, raw_parts).strip())
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
            tgt = next((p for p in parts if p.name == str(at.get("to"))), None)
            tb = tgt.bounds if tgt else base_bounds.get(str(at.get("to")))
            if tb is None:
                ctx.error("SRC_REF", f"{where}.attach.to", f"unknown part '{at.get('to')}'", suggest(str(at.get("to")), names).strip())
                continue
            c = anchor_coeffs(at.get("at"), f"{where}.attach.at", ctx)
            off = S.vec(at.get("offset", [0, 0, 0]), 3, env, f"{where}.attach.offset", ctx) or [0, 0, 0]
            pos = anchor_point(tb, c if c is not None else np.zeros(3)) + np.asarray(off)
            owner = tgt.name if tgt else str(at.get("to"))
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
                 (time.perf_counter() - t0) * 1000)


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
