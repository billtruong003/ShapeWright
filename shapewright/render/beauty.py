"""Presentation render (`mode: beauty`): the inspection renderer's rasterizer with presentation lighting.

Three-point lighting (key, fill, rim) in linear space, a shadow map for the key light, screen-space ambient
occlusion (times the baked ORM occlusion where an atlas exists), a contact shadow under the asset on a shadow-catcher
ground, ACES tone mapping and 2x2 supersampling. No GPU, no randomness: the same asset gives the same bytes.
The inspection modes (views.render) are untouched; this is for README, docs and portfolio images.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from ..assemble import Asset
from ..surface import Surface
from .raster import Buffers, fragments
from .views import VIEWS, Camera, View, _dir, _font, _surface_samples

SKY = np.array([0.80, 0.84, 0.92])  # linear ambient from above
GROUND_BOUNCE = np.array([0.36, 0.33, 0.29])  # linear ambient from below
BG_TOP = np.array([0.955, 0.952, 0.945])  # sRGB background gradient (top -> horizon)
BG_LOW = np.array([0.835, 0.828, 0.812])
KEY, FILL, RIM, AMBIENT = 1.75, 0.4, 0.7, 0.5
EXPOSURE = 0.82
SHADOW_RES = 1536
AO_DIRS = 8


def _raster(screen: np.ndarray, key: np.ndarray, w: int, h: int, normals=None, front=None, extra=None) -> Buffers:
    """Depth-resolved raster like raster.rasterize (largest key wins, ties to the lower triangle index), resolved
    with two scatter reductions instead of a 3-key sort: 3-5x faster on the heavy overdraw of shadow maps."""
    buf = Buffers(w, h, 0 if extra is None else extra.shape[2])
    t, px, py, b0, b1, b2 = fragments(screen, w, h)
    if len(t):
        k = b0 * key[t, 0] + b1 * key[t, 1] + b2 * key[t, 2]
        pix = py * w + px
        depth = np.full(w * h, -np.inf)
        np.maximum.at(depth, pix, k)
        win = k == depth[pix]
        best = np.full(w * h, np.iinfo(np.int64).max)
        np.minimum.at(best, pix[win], t[win])
        sel = np.flatnonzero(win & (t == best[pix]))
        _, first = np.unique(pix[sel], return_index=True)
        sel = sel[first]
        t, px, py, b0, b1, b2, k = t[sel], px[sel], py[sel], b0[sel], b1[sel], b2[sel], k[sel]
        buf.depth[py, px] = k
        buf.tri[py, px] = t
        if normals is not None:
            buf.normal[py, px] = b0[:, None] * normals[t, 0] + b1[:, None] * normals[t, 1] + b2[:, None] * normals[t, 2]
            buf.front[py, px] = front[t]
        if extra is not None:
            buf.extra[py, px] = b0[:, None] * extra[t, 0] + b1[:, None] * extra[t, 1] + b2[:, None] * extra[t, 2]
    if normals is not None:
        length = np.linalg.norm(buf.normal, axis=2, keepdims=True)
        buf.normal = np.where(length > 1e-12, buf.normal / np.maximum(length, 1e-12), 0)
    return buf


def view_at(azimuth: float, elevation: float = 22.0) -> View:
    """A perspective view from any azimuth (degrees, 0 = front, 90 = right): turntables and presentation sheets."""
    return View(f"az{azimuth:g}", _dir(azimuth, elevation), (0, 1, 0), False, f"perspective, azimuth {azimuth:g}")


def _aces(x):
    return np.clip(x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


def _blur(img: np.ndarray, radius: int) -> np.ndarray:
    """Separable Gaussian blur with a fixed kernel (deterministic)."""
    if radius < 1:
        return img
    x = np.arange(-radius, radius + 1)
    k = np.exp(-(x / (radius / 2.0)) ** 2 / 2)
    k /= k.sum()
    out = img
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (radius, radius)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            sl = [slice(None)] * out.ndim
            sl[axis] = slice(i, i + out.shape[axis])
            acc += w * p[tuple(sl)]
        out = acc
    return out


class _LightMap:
    """Orthographic depth map from a directional light (larger key = closer to the light)."""

    def __init__(self, T: np.ndarray, L: np.ndarray, res: int):
        self.f = -L / np.linalg.norm(L)  # light travels along f
        helper = np.array([0.0, 0.0, 1.0]) if abs(self.f[1]) > 0.9 else np.array([0.0, 1.0, 0.0])
        self.r = np.cross(self.f, helper)
        self.r /= np.linalg.norm(self.r)
        self.u = np.cross(self.r, self.f)
        P = T.reshape(-1, 3)
        x, y = P @ self.r, P @ self.u
        pad = 0.02 * max(np.ptp(x), np.ptp(y), 1e-3)
        self.x0, self.y0 = x.min() - pad, y.min() - pad
        self.scale = (res - 1) / max(np.ptp(x) + 2 * pad, np.ptp(y) + 2 * pad)
        self.res = res
        scr, key = self._project(T)
        self.depth = _raster(scr, key, res, res).depth
        self.texel = 1.0 / self.scale

    def _project(self, P):
        sx = (P @ self.r - self.x0) * self.scale
        sy = (P @ self.u - self.y0) * self.scale
        return np.stack([sx, sy], -1), -(P @ self.f)

    def lit(self, P: np.ndarray, bias: float) -> np.ndarray:
        """Fraction of a 3x3 PCF footprint that sees the light, per point (n,3)."""
        scr, key = self._project(P)
        ix = np.floor(scr[:, 0]).astype(np.int64)
        iy = np.floor(scr[:, 1]).astype(np.int64)
        total = np.zeros(len(P))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                jx, jy = ix + dx, iy + dy
                inside = (jx >= 0) & (jx < self.res) & (jy >= 0) & (jy < self.res)
                occ = np.full(len(P), -np.inf)
                occ[inside] = self.depth[jy[inside], jx[inside]]
                total += (occ <= key + bias).astype(float)
        return total / 9.0


def _ssao(P: np.ndarray, N: np.ndarray, hit: np.ndarray, radius_px: int, radius_world: float) -> np.ndarray:
    """Ambient occlusion from the position buffer: neighbours above a pixel's tangent plane occlude it."""
    H, W = hit.shape
    occ = np.zeros((H, W), np.float32)
    cnt = np.zeros((H, W), np.float32)
    Pf, Nf = P.astype(np.float32), N.astype(np.float32)
    for k in range(AO_DIRS):
        a = 2 * math.pi * (k + 0.5) / AO_DIRS
        for r in (radius_px * 0.4, radius_px):
            dx, dy = int(round(math.cos(a) * r)), int(round(math.sin(a) * r))
            if dx == 0 and dy == 0:
                continue
            ys, yd = (slice(dy, H), slice(0, H - dy)) if dy >= 0 else (slice(0, H + dy), slice(-dy, H))
            xs, xd = (slice(dx, W), slice(0, W - dx)) if dx >= 0 else (slice(0, W + dx), slice(-dx, W))
            v = Pf[ys, xs] - Pf[yd, xd]
            d = np.sqrt((v * v).sum(-1)) + 1e-6
            cos = (v * Nf[yd, xd]).sum(-1) / d
            w = 1.0 / (1.0 + (d / radius_world) ** 2)
            ok = hit[ys, xs] & hit[yd, xd]
            occ[yd, xd] += np.where(ok, np.clip(cos - 0.15, 0, 1) * w, 0)
            cnt[yd, xd] += 1
    return 1.0 - np.clip(1.6 * occ / np.maximum(cnt, 1), 0, 0.85)


