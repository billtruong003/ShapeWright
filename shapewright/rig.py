"""Native rigging (Phase 24, track G): a skeleton from a template, bone-heat weights, poses.

    rig:
      template: biped                      # biped | quadruped
      parts: [body]                        # skinned parts (default: every part)
      joints:                              # rest positions in metres (expressions allowed); `_l` mirrors to `_r`
        hips: [0, 0.3, 0]
        upper_arm_l: [0.14, 0.47, 0]
        tail_1: {at: [0, 0.25, -0.12], parent: hips}     # joints the template does not have name their parent

Template joints that are not given are fitted from the skinned parts' bounds (the template's default fractions),
so `template: biped` alone gives a usable skeleton for a standing figure; giving the joints from the model's own
items is better. Bones are the segments from each joint to its children (a joint without children gets a short
tip along its parent's direction); a vertex is weighted by bone heat (backend.bone_heat), at most 4 joints,
normalised. Rest frames are axis-aligned (no rest rotations): a pose rotates joints about their own position.
"""

from __future__ import annotations

import numpy as np

from . import backend
from .mesh import rotation_matrix

# name, parent, default (x as a fraction of the half-width, y as a fraction of the height, z as a fraction of the half-depth)
TEMPLATES = {
    "biped": [
        ("hips", None, (0, 0.30, 0)),
        ("spine", "hips", (0, 0.44, 0)),
        ("neck", "spine", (0, 0.56, 0)),
        ("head", "neck", (0, 0.70, 0)),
        ("upper_arm_l", "spine", (0.45, 0.50, 0)),
        ("lower_arm_l", "upper_arm_l", (0.65, 0.38, 0)),
        ("hand_l", "lower_arm_l", (0.80, 0.30, 0)),
        ("upper_leg_l", "hips", (0.30, 0.26, 0)),
        ("lower_leg_l", "upper_leg_l", (0.32, 0.13, 0)),
        ("foot_l", "lower_leg_l", (0.33, 0.03, 0.3)),
    ],
    "quadruped": [
        ("hips", None, (0, 0.55, -0.5)),
        ("spine", "hips", (0, 0.58, 0)),
        ("chest", "spine", (0, 0.58, 0.45)),
        ("neck", "chest", (0, 0.72, 0.65)),
        ("head", "neck", (0, 0.85, 0.85)),
        ("front_leg_l", "chest", (0.5, 0.45, 0.45)),
        ("front_shin_l", "front_leg_l", (0.5, 0.2, 0.45)),
        ("front_foot_l", "front_shin_l", (0.5, 0.03, 0.5)),
        ("back_leg_l", "hips", (0.5, 0.45, -0.5)),
        ("back_shin_l", "back_leg_l", (0.5, 0.2, -0.5)),
        ("back_foot_l", "back_shin_l", (0.5, 0.03, -0.45)),
    ],
}
TIP = 0.6  # a leaf joint's bone reaches this fraction of its parent bone's length past the joint

POSES = {  # joint -> euler degrees about the joint, in the rest (world-aligned) frame; _l mirrored to _r (y, z negated)
    "rest": {},
    "a_pose": {"upper_arm_l": [0, 0, -30]},
    "wave": {"upper_arm_r": [0, 0, -95], "lower_arm_r": [0, 0, -50]},
    "sit": {"upper_leg_l": [-85, 0, 0], "lower_leg_l": [85, 0, 0]},
    "walk": {"upper_leg_l": [-30, 0, 0], "upper_leg_r": [25, 0, 0], "lower_leg_r": [30, 0, 0],
             "upper_arm_l": [25, 0, 0], "upper_arm_r": [-25, 0, 0]},
    "look": {"head": [10, 30, 0], "neck": [0, 10, 0]},
}


