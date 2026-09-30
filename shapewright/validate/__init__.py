"""Layered deterministic validation.

Layers (run in order, all always run so an agent sees every problem at once):

    source     schema, references, expressions, limits (raised during build)
    geometry   per-part mesh integrity (closed, manifold, winding, degenerate)
    assembly   semantic structure: connectivity, grounding, origin, hidden parts
    budget     production constraints from the profile: triangles, materials
    intent     design checks declared in the asset source (`checks:`)
    surface    UVs and normals: overlap, bounds, texel density
    style      heuristic, style-profile-driven warnings (never errors)
    export     file validity and round-trip (run by `sw export`)

Perceptual quality (proportions, silhouette, style fit) is deliberately NOT
scored here. `sw review` renders evidence and prints the style checklist so
the agent can judge it visually.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

LAYERS = ["source", "geometry", "assembly", "budget", "intent", "surface", "style", "export"]


@dataclass
class Validator:
    name: str
    layer: str
    fn: Callable
    doc: str
    codes: tuple


VALIDATORS: list[Validator] = []


def validator(name: str, layer: str, doc: str, codes: tuple):
    def deco(fn):
        VALIDATORS.append(Validator(name, layer, fn, doc, codes))
        return fn

    return deco


def load_builtin():
    from . import checks, seams  # noqa: F401

    seams.register()
