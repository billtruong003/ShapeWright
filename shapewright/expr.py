"""Restricted arithmetic expressions used inside asset sources.

Asset sources are data, not programs. Numeric fields may contain expressions
such as ``"seat_height - seat_thickness / 2"`` so that relationships between
dimensions survive edits. This evaluator walks a whitelisted subset of the
Python AST: numbers, parameter names, arithmetic, comparisons, conditionals,
a fixed set of math functions and attribute lookups on read-only namespaces
(used by design checks such as ``backrest.size.x / seat.size.x``).

Nothing here can import, call arbitrary functions, touch the filesystem or
reach Python object internals.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Mapping

from .limits import LIMITS


class ExprError(ValueError):
    pass


class Namespace:
    """Read-only attribute bag exposed to expressions (e.g. part metrics)."""

    __slots__ = ("_items", "_label")

    def __init__(self, items: Mapping[str, Any], label: str = "namespace"):
        self._items = dict(items)
        self._label = label

    def get(self, name: str) -> Any:
        if name not in self._items:
            known = ", ".join(sorted(self._items)) or "nothing"
            raise ExprError(f"'{self._label}' has no field '{name}' (has: {known})")
        return self._items[name]

    def keys(self):
        return self._items.keys()


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _lerp(a, b, t):
    return a + (b - a) * t


FUNCTIONS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "clamp": _clamp,
    "lerp": _lerp,
}

CONSTANTS = {"pi": math.pi, "tau": math.tau, "true": True, "false": False}

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}
_CMP = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def names_in(src: str) -> set[str]:
    """Top-level names referenced by an expression (for dependency ordering)."""
    tree = _parse(src)
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in FUNCTIONS and node.id not in CONSTANTS:
            out.add(node.id)
    return out


def _parse(src: str) -> ast.Expression:
    if len(src) > LIMITS.max_expr_length:
        raise ExprError(f"expression longer than {LIMITS.max_expr_length} characters")
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"syntax error in '{src}': {e.msg}") from None
    if sum(1 for _ in ast.walk(tree)) > LIMITS.max_expr_nodes:
        raise ExprError("expression too complex")
    return tree


def evaluate(src: str, env: Mapping[str, Any]) -> Any:
    tree = _parse(src)
    try:
        value = _eval(tree.body, env)
    except ExprError:
        raise
    except ZeroDivisionError:
        raise ExprError(f"division by zero in '{src}'") from None
    except (TypeError, ValueError, OverflowError) as e:
        raise ExprError(f"cannot evaluate '{src}': {e}") from None
    if isinstance(value, float) and not math.isfinite(value):
        raise ExprError(f"'{src}' is not finite")
    return value


def _eval(node: ast.AST, env: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or isinstance(node.value, (int, float)):
            return node.value
        raise ExprError(f"only numbers are allowed, got {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        raise ExprError(f"unknown name '{node.id}'")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Pow) and (abs(right) > 64 or abs(left) > 1e6):
            raise ExprError("exponent too large")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.BoolOp):
        values = [_eval(v, env) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            if type(op) not in _CMP:
                raise ExprError("unsupported comparison")
            right = _eval(comp, env)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval(node.body, env) if _eval(node.test, env) else _eval(node.orelse, env)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise ExprError(f"only these functions are allowed: {', '.join(sorted(FUNCTIONS))}")
        if node.keywords:
            raise ExprError("keyword arguments are not allowed")
        return FUNCTIONS[node.func.id](*[_eval(a, env) for a in node.args])
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise ExprError("private attributes are not allowed")
        base = _eval(node.value, env)
        if not isinstance(base, Namespace):
            raise ExprError(f"cannot read '.{node.attr}' of a number")
        return base.get(node.attr)
    raise ExprError(f"unsupported syntax: {type(node).__name__}")
