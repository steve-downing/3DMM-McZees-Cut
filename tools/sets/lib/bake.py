"""Bake one texture for an object seen many times (instances x views)."""
import sys, os
import numpy as np
import xatlas
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(__file__))
from fuse import focal

def rasterize(uv, F, size):
    """texel -> (face, barycentrics) for texels whose center falls in a UV triangle"""
    fid = -np.ones((size, size), int); bary = np.zeros((size, size, 3))
    P = uv * size
    for f, (a, b, c) in enumerate(F):
        A, B, C = P[a], P[b], P[c]
        x0 = int(max(0, np.floor(min(A[0], B[0], C[0])))); x1 = int(min(size - 1, np.ceil(max(A[0], B[0], C[0]))))
        y0 = int(max(0, np.floor(min(A[1], B[1], C[1])))); y1 = int(min(size - 1, np.ceil(max(A[1], B[1], C[1]))))
        if x1 < x0 or y1 < y0: continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        v0 = B - A; v1 = C - A; den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12: continue
        px = xs - A[0]; py = ys - A[1]
        l1 = (px * v1[1] - v1[0] * py) / den; l2 = (v0[0] * py - px * v0[1]) / den; l0 = 1 - l1 - l2
        inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        iy, ix = np.nonzero(inside)
        fid[y0 + iy, x0 + ix] = f
        bary[y0 + iy, x0 + ix] = np.stack([l0[inside], l1[inside], l2[inside]], -1)
    return fid, bary

def dilate(tex, mask, n=4):
    from scipy import ndimage
    for _ in range(n):
        grown = ndimage.binary_dilation(mask)
        new = grown & ~mask
        if not new.any(): break
        acc = np.zeros_like(tex); cnt = np.zeros(mask.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                acc += np.roll(np.roll(tex * mask[..., None], dy, 0), dx, 1); cnt += np.roll(np.roll(mask, dy, 0), dx, 1)
        tex = np.where(new[..., None], acc / np.maximum(cnt, 1)[..., None], tex); mask = grown
    return tex

def bake(V, F, instances, views, size=1024):
    """instances: list of (A, t) with world = local @ A.T + t.  Returns uv, faces, vmapping, texture."""
    vmap, Fn, uv = xatlas.parametrize(V, F)
    Vn = V[vmap]
    fid, bary = rasterize(uv, Fn, size)
    tm = fid >= 0
    ty, tx = np.nonzero(tm)
    f = fid[ty, tx]; b = bary[ty, tx]
    tri = Vn[Fn[f]]
    P = (tri * b[..., None]).sum(1)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); nrm /= np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
    # orient normals outward: away from the object's center (good enough for convex-ish parts),
    # refined per observation by requiring the camera to be on the normal's side
    P32 = P.astype(np.float32); N32 = nrm.astype(np.float32)
    def observations():
        for A, t in instances:
            Pw = P32 @ A.T.astype(np.float32) + t.astype(np.float32); Nw = N32 @ A.T.astype(np.float32)
            for v in views:
                M = v['mat']; Pc = (Pw - M[3]) @ np.linalg.inv(M[:3]); dv = -Pc[:, 2]
                h, w = v['d'].shape; fo = focal(v)
                ok = dv > 0.5
                x = np.where(ok, Pc[:, 0] * fo / np.where(ok, dv, 1) + w/2, -1)
                y = np.where(ok, -Pc[:, 1] * fo / np.where(ok, dv, 1) + h/2, -1)
                ok &= (x >= 0.5) & (x < w - 1.5) & (y >= 0.5) & (y < h - 1.5)
                if not ok.any(): continue
                idx = np.nonzero(ok)[0]; x = x[idx]; y = y[idx]; dv = dv[idx]
                xi = x.astype(int); yi = y.astype(int)
                ds = v['d'][yi, xi]
                ray = Pw[idx] - M[3]; ray /= np.linalg.norm(ray, axis=1)[:, None]
                cos = np.abs((Nw[idx] * ray).sum(1))
                good = (np.abs(ds - dv) < 0.02 * dv + 0.12) & (cos > 0.25)
                idx = idx[good]; x = x[good]; y = y[good]; dv = dv[good]; cos = cos[good]
                x0 = np.clip(np.floor(x - 0.5).astype(int), 0, w - 2); y0 = np.clip(np.floor(y - 0.5).astype(int), 0, h - 2)
                fx = np.clip(x - 0.5 - x0, 0, 1)[:, None]; fy = np.clip(y - 0.5 - y0, 0, 1)[:, None]
                img = v['rgb'].astype(np.float32)
                col = (img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx) * (1 - fy) + (img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx) * fy
                yield idx, col, cos ** 2 / np.maximum(dv, 1) ** 2
    n = len(P)
    acc = np.zeros((n, 3)); ws = np.zeros(n); nobs = np.zeros(n)
    for idx, col, w in observations():
        np.add.at(acc, idx, col * w[:, None]); np.add.at(ws, idx, w); np.add.at(nobs, idx, 1)
    mean = acc / np.maximum(ws, 1e-12)[:, None]
    # robust second pass: down-weight observations far from the mean
    acc2 = np.zeros((n, 3)); ws2 = np.zeros(n)
    for idx, col, w in observations():
        w2 = w / (1 + (np.linalg.norm(col - mean[idx], axis=1) / 25.0) ** 2)
        np.add.at(acc2, idx, col * w2[:, None]); np.add.at(ws2, idx, w2)
    col = acc2 / np.maximum(ws2, 1e-12)[:, None]
    seen = ws > 0
    print('texels %d, seen %.0f%%, avg observations %.1f' % (n, 100 * seen.mean(), nobs[seen].mean()))
    if (~seen).any() and seen.any():
        _, nn = cKDTree(P[seen]).query(P[~seen], k=8)
        col[~seen] = col[seen][nn].mean(1)
    tex = np.zeros((size, size, 3)); tex[ty, tx] = col
    tex = dilate(tex, tm, 6)
    return vmap, Fn, uv, tex
