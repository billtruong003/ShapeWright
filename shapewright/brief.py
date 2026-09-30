"""`sw brief "REQUEST"`: the onboarding an agent needs for one request, in one call (Phase 14).

FRESH_AGENT_10 baselines spent 16-17 of about 40 tool calls before their first build: doctor, caps,
several docs, `sw doc` per shape, and reading two to four example assets picked by listing
`assets/`. This command ranks the example assets against the request, prints the best one's
source, suggests a profile and budget, gives compact docs for the vocabulary the examples use, and
lists the rules that apply to this kind of prop. It is deterministic: keyword overlap, not a model.
"""

from __future__ import annotations

import re

import yaml

from .caps import manifest

from . import paths

ROOT = paths.LIB

STOP = {"the", "and", "with", "for", "that", "from", "into", "under", "over", "game", "prop", "asset", "make", "create",
        "small", "large", "model", "textured", "texture", "textures", "surface", "detail", "export", "exported",
        "validated", "ready", "triangles", "tris", "can", "its", "has", "two", "one", "three", "four", "style", "stylized"}

# request cue -> (rule shown, words that trigger it)
RULES = [
    (("swing", "hinge", "hinged", "open", "opens", "turn", "turns", "rotate", "rotating", "crank", "lid", "door", "spin",
      "wheel", "moving", "move", "animated", "swinging"),
     "Moving part: give it `pivot:` (a named anchor, [cx, cy, cz] in -1..1, or `{at: [x, y, z]}` in asset coordinates, "
     "expressions allowed). Children follow it via `parent:`; export keeps the group as its own node at the pivot, "
     "with its own collision. Example: assets/treasure_chest (lid)."),
    (("wall", "mounted", "bracket", "hanging", "hangs", "hang", "sconce", "shelf"),
     "Wall prop: `asset: {placement: wall}`; the wall is the plane z = 0 and the prop extends toward +Z. "
     "Example: assets/torch_bracket."),
    (("leg", "legs", "splayed", "frame", "trestle", "stand", "brace", "braced", "strut"),
     "Legs/braces between two points: `strut` (from/to in asset coordinates). Trim a splayed leg at the ground with "
     "ops: [{type: flat_bottom, at: 0}]."),
    (("godot", "unreal", "unity", "engine"),
     "Engine delivery: `profile: godot|unreal|unity` (or `export: {target: ...}`; `sw export ASSET --target unreal` for "
     "another engine). Static parts merge per material; collision: {mode: single_hull | hull | box}. docs/PRODUCTION.md."),
    (("wood", "wooden", "oak", "plank", "weathered", "iron", "metal", "wrought", "rusty", "stone", "brick", "painted",
      "paint", "worn", "old", "dirty", "mossy"),
     "Surface detail = material archetypes (wood, metal, stone, painted, flat) with params (grain_strength, edge_wear, "
     "grime, ...): `sw doc wood`. Look with `sw render ASSET --mode textured` and `sw materials ASSET`. "
     "Run `sw uv ASSET lock` before texture work."),
    (("mobile", "phone", "android", "ios"),
     "Mobile: draw calls matter; keep materials within the budget and let `export: {merge: by_material}` "
     "(or a godot/unreal/unity profile) merge static parts."),
    (("sign", "arrow", "signpost", "board", "plaque"),
     "Mounted boards and signs must touch what holds them: the floating check gives the gap in metres; attach or move "
     "by that gap. `floating_ok` is only for parts meant to hover."),
]

GENERIC_RULES = [
    "Units m, +Y up, front +Z, right +X, degrees. Assets rest on y = 0.",
    "Place parts with `anchor:` + `position:` or `attach: {to: part, at: anchor, offset: [...]}`; measure other parts "
    "with `measure:` instead of re-deriving them (docs/RELATIONSHIPS.md).",
    "Name dimensions as params; write intent as `checks:`. Don't relax a failing check to pass: change the geometry "
    "or say why the intent changed.",
    "`sw review` writes .build/sheet.png: open it every iteration. `sw stats` gives exact part sizes.",
    "Instances: `mirror: x` -> NAME_left/NAME_right; `mirror: [x, z]` -> NAME_front_left, NAME_back_right, ... "
    "(front/back first); `array` -> NAME_0..n. Use these names in measure, checks and --part.",
    "Commas inside expressions are fine in [...] and {...}; quote text that has commas and colons (doc: \"a, b: c\").",
]


