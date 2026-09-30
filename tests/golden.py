"""Golden geometry records (tests/golden.json), shared by test_assets.py and update_golden.py.

Each asset has two records:
  hash  exact geometry hash per platform ("linux-x86_64", "win32-amd64", "darwin-arm64", ...). Any change, however
        small, breaks it, but booleans and simplification round differently across operating systems, so a hash is
        only compared on the platform that recorded it.
  sig   triangle count, bounds, surface area and volume. Compared on every platform within TOLERANCE, which is far
        above float noise and far below any modelling change: it tells OS drift from a real regression.
"""

import json
import platform
import sys
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden.json"
# tris: relative; bounds: metres; area, volume: relative (with a floor for tiny values)
TOLERANCE = {"tris": 0.01, "bounds": 1e-4, "area": 1e-3, "volume": 1e-3}
LEGACY_PLATFORM = "linux-x86_64"  # golden.json before per-platform hashes was recorded in the Linux cloud container


def platform_key() -> str:
    return f"{sys.platform}-{platform.machine().lower()}"


def load(path: Path = GOLDEN) -> dict:
    raw = json.loads(Path(path).read_text())
    return {k: ({"hash": {LEGACY_PLATFORM: v}} if isinstance(v, str) else v) for k, v in raw.items()}


def save(golden: dict):
    rows = [f" {json.dumps(k)}: {json.dumps(golden[k], sort_keys=True)}" for k in sorted(golden)]  # one line per asset
    GOLDEN.write_text("{\n" + ",\n".join(rows) + "\n}\n")


def _rel(a: float, b: float, floor: float) -> float:
    return abs(a - b) / max(abs(b), floor)


def sig_diff(sig: dict, ref: dict) -> list[str]:
    """Signature fields outside tolerance, as readable lines (empty: the same geometry up to float noise)."""
    out = []
    if _rel(sig["tris"], ref["tris"], 1) > TOLERANCE["tris"]:
        out.append(f"triangles {ref['tris']} -> {sig['tris']}")
    worst = max(abs(a - b) for ra, rb in zip(sig["bounds"], ref["bounds"]) for a, b in zip(ra, rb))
    if worst > TOLERANCE["bounds"]:
        out.append(f"bounds {ref['bounds']} -> {sig['bounds']} (max {worst * 1000:.3f} mm)")
    if _rel(sig["area"], ref["area"], 1e-4) > TOLERANCE["area"]:
        out.append(f"area {ref['area']:.6f} -> {sig['area']:.6f} m2")
    if _rel(sig["volume"], ref["volume"], 1e-6) > TOLERANCE["volume"]:
        out.append(f"volume {ref['volume']:.7f} -> {sig['volume']:.7f} m3")
    return out


def record(entry: dict | None, h: str, sig: dict, plat: str) -> tuple[dict, str]:
    """New golden entry for this platform's build, and what happened: unchanged | platform-added | changed | new."""
    if entry is None:
        return {"hash": {plat: h}, "sig": sig}, "new"
    hashes = entry.get("hash", {})
    if hashes.get(plat) == h and "sig" in entry:
        return entry, "unchanged"
    same_geometry = hashes.get(plat) == h if plat in hashes else ("sig" not in entry or not sig_diff(sig, entry["sig"]))
    if same_geometry:  # another OS's rounding of the same geometry: keep every hash, add this one
        return {"hash": {**hashes, plat: h}, "sig": entry.get("sig", sig)}, "platform-added"
    return {"hash": {plat: h}, "sig": sig}, "changed"  # other platforms' hashes are stale until re-recorded there


def merge(golden: dict, other: dict) -> list[str]:
    """Take platform hashes from another golden file (e.g. a CI artifact from another OS) where its signature agrees
    with ours; returns the assets that gained a hash. Disagreeing assets are left alone: that is a real difference."""
    gained = []
    for name, theirs in other.items():
        ours = golden.get(name)
        if not ours or "sig" not in theirs or sig_diff(theirs["sig"], ours["sig"]):
            continue
        new = {p: h for p, h in theirs["hash"].items() if p not in ours["hash"]}
        if new:
            ours["hash"].update(new)
            gained.append(name)
    return gained
