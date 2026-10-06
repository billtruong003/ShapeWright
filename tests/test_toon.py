"""Phase 25b: toon showcase renders (cel shading + continuous post-process outlines)."""

import numpy as np
import pytest

from shapewright.assemble import ROOT, build
from shapewright.render.views import TOON_INK, render
from shapewright.surface import build_surface

BG = np.array([236, 234, 230])


@pytest.mark.parametrize("name", ["crate", "chibi_fox"])
def test_toon_outline_closes_around_the_silhouette(name):
    a = build(ROOT / "assets" / name)
    s = build_surface(a)
    im = np.asarray(render(a, s, "front_right", "toon", 240, annotate=False)).astype(int)
    ink = np.abs(im - TOON_INK * 255).max(-1) < 60
    shape = np.asarray(render(a, s, "front_right", "silhouette", 240, annotate=False)).max(-1) < 128  # the form, whatever its colours
    border = shape & ~(np.roll(shape, 1, 0) & np.roll(shape, -1, 0) & np.roll(shape, 1, 1) & np.roll(shape, -1, 1))
    assert border.sum() > 100
    near = ink.copy()
    for _ in range(2):  # the image edge is anti-aliased: ink within 2 px of every border pixel
        near = near | np.roll(near, 1, 0) | np.roll(near, -1, 0) | np.roll(near, 1, 1) | np.roll(near, -1, 1)
    assert near[border].mean() > 0.97  # the silhouette is inked all round (no gaps at hard corners)


def test_toon_has_flat_bands_not_gradients():
    a = build(ROOT / "assets" / "crate")
    im = np.asarray(render(a, build_surface(a), "front", "toon", 200, annotate=False)).reshape(-1, 3)
    body = im[np.abs(im.astype(int) - BG).max(-1) > 12]
    colours = np.unique((body // 8), axis=0)
    shaded = np.asarray(render(a, build_surface(a), "front", "material", 200, annotate=False)).reshape(-1, 3)
    shaded_body = shaded[np.abs(shaded.astype(int) - BG).max(-1) > 12]
    assert len(colours) < len(np.unique(shaded_body // 8, axis=0))  # fewer tones than smooth shading