def _tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z][a-z0-9_]+", text.lower()):
        for part in w.split("_"):
            if len(part) >= 3 and part not in STOP:
                out.add(part[:-1] if part.endswith("s") and len(part) > 4 else part)
    return out


def _examples() -> list[dict]:
    out = []
    seen = set()
    for p in sorted(q for d in paths.asset_dirs() + [ROOT / "assets"] for q in d.glob("*/asset.yaml")):
        if p.resolve() in seen:
            continue
        seen.add(p.resolve())
        try:
            src = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError:
            continue
        if "extends" in src:
            continue  # variants repeat their base
        meta = src.get("asset") or {}
        head = " ".join(str(meta.get(k, "")) for k in ("name", "kind", "description")) + " " + " ".join(meta.get("tags") or [])
        parts = src.get("parts") or {}
        docs = " ".join(str((v or {}).get("doc", "")) for v in parts.values() if isinstance(v, dict))
        out.append({"path": p, "name": p.parent.name, "src": src, "text": p.read_text(), "head": _tokens(head),
                    "parts": _tokens(" ".join(parts)), "body": _tokens(docs), "all": _tokens(p.read_text()),
                    "lines": p.read_text().count("\n")})
    return out


def rank(request: str, examples: list[dict] | None = None) -> list[tuple[float, dict]]:
    words = _tokens(request)
    examples = _examples() if examples is None else examples
    import math

    n = max(len(examples), 1)
    idf = {w: math.log((n + 1) / (1 + sum(w in e["all"] for e in examples))) + 0.1 for w in words}  # rare words decide
    scored = []
    for e in examples:
        s = sum(idf[w] * (3.0 if w in e["head"] else 2.0 if w in e["parts"] else 1.0 if w in e["body"] else 0.3 if w in e["all"] else 0.0)
                for w in words)
        # structure outweighs setting words ("tavern" sign is not a tavern chair)
        cues = _tokens(request)
        if cues & {"swing", "hinge", "hinged", "open", "turn", "crank", "lid", "door", "spin", "rotate"}:
            s += 4.0 if "pivot:" in e["text"] else 0.0
        if cues & {"wall", "mounted", "bracket", "hanging", "hang", "sconce"}:
            s += 5.0 if "placement: wall" in e["text"] else 0.0
        if "pack" in e["src"] or "component:" in e["text"]:
            s *= 0.7  # a good starting point is self-contained: packs and components mean more files to read
        scored.append((s, e))
    scored.sort(key=lambda t: (-t[0], t[1]["lines"]))
    return scored


def _profile(request: str, profiles: dict) -> tuple[str, str]:
    low = request.lower()
    for name in ("godot", "unreal", "unity"):
        if name in low:
            return name, f"the {name} profile packages collision, merging and LODs for {name.capitalize()}"
    if any(w in low for w in ("mobile", "phone", "android", "ios")):
        return "mobile_mid", "mobile"
    if " vr" in f" {low}" or "quest" in low:
        return "vr_standalone", "standalone VR"
    if "web" in low or "browser" in low:
        return "web", "web"
    return "desktop_indie", "no platform named"


def _used_vocab(src: dict) -> tuple[list[str], list[str], list[str]]:
    text = yaml.safe_dump(src)
    shapes = sorted(set(re.findall(r"type: (\w+)", text)))
    arche = sorted(set(re.findall(r"archetype: (\w+)", text)))
    return shapes, arche, sorted(set(re.findall(r"\b(arc|helix|line):", text)))


