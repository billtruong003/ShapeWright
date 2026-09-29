import pytest

from shapewright import expr


def test_arithmetic_and_functions():
    env = {"a": 2.0, "b": 3.0}
    assert expr.evaluate("a * b + 1", env) == 7.0
    assert expr.evaluate("clamp(a * 10, 0, 5)", env) == 5
    assert expr.evaluate("a if b > 2 else 0", env) == 2.0
    assert abs(expr.evaluate("sin(90)", env) - 1.0) < 1e-12  # degrees
    assert expr.names_in("a + sqrt(b) + pi") == {"a", "b"}


def test_namespace_attributes():
    ns = expr.Namespace({"size": expr.Namespace({"x": 0.5})})
    assert expr.evaluate("seat.size.x * 2", {"seat": ns}) == 1.0
    with pytest.raises(expr.ExprError):
        expr.evaluate("seat.size.q", {"seat": ns})


@pytest.mark.parametrize("src", [
    "__import__('os')", "open('x')", "(1).__class__", "a.__dict__", "[1, 2]", "'text'", "lambda: 1",
    "a.real", "2 ** 1000", "exec('1')", "{'a': 1}", "print(1)",
])
def test_rejects_unsafe_or_unsupported(src):
    with pytest.raises(expr.ExprError):
        expr.evaluate(src, {"a": 1.0})


def test_limits():
    with pytest.raises(expr.ExprError):
        expr.evaluate("1+" * 300 + "1", {})
    with pytest.raises(expr.ExprError):
        expr.evaluate("1 / 0", {})
