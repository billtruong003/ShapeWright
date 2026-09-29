"""Semantic materials: archetypes with human-meaningful parameters (docs/SURFACES.md).

A material is a *recipe*: an archetype (flat, wood, metal, stone, painted) plus
semantic parameters ("grain_strength", "edge_wear", ...). Recipes are evaluated
deterministically at 3D surface points (object space) and baked into the UV
atlas by `bake.py`. Pixels are build artifacts; the recipe is the source.

Archetypes are registered like shapes and ops: typed parameters, docs,
examples, suggestions, and `sw caps`/`sw doc` listing.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .registry import Param, suggest

ARCHETYPES: dict[str, "Archetype"] = {}


@dataclass
class Archetype:
    name: str
    fn: Callable
    doc: str
    params: list[Param]
    example: str = ""

    def describe(self) -> dict:
        d = {"doc": self.doc, "params": {p.name: p.describe() for p in self.params}}
        if self.example:
            d["example"] = self.example
        return d


COMMON = [
    Param("color", "color", "#b0b0b0", "base colour (sRGB hex or [r, g, b] 0..1)"),
    Param("roughness", "num", 0.8, "0 = mirror, 1 = matte", min=0, max=1),
    Param("edge_wear", "num", 0.0, "0..1: convex edges lighten/scuff (reads as handled, worn)", min=0, max=1),
    Param("edge_color", "color", None, "colour of worn edges (default: a lighter base colour)"),
    Param("edge_width", "num", 0.012, "worn band width in metres", min=0.001, max=0.1),
    Param("seed", "int", 0, "variation seed (same seed = same pattern)"),
    Param("grime", "num", 0.0, "0..1: dirt collecting in creases and near the ground (reads as used, dirty)", min=0, max=1),
    Param("grime_color", "color", None, "colour of the dirt (default: a much darker base colour)"),
    Param("grime_height", "num", 0.15, "how far up from the asset's base ground dirt reaches, in metres", min=0.0, max=5),
]


def archetype(name: str, doc: str, params: list[Param], example: str = ""):
    def deco(fn):
        ARCHETYPES[name] = Archetype(name, fn, doc, COMMON + params, example)
        return fn
    return deco


# ------------------------------------------------------------------ deterministic noise


def _hash3(ix, iy, iz, seed: int) -> np.ndarray:
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def value_noise(P: np.ndarray, seed: int = 0) -> np.ndarray:
    """Smooth value noise in [0, 1] at points P (k, 3), unit lattice."""
    base = np.floor(P)
    f = P - base
    u = f * f * (3 - 2 * f)
    ix, iy, iz = base[:, 0].astype(np.int64), base[:, 1].astype(np.int64), base[:, 2].astype(np.int64)
    out = np.zeros(len(P))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (u[:, 0] if dx else 1 - u[:, 0]) * (u[:, 1] if dy else 1 - u[:, 1]) * (u[:, 2] if dz else 1 - u[:, 2])
                out += w * _hash3(ix + dx, iy + dy, iz + dz, seed)
    return out


def fbm(P: np.ndarray, seed: int = 0, octaves: int = 4) -> np.ndarray:
    total, amp, norm = np.zeros(len(P)), 1.0, 0.0
    for o in range(octaves):
        total += amp * value_noise(P * (2 ** o), seed + 17 * o)
        norm += amp
        amp *= 0.5
    return total / norm


# ------------------------------------------------------------------ colour helpers (sRGB 0..1)


def mix(a, b, t):
    return a + (np.asarray(b) - a) * np.asarray(t)[..., None]


def lighten(c, amount: float):
    h, light, s = colorsys.rgb_to_hls(*np.clip(c, 0, 1))
    return np.array(colorsys.hls_to_rgb(h, min(1.0, light + amount * (1 - light)), s * (1 - 0.3 * amount)))


@dataclass
class Samples:
    """Surface points of one part to evaluate a material at."""

    P: np.ndarray  # (k, 3) world positions
    N: np.ndarray  # (k, 3) unit normals
    edge: np.ndarray  # (k,) 0..1 proximity to sharp convex edges (1 = on the edge), per the material's edge_width
    axis: np.ndarray  # (3,) the part's long axis (grain direction)
    center: np.ndarray  # (3,) part centre
    part_seed: int = 0
    cavity: np.ndarray | None = None  # (k,) 0..1 proximity to concave creases within the part
    height: np.ndarray | None = None  # (k,) metres above the asset's lowest point


@dataclass
class Channels:
    base: np.ndarray  # (k, 3) sRGB 0..1
    roughness: np.ndarray  # (k,)
    metallic: np.ndarray  # (k,)
    extras: dict = field(default_factory=dict)


def _const(k, v):
    return np.full(k, float(v))


def _apply_wear(a, s: Samples, base: np.ndarray, rough: np.ndarray, metal_rough_drop: float = 0.0):
    if a["edge_wear"] <= 0:
        return base, rough
    edge_col = np.asarray(a["edge_color"] if a["edge_color"] is not None else lighten(np.asarray(a["color"]), 0.45))
    # break the band up so it reads hand-worn, not machined
    breakup = fbm(s.P / max(a["edge_width"] * 3, 1e-3), a["seed"] + 101, 2)
    w = np.clip(s.edge * (0.6 + 0.8 * breakup) * a["edge_wear"] * 1.4, 0, 1)
    return mix(base, edge_col, w), rough - metal_rough_drop * w


def apply_grime(a, s: Samples, ch: "Channels") -> "Channels":
    """Common to every archetype: darken creases and the lower band, broken up by noise; dirt is rough and non-metal."""
    if a.get("grime", 0) <= 0:
        return ch
    k = len(s.P)
    cav = s.cavity if s.cavity is not None else np.zeros(k)
    ground = np.zeros(k) if s.height is None or a["grime_height"] <= 0 else np.clip(1 - s.height / a["grime_height"], 0, 1) ** 1.5
    breakup = fbm(s.P / 0.06, a["seed"] + 211, 3)
    w = np.clip(np.maximum(cav, ground) * (0.35 + 0.9 * breakup) * a["grime"] * 1.3, 0, 0.9)
    col = np.asarray(a["grime_color"]) if a["grime_color"] is not None else np.asarray(a["color"]) * 0.35
    return Channels(mix(ch.base, col, w), np.clip(ch.roughness + 0.25 * w, 0, 1), ch.metallic * (1 - w), ch.extras)


# ------------------------------------------------------------------ archetypes


@archetype("flat", "Uniform colour and roughness (v0.1 behaviour).", [
    Param("metallic", "num", 0.0, "0 = dielectric, 1 = metal", min=0, max=1)],
    example="{archetype: flat, color: '#8a5a36', roughness: 0.85}")
def flat(a, s: Samples) -> Channels:
    k = len(s.P)
    base = np.tile(np.asarray(a["color"]), (k, 1))
    rough = _const(k, a["roughness"])
    base, rough = _apply_wear(a, s, base, rough)
    return Channels(base, rough, _const(k, a["metallic"]))


@archetype("wood", "Stylized wood: growth rings along the part's long axis, streaky grain, optional worn edges.", [
    Param("grain_strength", "num", 0.35, "0 = flat colour, 1 = strong ring contrast", min=0, max=1),
    Param("grain_scale", "num", 0.03, "ring spacing in metres", min=0.002, max=1),
    Param("grain_color", "color", None, "colour of the dark grain (default: darker base)"),
    Param("streaks", "num", 0.4, "0..1 lengthwise streak variation", min=0, max=1),
    Param("knots", "num", 0.0, "0..1 amount of darker knot blotches", min=0, max=1),
    Param("grain_axis", "str", "auto", "direction the grain runs: auto (each part's longest axis) | x | y | z (asset axes; "
          "e.g. y for end-grain rings on a horizontal cut face)", choices=("auto", "x", "y", "z"))],
    example="{archetype: wood, color: '#8a5a36', grain_strength: 0.35, grain_scale: 0.03, edge_wear: 0.3}")
def wood(a, s: Samples) -> Channels:
    k = len(s.P)
    base_c = np.asarray(a["color"])
    dark = np.asarray(a["grain_color"]) if a["grain_color"] is not None else base_c * 0.62
    axis = s.axis if a.get("grain_axis", "auto") == "auto" else np.eye(3)["xyz".index(a["grain_axis"])]
    rel = s.P - s.center
    along = rel @ axis
    radial = np.linalg.norm(rel - np.outer(along, axis), axis=1)
    seed = a["seed"] + s.part_seed
    warp = fbm(np.c_[along * 2.0, radial * 6, np.zeros(k)], seed, 3) * 1.5
    rings = 0.5 + 0.5 * np.sin(2 * np.pi * (radial / a["grain_scale"] + warp))
    rings = rings ** 3  # thin dark lines, wide light bands
    streak = fbm(np.c_[along * 0.8, (s.P @ np.array([0.37, 0.61, 0.7])) * 25, np.zeros(k)], seed + 7, 3)
    t = np.clip(a["grain_strength"] * (0.75 * rings + a["streaks"] * 0.6 * (streak - 0.5)), 0, 1)
    base = mix(np.tile(base_c, (k, 1)), dark, t)
    if a["knots"] > 0:
        blot = fbm(s.P * 4, seed + 31, 2)
        base = mix(base, dark * 0.8, np.clip((blot - (1 - 0.25 * a["knots"])) * 8, 0, 1))
    rough = _const(k, a["roughness"]) + 0.05 * (t - 0.5)
    base, rough = _apply_wear(a, s, base, rough)
    return Channels(base, np.clip(rough, 0, 1), np.zeros(k))


@archetype("metal", "Stylized metal: subtle brushed variation, brighter worn edges, optional rust patches.", [
    Param("variation", "num", 0.15, "0..1 tonal variation", min=0, max=1),
    Param("rust", "num", 0.0, "0..1 rust coverage (rust is non-metallic and rough)", min=0, max=1),
    Param("rust_color", "color", "#7a4a2a", "rust colour"),
    Param("scale", "num", 0.08, "variation feature size in metres", min=0.005, max=2)],
    example="{archetype: metal, color: '#5a5f66', roughness: 0.5, edge_wear: 0.5, rust: 0.2}")
def metal(a, s: Samples) -> Channels:
    k = len(s.P)
    seed = a["seed"] + s.part_seed
    n = fbm(s.P / a["scale"], seed, 4)
    base = np.tile(np.asarray(a["color"]), (k, 1)) * (1 + a["variation"] * (n - 0.5))[:, None]
    rough = _const(k, a["roughness"]) + 0.15 * a["variation"] * (n - 0.5)
    metallic = np.ones(k)
    base, rough = _apply_wear(a, s, base, rough, metal_rough_drop=0.25)
    if a["rust"] > 0:
        r = fbm(s.P / (a["scale"] * 1.5), seed + 53, 4)
        cavity = 1 - s.edge  # rust gathers away from worn edges
        m = np.clip((r * cavity - (1 - a["rust"]) * 0.8) * 6, 0, 1)
        base = mix(base, np.asarray(a["rust_color"]), m)
        rough = rough + (0.95 - rough) * m
        metallic = metallic * (1 - m)
    return Channels(np.clip(base, 0, 1), np.clip(rough, 0, 1), metallic)


@archetype("stone", "Stylized stone: blotchy tonal variation, darker cavities, lighter edges.", [
    Param("variation", "num", 0.35, "0..1 tonal variation", min=0, max=1),
    Param("scale", "num", 0.15, "blotch size in metres", min=0.005, max=5),
    Param("secondary_color", "color", None, "second tone mixed in by the noise (default: darker base)")],
    example="{archetype: stone, color: '#8b8f94', variation: 0.4, edge_wear: 0.3}")
def stone(a, s: Samples) -> Channels:
    k = len(s.P)
    seed = a["seed"] + s.part_seed
    n = fbm(s.P / a["scale"], seed, 5)
    second = np.asarray(a["secondary_color"]) if a["secondary_color"] is not None else np.asarray(a["color"]) * 0.7
    base = mix(np.tile(np.asarray(a["color"]), (k, 1)), second, np.clip((n - 0.5) * 2 * a["variation"] + 0.5 * a["variation"], 0, 1))
    rough = _const(k, a["roughness"])
    base, rough = _apply_wear(a, s, base, rough)
    return Channels(np.clip(base, 0, 1), rough, np.zeros(k))


@archetype("painted", "Painted surface over an underlying material colour; worn edges reveal the under colour (chipped paint).", [
    Param("under_color", "color", "#6b4a30", "colour revealed where paint is chipped"),
    Param("chips", "num", 0.4, "0..1 how much paint is chipped at edges", min=0, max=1),
    Param("variation", "num", 0.08, "0..1 brush/tonal variation", min=0, max=1)],
    example="{archetype: painted, color: '#3f6b8a', under_color: '#6b4a30', chips: 0.5}")
def painted(a, s: Samples) -> Channels:
    k = len(s.P)
    seed = a["seed"] + s.part_seed
    n = fbm(s.P * 12, seed, 3)
    base = np.tile(np.asarray(a["color"]), (k, 1)) * (1 + a["variation"] * (n - 0.5))[:, None]
    chip = np.clip((s.edge * (0.5 + fbm(s.P * 40, seed + 9, 2)) - (1 - a["chips"])) * 4, 0, 1)
    base = mix(base, np.asarray(a["under_color"]), chip)
    rough = _const(k, a["roughness"]) + 0.1 * chip
    base, rough = _apply_wear(a, s, base, rough)
    return Channels(np.clip(base, 0, 1), np.clip(rough, 0, 1), np.zeros(k))


def is_textured(mat: dict) -> bool:
    args = mat.get("args", {})
    return mat.get("archetype", "flat") != "flat" or bool(mat.get("layers")) or args.get("edge_wear", 0) > 0 or args.get("grime", 0) > 0


def archetype_names():
    return sorted(ARCHETYPES)


def unknown_archetype_hint(name: str) -> str:
    return suggest(name, ARCHETYPES).strip() or f"archetypes: {', '.join(sorted(ARCHETYPES))}"