def brief(request: str, n_examples: int = 3) -> str:
    m = manifest()
    lines: list[str] = []
    add = lines.append
    add(f"BRIEF for: {request}")
    add("")
    ranked = [t for t in rank(request) if t[0] > 0][:n_examples]
    add("CLOSEST EXAMPLE ASSETS (copying structure is encouraged; `sw new NAME` then edit, or `sw new NAME --from EXAMPLE`)")
    if not ranked:
        add("  (no close match; browse assets/ by name)")
    for s, e in ranked:
        meta = e["src"].get("asset") or {}
        tri = (e["src"].get("budget") or {}).get("triangles", "")
        add(f"  {e['name']:22s} score {s:4.1f}  {meta.get('kind', '')}  profile {e['src'].get('profile', '')}"
            f"{'  budget ' + str(tri) + ' tris' if tri else ''}  parts {len(e['src'].get('parts') or {})}")
    add("")
    tris = re.search(r"(\d[\d,]*)\s*(?:triangles|tris)", request.lower())
    prof, why = _profile(request, m["profiles"])
    try:
        budget = (yaml.safe_load((paths.find("profiles", prof) or ROOT / "profiles" / f"{prof}.yaml").read_text()) or {}).get("budget", {})
    except OSError:
        budget = {}
    add(f"PROFILE: profile: {prof}  ({why}; budget {budget})")
    if tris:
        add(f"  the request sets the budget: budget: {{triangles: {tris.group(1).replace(',', '')}}} (overrides the profile's)")
    add("  other profiles: " + ", ".join(k for k in m["profiles"] if k != prof))
    add("")
    add("RULES FOR THIS REQUEST")
    words = set(re.findall(r"[a-z]+", request.lower()))
    for cues, rule in RULES:
        if words & set(cues):
            add("  - " + rule)
    for rule in GENERIC_RULES:
        add("  - " + rule)
    add("")
    used_shapes: set[str] = set()
    used_arche: set[str] = set()
    for _, e in ranked[:2]:
        sh, ar, _gen = _used_vocab(e["src"])
        used_shapes |= set(sh)
        used_arche |= set(ar)
    add("VOCABULARY (all names; `sw doc NAME` for any one)")
    add("  shapes: " + ", ".join(m["shapes"]))
    add("  ops: " + ", ".join(m["ops"]))
    add("  material archetypes: " + ", ".join(m["material_archetypes"]) + "   point generators: " + ", ".join(m["point_generators"]))
    add("  part keys: " + ", ".join(m["part_keys"]))
    add("")
    add("DOCS FOR WHAT THE EXAMPLES USE")
    for fam, used in (("shapes", used_shapes), ("ops", used_shapes), ("material_archetypes", used_arche)):
        for name in sorted(used):
            spec = m[fam].get(name)
            if not spec:
                continue
            params = spec.get("params") or {}
            sig = ", ".join(f"{k}{'*' if 'default' not in v else ''}" + (f"={v['default']}" if v.get("default") not in (None, "") else "")
                            for k, v in params.items()) if isinstance(params, dict) else ""
            add(f"  {name} ({sig}): {spec.get('doc', '')[:220]}")
            if spec.get("example"):
                add(f"      e.g. {spec['example']}")
    if ranked:
        best = ranked[0][1]
        add("")
        add(f"SOURCE OF THE CLOSEST EXAMPLE: assets/{best['name']}/asset.yaml")
        add(best["text"].rstrip())
    add("")
    add("NEXT: ./sw new NAME  ->  write assets/NAME/asset.yaml  ->  ./sw review NAME  ->  open assets/NAME/.build/sheet.png"
        "  ->  edit, review, ./sw snapshot NAME -m ... --critique ...  ->  ./sw export NAME")
    add("Reference when needed: docs/ASSET_FORMAT.md (all keys), docs/VALIDATION.md (codes), docs/RELATIONSHIPS.md (measure).")
    return "\n".join(lines)
