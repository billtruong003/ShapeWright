"""Structured diagnostics shared by the build, validators and CLI.

Reports are designed for agent context windows: every issue has a stable
``code``, a ``where`` pointing at a source path or semantic part, a one-line
message and, when possible, a concrete ``hint`` naming the field to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("error", "warning", "info")


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    where: str = ""
    layer: str = ""
    hint: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"code": self.code, "severity": self.severity, "layer": self.layer, "where": self.where, "msg": self.message}
        if self.hint:
            d["hint"] = self.hint
        if self.data:
            d["data"] = self.data
        return {k: v for k, v in d.items() if v not in ("", None)}

    def line(self) -> str:
        where = f" [{self.where}]" if self.where else ""
        hint = f"  -> {self.hint}" if self.hint else ""
        return f"{self.severity.upper():7} {self.code}{where}: {self.message}{hint}"


class SourceError(Exception):
    """Raised when an asset source cannot be built at all."""

    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("; ".join(i.line() for i in issues))


def status_of(issues: list[Issue]) -> str:
    if any(i.severity == "error" for i in issues):
        return "FAIL"
    if any(i.severity == "warning" for i in issues):
        return "WARN"
    return "PASS"


def compact_json(d: dict) -> str:
    """One top-level key per line, values on a single line: cheap for agent context."""
    import json

    body = ",\n".join(f" {json.dumps(k)}: {json.dumps(v, separators=(', ', ': '))}" for k, v in d.items())
    return "{\n" + body + "\n}"
