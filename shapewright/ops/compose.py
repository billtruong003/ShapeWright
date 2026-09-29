"""Composite generators: geometry built from other geometry expressions.

These make composition recursive without special cases: any geometry
expression (generator + ops + transform + material) can be an input, and the
result is itself a geometry expression that can take ops, be a boolean tool,
be mirrored, and so on.

    {type: boolean, operation: difference,
     base:  {type: chamfer_box, size: [...], ops: [{type: taper, scale: 0.8}]},
     tools: [{type: cylinder, ..., rotate: [90, 0, 0], translate: [0, 0.1, 0]}]}
"""

from __future__ import annotations

from .. import backend
from ..limits import LIMITS, check
from ..mesh import concat
from ..registry import Param, shape


@shape("boolean", "Boolean of geometry expressions: base (op) each tool, in order. Inputs may carry their own ops, "
       "transforms and materials; faces keep their provenance.",
       [Param("operation", "str", "difference", "union | difference | intersection", choices=("union", "difference", "intersection")),
        Param("base", "geometry", doc="the geometry expression to start from"),
        Param("tools", "geometry_list", doc="geometry expressions applied in order")],
       category="compose", topology="rebuild",
       example="{type: boolean, operation: difference, base: {type: chamfer_box, size: [0.4, 0.3, 0.3], chamfer: 0.02}, "
               "tools: [{type: cylinder, radius: 0.08, height: 0.5, rotate: [90, 0, 0], ops: [{type: taper, scale: 0.6}]}]}")
def boolean(a, b):
    m = b.build_geometry(a["base"], "base")
    for i, t in enumerate(a["tools"]):
        out = backend.boolean(m, b.build_geometry(t, f"tools[{i}]"), a["operation"]).merged()
        m = out if a["operation"] == "union" else b.cut_check(m, out, f"{a['operation']} with tools[{i}]")
    return m


@shape("combine", "Several geometry expressions kept as separate shells in one part (no boolean). "
       "Use when pieces interpenetrate by design and one semantic part is wanted.",
       [Param("items", "geometry_list", doc="geometry expressions (each may use translate/rotate/ops)")],
       category="compose", topology="rebuild",
       example="{type: combine, items: [{type: box, size: [0.2, 0.2, 0.2]}, {type: sphere, radius: 0.1, translate: [0, 0.15, 0]}]}")
def combine(a, b):
    items, total = [], 0
    for i, t in enumerate(a["items"]):
        items.append(b.build_geometry(t, f"items[{i}]"))
        total += items[-1].n_tris
        check(total, LIMITS.max_triangles_per_part, "triangles in combine")
    return concat(items)
