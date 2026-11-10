"""The lab's two painted surfaces, drawn as textures.

    python textures.py            -> data/plaster.png, data/rock.png

plaster.png: the walls. Old lime plaster, pale and a little warm, mottled, with
dark grime running down from the ceiling in uneven streaks (heaviest near the
top, as in 1995), a dirty band near the floor and a few hairline cracks. It
tiles across (16 units wide) and runs once from floor to ceiling (32 units).

rock.png: the ceiling, rough brown stone: irregular slabs, each its own shade,
with dark seams and pitting. It tiles both ways (12 units square).

The colors sit in the dining room's palette: the plaster near its curtain white
dulled toward the stone gray, the rock near its timber and stone."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))


def noise(shape, cell, rng, wrap_x=True):
    """smooth value noise (bicubic-upsampled random grid), tiling across"""
    h, w = shape
    gh, gw = h // cell, w // cell
    g = rng.random((gh, gw))
    g = np.concatenate([g[:, -2:], g, g[:, :2]], 1)   # wrap both ways so the result tiles
    g = np.concatenate([g[-2:], g, g[:2]], 0)
    im = Image.fromarray((g * 255).astype(np.uint8)).resize(((gw + 4) * cell, (gh + 4) * cell), Image.BICUBIC)
    a = np.asarray(im).astype(float)[2 * cell:2 * cell + h, 2 * cell:2 * cell + w] / 255
    return a


def plaster(out, W=1024, H=512):
    rng = np.random.default_rng(7)
    base = np.array([168, 160, 146], float)          # pale, warm lime plaster
    grime = np.array([58, 52, 46], float)
    m = 0.55 * noise((H, W), 64, rng) + 0.3 * noise((H, W), 16, rng) + 0.15 * noise((H, W), 4, rng)
    img = base[None, None] * (0.86 + 0.24 * m[..., None])
    # streaks: grime running down from the ceiling, uneven, heaviest at the top
    dark = np.zeros((H, W))
    y = np.arange(H)[:, None] / H                    # 0 at the top of the wall
    for _ in range(60):
        x0 = rng.uniform(0, W); wd = rng.uniform(3, 22); ln = rng.uniform(0.1, 0.7); s = rng.uniform(0.2, 0.7)
        xs = (np.arange(W)[None] - x0 + W / 2) % W - W / 2       # distance across, wrapping
        wob = 3 * np.sin(y * rng.uniform(8, 20) + rng.uniform(0, 6))
        across = np.exp(-((xs + wob) / wd) ** 2)
        down = np.clip(1 - y / ln, 0, 1) ** 1.5
        dark = np.maximum(dark, s * across * down)
    dark = np.clip(dark + 0.25 * np.clip(1 - y / 0.12, 0, 1), 0, 1)                 # under the ceiling
    dark *= 0.75 + 0.5 * noise((H, W), 8, rng)
    img = img * (1 - dark[..., None]) + grime[None, None] * dark[..., None]
    floor_band = np.clip((y - 0.86) / 0.14, 0, 1) ** 2                             # dirt near the floor
    img = img * (1 - 0.35 * floor_band[..., None])
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for _ in range(9):                               # hairline cracks
        x, yy = rng.uniform(0, W), rng.uniform(0.2, 0.8) * H
        pts = [(x, yy)]
        for k in range(rng.integers(5, 12)):
            x += rng.uniform(-14, 14); yy += rng.uniform(4, 16); pts.append((x % W, yy))
        for p, q in zip(pts[:-1], pts[1:]):
            if abs(p[0] - q[0]) < W / 2: d.line([p, q], fill=(122, 115, 104), width=1)
    im.save(out); print('plaster', im.size, '->', out)


def rock(out, S=512, n=70):
    rng = np.random.default_rng(11)
    pts = rng.random((n, 2)) * S
    tiles = np.concatenate([pts + [dx * S, dy * S] for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    yy, xx = np.mgrid[0:S, 0:S]
    P = np.stack([xx, yy], -1).reshape(-1, 1, 2).astype(float)
    best = np.full(S * S, 1e9); second = np.full(S * S, 1e9); idx = np.zeros(S * S, int)
    for k0 in range(0, len(tiles), 60):              # nearest and second-nearest seed, in chunks
        d = np.linalg.norm(P - tiles[None, k0:k0 + 60], axis=-1)
        for j in range(d.shape[1]):
            dj = d[:, j]
            closer = dj < best
            second = np.where(closer, best, np.minimum(second, dj)); idx = np.where(closer, k0 + j, idx); best = np.where(closer, dj, best)
    edge = (second - best).reshape(S, S)
    shade = (0.78 + 0.4 * rng.random(n))[idx % n].reshape(S, S)
    base = np.array([104, 80, 60], float)            # brown stone, between the timber and the stone floor
    m = 0.6 * noise((S, S), 32, rng) + 0.4 * noise((S, S), 6, rng)
    img = base[None, None] * shade[..., None] * (0.8 + 0.4 * m[..., None])
    seam = np.clip(1 - edge / 7, 0, 1)
    img *= (1 - 0.6 * seam)[..., None]
    pits = noise((S, S), 3, rng) > 0.86
    img[pits] *= 0.7
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.SMOOTH)
    im.save(out); print('rock', im.size, '->', out)


if __name__ == '__main__':
    os.makedirs(os.path.join(HERE, 'data'), exist_ok=True)
    plaster(os.path.join(HERE, 'data', 'plaster.png'))
    rock(os.path.join(HERE, 'data', 'rock.png'))