class Rig:
    def __init__(self, names: list[str], parents: list[int], rest: np.ndarray, parts: list[str]):
        self.names, self.parents, self.rest, self.parts = names, parents, rest, parts
        self.weights: dict[str, np.ndarray] = {}  # part name -> (n_vertices, joints) normalised, top 4
        self.raw_max: dict[str, np.ndarray] = {}  # part name -> strongest raw weight per vertex (before normalising)
        self.rest_V: dict[str, np.ndarray] = {}  # part name -> the vertices the weights belong to

    def index(self, name: str) -> int:
        return self.names.index(name)

    def children(self, j: int) -> list[int]:
        return [k for k, p in enumerate(self.parents) if p == j]

    def segments(self):
        A, B, owner = [], [], []
        for j in range(len(self.names)):
            kids = self.children(j)
            for k in kids:
                A.append(self.rest[j])
                B.append(self.rest[k])
                owner.append(j)
            if not kids:
                p = self.parents[j]
                d = self.rest[j] - (self.rest[p] if p >= 0 else self.rest[j] - np.array([0, 0.05, 0]))
                A.append(self.rest[j])
                B.append(self.rest[j] + TIP * d)
                owner.append(j)
        return np.array(A), np.array(B), np.array(owner)


def _mirror_name(n: str) -> str | None:
    return n[:-2] + "_r" if n.endswith("_l") else None


def build_rig(asset) -> Rig | None:
    """The asset's rig (cached), or None. Raises ValueError for a malformed `rig:` block."""
    cache = asset.__dict__
    if "_rig" in cache:
        return cache["_rig"]
    raw = (asset.source or {}).get("rig")
    if not raw:
        cache["_rig"] = None
        return None
    from . import source as S

    if not isinstance(raw, dict):
        raise ValueError("rig: expected {template, parts, joints}")
    unknown = set(raw) - {"template", "parts", "joints", "doc"}
    if unknown:
        raise ValueError(f"rig: unknown key '{sorted(unknown)[0]}' (template, parts, joints)")
    tname = raw.get("template", "biped")
    if tname not in TEMPLATES:
        raise ValueError(f"rig.template: one of {', '.join(TEMPLATES)}")
    part_names = raw.get("parts") or [p.base for p in asset.parts]
    parts = [p for p in asset.parts if p.base in part_names or p.name in part_names]
    if not parts:
        raise ValueError(f"rig.parts: no part named {part_names}")
    V = np.concatenate([p.mesh.V for p in parts])
    lo, hi = V.min(0), V.max(0)
    c, half = (lo + hi) / 2, (hi - lo) / 2

    template = []
    for name, parent, f in TEMPLATES[tname]:
        template.append((name, parent, f))
        m = _mirror_name(name)
        if m:
            template.append((m, _mirror_name(parent) or parent, (-f[0], f[1], f[2])))
    names = [t[0] for t in template]
    parent_of = {t[0]: t[1] for t in template}
    pos = {t[0]: np.array([c[0] + t[2][0] * half[0], lo[1] + t[2][1] * (hi[1] - lo[1]), c[2] + t[2][2] * half[2]]) for t in template}
    ctx = S.Ctx()
    given = dict(raw.get("joints") or {})
    for name, val in list(given.items()):  # mirror _l -> _r unless given
        m = _mirror_name(str(name))
        if m and m not in given:
            if isinstance(val, dict):
                given[m] = {**val, "mirror_of": name}
            else:
                given[m] = {"at": val, "mirror_of": name}
    for name, val in given.items():
        at, parent, mirror = (val.get("at"), val.get("parent"), val.get("mirror_of")) if isinstance(val, dict) else (val, None, None)
        v = S.vec(at, 3, asset.env, f"rig.joints.{name}", ctx)
        if v is None:
            raise ValueError(f"rig.joints.{name}: expected [x, y, z]")
        v = np.asarray(v, dtype=np.float64)
        if mirror:
            v = v * np.array([-1.0, 1.0, 1.0])
            if parent is not None:
                parent = _mirror_name(parent) or parent
        if name not in parent_of:
            if parent is None:
                raise ValueError(f"rig.joints.{name}: not in the {tname} template; give {{at: [x, y, z], parent: JOINT}}")
            names.append(name)
        if parent is not None:
            parent_of[name] = parent
        pos[name] = v
    for n in names:
        p = parent_of[n]
        if p is not None and p not in parent_of:
            raise ValueError(f"rig.joints.{n}: parent '{p}' is not a joint")
    roots = [n for n in names if parent_of[n] is None]
    if len(roots) != 1:
        raise ValueError(f"rig: exactly one root joint (found {roots})")
    order, seen = [], set()  # parents before children (glTF needs no order, poses do)

    def visit(n):
        if n in seen:
            return
        p = parent_of[n]
        if p is not None:
            visit(p)
        seen.add(n)
        order.append(n)
    for n in names:
        visit(n)
    rig = Rig(order, [order.index(parent_of[n]) if parent_of[n] else -1 for n in order], np.array([pos[n] for n in order]),
              [p.name for p in parts])
    A, B, owner = rig.segments()
    for p in parts:
        W = backend.bone_heat(p.mesh.V, p.mesh.F, A, B, owner, len(order))
        rig.raw_max[p.name] = W.max(1)
        rig.rest_V[p.name] = p.mesh.V.copy()
        top = np.argsort(-W, axis=1)[:, :4]
        keep = np.zeros_like(W)
        np.put_along_axis(keep, top, np.take_along_axis(W, top, 1), 1)
        s = keep.sum(1, keepdims=True)
        nearest = owner[backend.segment_distances(p.mesh.V, A, B).argmin(1)]
        fallback = np.eye(len(order))[nearest]  # a vertex the heat did not reach takes its nearest bone
        rig.weights[p.name] = np.where(s > 1e-9, keep / np.maximum(s, 1e-12), fallback)
    cache["_rig"] = rig
    return rig


