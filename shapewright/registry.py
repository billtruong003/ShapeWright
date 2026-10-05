"""Operation registry: the single source of truth for modelling vocabulary.

Shapes (generators) and ops (mesh -> mesh modifiers) register themselves with
a typed parameter spec. The spec is used to

* validate and resolve asset-source fields (with expressions),
* produce precise error messages with suggestions,
* generate the machine-readable capability manifest (``sw caps``).

Adding a capability therefore means adding one decorated function; the CLI,
validator and documentation pick it up automatically.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Callable

REQUIRED = object()

KINDS = {
    "num": "number",
    "int": "integer",
    "vec2": "[x, y]",
    "vec3": "[x, y, z]",
    "num|vec3": "number or [x, y, z]",
    "points2": "list of [x, y]",
    "points3": "list of [x, y, z]",
    "axis": "x | y | z",
    "str": "string",
    "bool": "true | false",
    "geometry": "nested geometry expression {type, ..., ops, material, rotate, translate}",
    "geometry_list": "list of geometry expressions",
    "sdf_list": "list of SDF items {sdf: sphere | ellipsoid | capsule | cone | box | torus, ...}",
    "decal_list": "list of decals {kind: eye | disc | smile, at: [x, y, z], ...}",
}

TOPOLOGY = ("preserve", "refine", "rebuild", "resample", "generate")


@dataclass
class Param:
    name: str
    kind: str
    default: Any = REQUIRED
    doc: str = ""
    choices: tuple = ()
    min: float | None = None
    max: float | None = None

    @property
    def required(self) -> bool:
        return self.default is REQUIRED

    def describe(self) -> dict:
        d = {"type": KINDS.get(self.kind, self.kind), "doc": self.doc}
        if not self.required:
            d["default"] = self.default
        if self.choices:
            d["choices"] = list(self.choices)
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        return d


@dataclass
class OpSpec:
    name: str
    family: str  # "shape" or "op"
    fn: Callable
    doc: str
    params: list[Param] = field(default_factory=list)
    category: str = ""
    example: str = ""
    topology: str = "generate"  # attribute policy class, see mesh.POLICY

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def describe(self) -> dict:
        d = {"doc": self.doc, "category": self.category, "topology": self.topology,
             "params": {p.name: p.describe() for p in self.params}}
        if self.example:
            d["example"] = self.example
        return d


SHAPES: dict[str, OpSpec] = {}
OPS: dict[str, OpSpec] = {}


def _register(table: dict, family: str, name: str, doc: str, params: list[Param], category: str, example: str, topology: str):
    if topology not in TOPOLOGY:
        raise ValueError(f"{family} '{name}': topology must be one of {TOPOLOGY}")

    def deco(fn):
        if name in table:
            raise ValueError(f"{family} '{name}' registered twice")
        table[name] = OpSpec(name, family, fn, doc, params, category, example, topology)
        return fn

    return deco


def shape(name: str, doc: str, params: list[Param], category: str = "primitive", example: str = "", topology: str = "generate"):
    """Register a generator. Composite generators (boolean, combine) declare the
    topology class of what they do to their inputs."""
    return _register(SHAPES, "shape", name, doc, params, category, example, topology)


def op(name: str, doc: str, params: list[Param], topology: str, category: str = "modifier", example: str = ""):
    """Register a modifier. `topology` is mandatory: it states the attribute
    contract the op obeys (preserve | refine | rebuild | resample)."""
    return _register(OPS, "op", name, doc, params, category, example, topology)


def suggest(name: str, options) -> str:
    close = difflib.get_close_matches(str(name), list(options), n=1, cutoff=0.6)
    return f" Did you mean '{close[0]}'?" if close else ""


def load_builtin():
    # importing registers everything
    from .ops import compose, modifiers, organic, shapes, sources  # noqa: F401
