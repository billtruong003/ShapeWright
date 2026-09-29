"""Resource limits for evaluating untrusted asset sources.

Asset sources are written by agents inside autonomous loops. A typo such as
``segments: 20000`` must fail fast with a clear message instead of freezing the
loop or exhausting memory. Every limit here is checked by the kernel, not by
individual operations, so new operations inherit protection automatically.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_triangles_total: int = 200_000
    max_triangles_per_part: int = 100_000
    max_parts: int = 256
    max_instances: int = 1024
    max_segments: int = 256
    max_array_count: int = 128
    max_ops_per_part: int = 64
    max_subdivide_iterations: int = 3
    max_expr_length: int = 400
    max_expr_nodes: int = 200
    max_extends_depth: int = 8
    max_render_size: int = 2048
    max_source_bytes: int = 512_000
    build_timeout_s: int = 120


LIMITS = Limits()


class LimitError(Exception):
    pass


def check(value: float, maximum: float, what: str) -> None:
    if value > maximum:
        raise LimitError(f"{what} = {value} exceeds limit {maximum}")
