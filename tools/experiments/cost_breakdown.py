"""Where a fresh agent spends its tool calls (Phase 14 research).

Usage: python tools/experiments/cost_breakdown.py TRANSCRIPT.jsonl [...] [--json]

Reads Claude Code subagent transcripts (JSONL) and classifies every tool call: reading docs,
reading example assets, reading framework code, `sw` subcommands, source edits, image views, and
calls that failed. The transcripts stay outside the repository; the derived tables go into
docs/AGENT_COST.md.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


def classify(name: str, inp: dict) -> str:
    if name in ("Read",):
        p = inp.get("file_path", "")
        if p.endswith(".png"):
            return "view image"
        if "/assets/" in p or "/components/" in p:
            return "read asset/component" if p.endswith((".yaml", ".yml")) else "read asset output"
        if p.endswith(".md"):
            return "read docs"
        if "/shapewright/shapewright/" in p or p.endswith(".py"):
            return "read framework code"
        return "read other"
    if name in ("Write", "Edit", "MultiEdit"):
        p = inp.get("file_path", "")
        if "/assets/" in p or "/components/" in p:
            return "edit asset"
        return "edit framework/other"
    if name == "Bash":
        cmd = inp.get("command", "")
        labels = []  # one shell call often edits, rebuilds and reviews at once
        if "python" in cmd and re.search(r"(assets|components)/[\w/]*\.ya?ml|asset\.yaml", cmd) and ".replace(" in cmd \
                or re.search(r"sed -i[^|;&]*\.ya?ml|cat >\s*\S*\.ya?ml", cmd):
            labels.append("edit asset")
        elif "python" in cmd and re.search(r"\.(report|summary)?\.?json", cmd) and "json.load" in cmd:
            labels.append("read report json")
        elif "python" in cmd and re.search(r"\b(trimesh|manifold3d|numpy|struct)\b", cmd):
            labels.append("custom geometry/file probe")
        elif re.search(r"\b(cat|head|sed -n|less)\b[^|;&]*\.md\b", cmd):
            labels.append("read docs")
        elif re.search(r"\b(cat|head|sed -n|less)\b[^|;&]*\.ya?ml\b", cmd):
            labels.append("read asset/component")
        elif re.search(r"\b(cat|head|sed -n|less|tail)\b", cmd) and ".py" in cmd:
            labels.append("read framework code")
        labels += [f"sw {m}" for m in re.findall(r"\./sw\s+(\w+)", cmd)]
        if labels:
            return labels
        if re.search(r"\b(grep|rg|find|ls)\b", cmd):
            return "search/list"
        if re.search(r"\b(cat|head|sed -n)\b", cmd):
            return "read (shell)"
        if "python" in cmd:
            return "python script"
        return "shell other"
    if name in ("Grep", "Glob"):
        return "search/list"
    return name


def analyse(path: Path) -> dict:
    calls, failed = Counter(), Counter()
    pending = {}
    usage_out = 0
    for line in path.open():
        d = json.loads(line)
        m = d.get("message") or {}
        u = m.get("usage") or {}
        usage_out += u.get("output_tokens", 0) or 0
        c = m.get("content")
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get("type") == "tool_use":
                ks = classify(b["name"], b.get("input") or {})
                ks = ks if isinstance(ks, list) else [ks]
                calls.update(ks)
                calls["(tool calls)"] += 1
                pending[b["id"]] = ks[-1]
            elif b.get("type") == "tool_result":
                t = b.get("content")
                t = t if isinstance(t, str) else json.dumps(t)
                k = pending.get(b.get("tool_use_id"), "?")
                if b.get("is_error") or t.startswith("FAIL") or "Traceback" in t or "SourceError" in t or "ERROR " in t[:400]:
                    failed[k] += 1
    return {"file": path.name, "calls": dict(calls), "failed": dict(failed), "total": calls["(tool calls)"],
            "output_tokens": usage_out}


def main(argv):
    files = [Path(a) for a in argv if not a.startswith("--")]
    if not files:
        print(__doc__)
        return 2
    res = [analyse(f) for f in files]
    if "--json" in argv:
        print(json.dumps(res, indent=1))
        return 0
    for r in res:
        print(f"{r['file']}: {r['total']} calls, {r['output_tokens']} output tokens")
        for k, v in sorted(r["calls"].items(), key=lambda kv: -kv[1]):
            f = r["failed"].get(k, 0)
            print(f"  {k:24s} {v:4d}" + (f"  ({f} failed/FAIL)" if f else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