def _side(d: dict) -> dict:
    """Pose with _l entries mirrored to _r (rotations about y and z negate under the x mirror)."""
    out = dict(d)
    for k, v in d.items():
        m = _mirror_name(k)
        if m and m not in d:
            out[m] = [v[0], -v[1], -v[2]]
    return out


def joint_matrices(rig: Rig, pose: dict, offset=None) -> np.ndarray:
    """(joints, 4, 4) skinning matrices G_j(pose) @ inverse(G_j(rest)); offset moves the root joint (a bob)."""
    pose = _side(pose)
    G = np.zeros((len(rig.names), 4, 4))
    for j, n in enumerate(rig.names):
        p = rig.parents[j]
        T = np.eye(4)
        T[:3, 3] = rig.rest[j] - (rig.rest[p] if p >= 0 else 0) + (np.asarray(offset) if p < 0 and offset is not None else 0)
        local = T @ rotation_matrix(pose.get(n, [0, 0, 0]))
        G[j] = (G[p] if p >= 0 else np.eye(4)) @ local
    inv_rest = np.tile(np.eye(4), (len(rig.names), 1, 1))
    inv_rest[:, :3, 3] = -rig.rest
    return G @ inv_rest


def posed(asset, rig: Rig, pose: dict, offset=None):
    """A copy of the asset with the skinned parts deformed into `pose` (linear blend skinning)."""
    import dataclasses

    S = joint_matrices(rig, pose, offset)
    parts = []
    for p in asset.parts:
        if p.name not in rig.weights:
            parts.append(p)
            continue
        W = rig.weights[p.name]
        Vh = np.c_[p.mesh.V, np.ones(len(p.mesh.V))]
        M = np.einsum("nj,jab->nab", W, S)
        V = np.einsum("nab,nb->na", M, Vh)[:, :3]
        parts.append(dataclasses.replace(p, mesh=p.mesh.with_positions(V)))
    return dataclasses.replace(asset, parts=parts)


def volume_kept(asset, rig: Rig, pose: dict) -> float:
    """Volume of the skinned parts in `pose` over their rest volume (candy-wrapper collapse shows as a loss)."""
    a = posed(asset, rig, pose)
    rest = sum(abs(p.mesh.volume()) for p in asset.parts if p.name in rig.weights)
    now = sum(abs(p.mesh.volume()) for p in a.parts if p.name in rig.weights)
    return now / max(rest, 1e-12)