def render_beauty(asset: Asset, surface: Surface, view: str | View = "front_right", size: int = 512,
                  frame: np.ndarray | None = None, supersample: int = 2, label: str = "") -> Image.Image:
    from ..bake import textures_for

    view = VIEWS[view] if isinstance(view, str) else view
    W = H = size * supersample
    parts = asset.parts
    bounds = frame if frame is not None else np.stack([np.min([p.bounds[0] for p in parts], 0), np.max([p.bounds[1] for p in parts], 0)])
    diag = float(np.linalg.norm(bounds[1] - bounds[0]))
    cam = Camera(view, bounds, W, H, margin=0.16)
    tex = textures_for(asset, surface)

    tris, nrms, fnorm, owner, cuvs = [], [], [], [], []
    for pi, p in enumerate(parts):
        sp = surface.parts[p.name]
        tris.append(sp.positions[sp.indices].astype(np.float64))
        nrms.append(sp.normals[sp.indices].astype(np.float64))
        fnorm.append(p.mesh.face_normals()[0])
        owner.append(np.full(len(sp.indices), pi))
        cuvs.append(sp.corner_uv if sp.corner_uv is not None else np.zeros((len(sp.indices), 3, 2)))
    T, Nc, FN, OWN = (np.concatenate(x) for x in (tris, nrms, fnorm, owner))
    scr, key = cam.project(T)
    front = cam.facing(T.mean(1), FN)
    buf = _raster(scr, key, W, H, Nc, front, np.concatenate([np.concatenate(cuvs), T], axis=2))
    hit = buf.tri >= 0
    n = np.where(buf.front[..., None], buf.normal, -buf.normal)  # two-sided shading for presentation
    P = buf.extra[..., 2:5]

    up = np.array([0.0, 1.0, 0.0])
    key_l = -cam.right * 0.55 + up * 1.0 - cam.fwd * 0.45
    key_l /= np.linalg.norm(key_l)
    fill_l = cam.right * 0.8 + up * 0.25 - cam.fwd * 0.55
    fill_l /= np.linalg.norm(fill_l)
    rim_l = cam.fwd * 0.75 + up * 0.55 - cam.right * 0.2
    rim_l /= np.linalg.norm(rim_l)

    light = _LightMap(T, key_l, int(min(SHADOW_RES, max(512, 0.75 * W))))
    ground_y = float(bounds[0][1])

    # ---- asset pixels
    img = np.zeros((H, W, 3))
    pid = np.where(hit, OWN[np.clip(buf.tri, 0, None)], -1)
    hp = hit
    base, rgh, mtl = _surface_samples(asset, surface, parts, pid[hp], buf.extra[hp][:, :2], tex)
    baked_ao = np.ones(int(hp.sum()))
    if tex is not None:
        uv = buf.extra[hp][:, :2]
        r = tex.resolution
        tx = np.clip((uv[:, 0] * r).astype(int), 0, r - 1) if surface.uv_method != "trim" else (np.floor(uv[:, 0] * r).astype(int) % r)  # trim sheets repeat in U
        ty = np.clip(((1 - uv[:, 1]) * r).astype(int), 0, r - 1)
        atlas = np.array([not surface.parts[parts[i].name].authored for i in pid[hp]])
        baked_ao = np.where(atlas, tex.orm[ty, tx, 0], 1.0)
    nn = n[hp]
    Ph = P[hp]
    shadow = light.lit(Ph + nn * light.texel * 1.5, bias=light.texel * 1.0)
    ao = _ssao(P, n, hit, max(3, int(W * 0.018)), 0.035 * diag)[hp] * baked_ao
    albedo = np.clip(base, 0, 1) ** 2.2
    to_eye = (-cam.fwd[None, :]) if view.ortho else (cam.eye[None, :] - Ph)
    V = to_eye / np.linalg.norm(to_eye, axis=1, keepdims=True)
    ndl = np.clip(nn @ key_l, 0, 1)
    amb = (GROUND_BOUNCE + (SKY - GROUND_BOUNCE) * (0.5 + 0.5 * nn[:, 1:2])) * AMBIENT
    diffuse = albedo * (KEY * ndl[:, None] * shadow[:, None] + FILL * np.clip(nn @ fill_l, 0, 1)[:, None] + amb * ao[:, None])
    half = key_l[None, :] + V
    half /= np.linalg.norm(half, axis=1, keepdims=True)
    gloss = (1 - np.clip(rgh, 0.04, 1)) ** 2
    spec_pow = 2 + 120 * gloss
    f0 = 0.04 * (1 - mtl)[:, None] + albedo * mtl[:, None]
    spec = f0 * (np.clip((nn * half).sum(1), 0, 1) ** spec_pow * (spec_pow + 2) / 8 * ndl * shadow)[:, None] * KEY * 0.25
    rim = RIM * (1 - np.clip((nn * V).sum(1), 0, 1)) ** 3 * np.clip(nn @ rim_l, 0, 1)
    col = diffuse * (1 - 0.7 * mtl)[:, None] + spec + rim[:, None] * (0.35 + 0.65 * albedo)
    img[hp] = _aces(col * EXPOSURE) ** (1 / 2.2)

    # ---- background: gradient + shadow catcher on the ground plane
    ys = (np.arange(H) + 0.5) / H
    grad = BG_TOP[None, :] + (BG_LOW - BG_TOP)[None, :] * np.clip(ys * 1.15, 0, 1)[:, None] ** 1.4
    bg = np.repeat(grad[:, None, :], W, axis=1)
    gx, gy = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    if view.ortho:
        o = cam.target[None, None, :] + (gx - W / 2)[..., None] / cam.scale * cam.right + (H / 2 - gy)[..., None] / cam.scale * cam.up - cam.fwd * diag * 4
        d = np.broadcast_to(cam.fwd, o.shape)
    else:
        d = (gx - W / 2)[..., None] / cam.focal * cam.right + (H / 2 - gy)[..., None] / cam.focal * cam.up + cam.fwd
        d = d / np.linalg.norm(d, axis=2, keepdims=True)
        o = np.broadcast_to(cam.eye, d.shape)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (ground_y - o[..., 1]) / d[..., 1]
    on_ground = (~hit) & (d[..., 1] < -1e-4) & (t > 0)
    darken = np.ones((H, W))
    if on_ground.any():
        G = o[on_ground] + d[on_ground] * t[on_ground][:, None]
        lit = light.lit(G, bias=light.texel * 1.0)
        # contact shadow: a soft top-down footprint of the geometry near the ground
        cres = 256
        lo, hi = bounds[0][[0, 2]], bounds[1][[0, 2]]
        pad = 0.25 * max(hi - lo)
        lo, hi = lo - pad, hi + pad
        cs = (cres - 1) / max(hi - lo)
        fx = (T[..., 0] - lo[0]) * cs
        fz = (T[..., 2] - lo[1]) * cs
        top = _raster(np.stack([fx, fz], -1), -T[..., 1], cres, cres)
        height = np.where(top.tri >= 0, -top.depth - ground_y, np.inf)
        near = np.clip(1 - height / (0.12 * diag + 1e-6), 0, 1)
        contact = _blur(near, max(2, cres // 40))
        jx = np.clip(((G[:, 0] - lo[0]) * cs).astype(int), 0, cres - 1)
        jz = np.clip(((G[:, 2] - lo[1]) * cs).astype(int), 0, cres - 1)
        inside = (G[:, 0] >= lo[0]) & (G[:, 0] <= hi[0]) & (G[:, 2] >= lo[1]) & (G[:, 2] <= hi[1])
        c = np.where(inside, contact[jz, jx], 0.0)
        dist = np.linalg.norm(G[:, [0, 2]] - (bounds[0][[0, 2]] + bounds[1][[0, 2]]) / 2, axis=1)
        fade = np.clip(1.6 - dist / (0.9 * diag + 1e-6), 0, 1)  # the catcher fades out, no visible ground edge
        darken[on_ground] = (1 - 0.42 * (1 - lit) * fade) * (1 - 0.55 * c)
    img[~hit] = bg[~hit] * darken[~hit][:, None]
    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).resize((size, size), Image.LANCZOS)
    if label:
        d = ImageDraw.Draw(out)
        font = _font(max(11, size // 40))
        d.rectangle([4, 4, 12 + d.textlength(label, font=font), 8 + max(11, size // 40) + 4], fill=(246, 245, 242))
        d.text((8, 6), label, fill=(70, 70, 70), font=font)
    return out


def turntable(asset: Asset, surface: Surface, frames: int = 24, size: int = 384, elevation: float = 22.0) -> list[Image.Image]:
    """Beauty frames around the asset, framed once so the asset does not jump between frames."""
    parts = asset.parts
    b = np.stack([np.min([p.bounds[0] for p in parts], 0), np.max([p.bounds[1] for p in parts], 0)])
    c, r = (b[0] + b[1]) / 2, np.linalg.norm(b[1] - b[0]) / 2
    frame = np.stack([c - r, c + r])  # a sphere-sized box: the same framing from every azimuth
    frame[0][1] = b[0][1]
    return [render_beauty(asset, surface, view_at(35 + 360 * i / frames, elevation), size, frame=frame) for i in range(frames)]


def save_turntable(frames: list[Image.Image], out_gif) -> list:
    """GIF always; MP4 too when imageio-ffmpeg is installed (optional). Returns the files written."""
    from pathlib import Path

    out_gif = Path(out_gif)
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=255) for f in frames]
    pal[0].save(out_gif, save_all=True, append_images=pal[1:], duration=80, loop=0, optimize=False)
    written = [out_gif]
    try:
        import imageio.v2 as imageio  # optional
        mp4 = out_gif.with_suffix(".mp4")
        with imageio.get_writer(mp4, fps=12, macro_block_size=1) as w:
            for f in frames:
                w.append_data(np.asarray(f))
        written.append(mp4)
    except Exception:  # noqa: BLE001 - no ffmpeg: the GIF is the deliverable
        pass
    return written


def _detail_parts(asset: Asset, n: int = 4) -> list[str]:
    """The most detailed distinct source parts (most triangles per instance): locks, handles, carvings.
    Large plain boards are what the full views already show."""
    tris: dict[str, int] = {}
    for p in asset.parts:
        tris[p.base] = max(tris.get(p.base, 0), p.mesh.n_tris)
    return [k for k, _ in sorted(tris.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def present_sheet(asset: Asset, surface: Surface, tile: int = 384, details: list[str] | None = None) -> Image.Image:
    """A concept-art style sheet: beauty views, detail close-ups, wireframe and silhouette, palette and counts."""
    from .views import render

    details = details or _detail_parts(asset)
    head, foot = max(28, tile // 10), max(34, tile // 9)
    sheet = Image.new("RGB", (4 * tile, head + 3 * tile + foot), (246, 245, 242))
    d = ImageDraw.Draw(sheet)
    font, small = _font(max(14, tile // 18)), _font(max(11, tile // 28))
    d.text((10, 6), f"{asset.name}  -  {asset.meta.get('description', '')}"[:110], fill=(40, 40, 40), font=font)
    for i, v in enumerate(("front", "right", "back", "front_right")):
        sheet.paste(render_beauty(asset, surface, v, tile, label=v.replace("_", " ")), (i * tile, head))
    for i, name in enumerate(details[:4]):
        ps = asset.parts_named(name)
        b = np.stack([np.min([p.bounds[0] for p in ps], 0), np.max([p.bounds[1] for p in ps], 0)])
        c, r = (b[0] + b[1]) / 2, max(np.max(b[1] - b[0]) / 2 * 1.2, 0.03)
        sheet.paste(render_beauty(asset, surface, "front_right", tile, frame=np.stack([c - r, c + r]), label=f"detail: {name}"),
                    (i * tile, head + tile))
    sheet.paste(render(asset, surface, "front_right", "wire", tile, label="wireframe"), (0, head + 2 * tile))
    sheet.paste(render(asset, surface, "front", "silhouette", tile, label="silhouette"), (tile, head + 2 * tile))
    sheet.paste(render(asset, surface, "back_left", "textured", tile, label="back left"), (2 * tile, head + 2 * tile))
    # palette: each material's base colour, largest first by the area that uses it
    use: dict[str, float] = {}
    for p in asset.parts:
        use[p.material or ""] = use.get(p.material or "", 0.0) + float(p.mesh.area())
    x0, y0 = 3 * tile + 12, head + 2 * tile + 12
    d.text((x0, y0), "palette", fill=(40, 40, 40), font=font)
    for k, (m, _) in enumerate(sorted(use.items(), key=lambda kv: -kv[1])[:8]):
        col = (asset.materials.get(m) or {}).get("base_color") or [0.8, 0.8, 0.8]
        y = y0 + 30 + k * (tile // 9)
        d.rectangle([x0, y, x0 + tile // 4, y + tile // 12], fill=tuple(int(np.clip(c, 0, 1) * 255) for c in col[:3]))
        d.text((x0 + tile // 4 + 8, y), m or "(none)", fill=(50, 50, 50), font=small)
    size = asset.bounds()[1] - asset.bounds()[0]
    d.text((10, head + 3 * tile + 8), f"{asset.n_tris:,} triangles   {len(asset.materials)} materials   {len(asset.parts)} parts   "
           f"{size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m   profile {asset.profile.get('name', '')}", fill=(60, 60, 60), font=font)
    return sheet