def surface_weights(rig: Rig, part, positions: np.ndarray) -> np.ndarray:
    """Weights for any vertices of this part (the surface's, split at UV seams; an LOD's), looked up by position
    in the rest mesh the weights were solved on, nearest vertex where there is no exact match."""
    W, V = rig.weights[part.name], rig.rest_V[part.name]
    key = {tuple(k): i for i, k in enumerate(np.round(V.astype(np.float32).astype(np.float64), 5))}
    P = np.asarray(positions, dtype=np.float64)
    idx = np.array([key.get(tuple(k), -1) for k in np.round(P, 5)])
    miss = np.flatnonzero(idx < 0)
    for chunk in np.array_split(miss, max(1, len(miss) // 2000)) if len(miss) else []:
        idx[chunk] = np.linalg.norm(P[chunk][:, None, :] - V[None], axis=-1).argmin(1)
    return W[idx]


def top4(W: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(joint indices uint16 (n,4), weights float32 (n,4) summing to 1): glTF JOINTS_0 / WEIGHTS_0."""
    idx = np.argsort(-W, axis=1)[:, :4]
    w = np.take_along_axis(W, idx, 1)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-12)
    idx = np.where(w > 0, idx, 0)
    return idx.astype(np.uint16), w.astype(np.float32)


def posed_view(asset, surface, rig: Rig, pose: dict, offset=None):
    """(asset, surface) deformed into `pose`, sharing the rest surface's UVs and textures (for renders)."""
    import copy
    import dataclasses

    a = posed(asset, rig, pose, offset)
    S = joint_matrices(rig, pose, offset)
    s = copy.copy(surface)
    s.parts = dict(surface.parts)
    for p in asset.parts:
        if p.name not in rig.weights:
            continue
        sp = surface.parts[p.name]
        W = surface_weights(rig, p, sp.positions)
        M = np.einsum("nj,jab->nab", W, S)
        P = np.einsum("nab,nb->na", M, np.c_[sp.positions, np.ones(len(sp.positions))])[:, :3]
        s.parts[p.name] = dataclasses.replace(sp, positions=P.astype(np.float32))
    return a, s


# ---------------------------------------------------------------- procedural clips (G5)

CLIP_DEFAULTS = {
    "idle": {"seconds": 2.0, "bob": 0.012, "breathe": 3.0, "sway": 8.0},
    "walk": {"seconds": 1.0, "stride": 30.0, "knee": 35.0, "arm_swing": 25.0, "bounce": 0.015, "sway": 10.0},
    "wave": {"seconds": 1.2, "raise": 95.0, "swing": 25.0},
}
KEYS = 16  # keyframes per clip (the last repeats the first: clips loop)


def clip_settings(asset) -> dict:
    """{clip name: params} from rig.clips (default: idle, walk, wave)."""
    raw = (asset.source or {}).get("rig") or {}
    clips = raw.get("clips")
    if clips is None:
        clips = {k: {} for k in CLIP_DEFAULTS}
    if not isinstance(clips, dict):
        raise ValueError("rig.clips: expected {idle: {...}, walk: {...}, wave: {...}}")
    out = {}
    for name, params in clips.items():
        if name not in CLIP_DEFAULTS:
            raise ValueError(f"rig.clips.{name}: one of {', '.join(CLIP_DEFAULTS)}")
        params = params or {}
        bad = set(params) - set(CLIP_DEFAULTS[name])
        if bad:
            raise ValueError(f"rig.clips.{name}: no '{sorted(bad)[0]}' (params: {', '.join(CLIP_DEFAULTS[name])})")
        out[name] = {**CLIP_DEFAULTS[name], **{k: float(v) for k, v in params.items()}}
    return out


def clip_pose(rig: Rig, name: str, p: dict, t: float) -> tuple[dict, np.ndarray]:
    """(pose: joint -> euler degrees, root offset) at time t seconds."""
    ph = 2 * np.pi * (t / p["seconds"])
    s, c = np.sin(ph), np.cos(ph)
    has = set(rig.names)
    pose: dict = {}
    off = np.zeros(3)

    def put(j, rot):
        if j in has:
            pose[j] = [float(x) for x in rot]

    tail = [n for n in rig.names if n.startswith("tail")]
    if name == "idle":
        off[1] = p["bob"] * s
        put("spine", [p["breathe"] * s, 0, 0])
        put("head", [-0.5 * p["breathe"] * s, 0, 0])
        for k, j in enumerate(tail):
            put(j, [0, p["sway"] * np.sin(ph - 0.6 * k), 0])
    elif name == "walk":
        off[1] = p["bounce"] * abs(c)
        for side, sign in (("l", 1), ("r", -1)):
            put(f"upper_leg_{side}", [-sign * p["stride"] * s, 0, 0])
            put(f"lower_leg_{side}", [p["knee"] * max(0.0, sign * c), 0, 0])
            put(f"upper_arm_{side}", [sign * p["arm_swing"] * s, 0, 0])
            put(f"front_leg_{side}", [-sign * p["stride"] * s, 0, 0])  # quadruped: diagonal pairs
            put(f"back_leg_{side}", [sign * p["stride"] * s, 0, 0])
            put(f"front_shin_{side}", [p["knee"] * max(0.0, sign * c), 0, 0])
            put(f"back_shin_{side}", [-p["knee"] * max(0.0, -sign * c), 0, 0])
        for k, j in enumerate(tail):
            put(j, [0, p["sway"] * np.sin(ph - 0.6 * k), 0])
    else:  # wave
        put("upper_arm_r", [0, 0, -p["raise"]])
        put("lower_arm_r", [0, 0, -40 + p["swing"] * np.sin(2 * ph)])
        put("head", [0, -8, 4])
    return pose, off


def clip_keys(rig: Rig, name: str, p: dict):
    """(times (k,), {joint index: (k, 3) euler degrees}, root offsets (k, 3))."""
    times = np.linspace(0.0, p["seconds"], KEYS)
    rots = {j: np.zeros((KEYS, 3)) for j in range(len(rig.names))}
    offs = np.zeros((KEYS, 3))
    for k, t in enumerate(times):
        pose, off = clip_pose(rig, name, p, t)
        offs[k] = off
        for jn, r in pose.items():
            rots[rig.index(jn)][k] = r
    used = {j: r for j, r in rots.items() if np.abs(r).max() > 1e-9}
    return times, used, offs


# ---------------------------------------------------------------- rigid clips (doors, lids, wheels)

LOOPS = ("once", "pingpong", "cycle")


def rigid_clips(asset) -> list[dict]:
    """Top-level `animations: [{name, part, rotate: [x, y, z], seconds, loop}]`: a part (or hinge group) turning
    about its own pivot. once: 0 -> rotate; pingpong: 0 -> rotate -> 0; cycle: a full turn of `rotate` per loop
    (wheels, fans). Raises ValueError for a malformed list."""
    raw = (asset.source or {}).get("animations")
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("animations: expected a list of {name, part, rotate, seconds, loop}")
    out = []
    for i, a in enumerate(raw):
        if not isinstance(a, dict) or not {"name", "part", "rotate"} <= set(a):
            raise ValueError(f"animations[{i}]: needs name, part and rotate [x, y, z] degrees")
        bad = set(a) - {"name", "part", "rotate", "seconds", "loop", "doc"}
        if bad:
            raise ValueError(f"animations[{i}]: no '{sorted(bad)[0]}' (name, part, rotate, seconds, loop)")
        parts = asset.parts_named(str(a["part"]))
        if not parts:
            from .registry import suggest

            raise ValueError(f"animations[{i}].part: no part '{a['part']}'.{suggest(str(a['part']), {p.base for p in asset.parts})}")
        loop = a.get("loop", "once")
        if loop not in LOOPS:
            raise ValueError(f"animations[{i}].loop: one of {', '.join(LOOPS)}")
        rot = np.asarray(a["rotate"], dtype=np.float64)
        if rot.shape != (3,):
            raise ValueError(f"animations[{i}].rotate: [x, y, z] degrees")
        out.append({"name": str(a["name"]), "parts": [p.name for p in parts], "rotate": rot,
                    "seconds": float(a.get("seconds", 1.0)), "loop": loop})
    return out


def rigid_keys(clip: dict) -> tuple[np.ndarray, np.ndarray]:
    """(times, euler degrees per key): short enough steps that slerp follows the intended direction."""
    T, a = clip["seconds"], clip["rotate"]
    steps = max(2, int(np.ceil(np.abs(a).max() / 60.0)) + 1)  # <= 60 degrees between keys
    f = np.linspace(0.0, 1.0, steps)
    if clip["loop"] == "pingpong":
        f = np.concatenate([f, f[-2::-1]])
    times = np.linspace(0.0, T, len(f))
    return times, f[:, None] * a[None, :]
