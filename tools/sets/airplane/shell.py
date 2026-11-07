"""Cabin shell: the symmetric cross-section swept along z, plus two end walls.
Textures are splatted from every observed point near the surface, then gaps
are filled from the mirror side, then along the cabin's length."""
import sys, os, json
import numpy as np
from PIL import Image
from scipy import ndimage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from cloud import clouds

RES = 0.07
Z0, Z1 = -17.0, 27.25
ZDOOR = -18.55
ARCH = dict(xc=-0.55, hw=6.5, spring=17.0)   # door: half width, height where the arch starts

def in_arch(x, y):
    dx = x - ARCH['xc']
    return (y >= 0) & (np.abs(dx) <= ARCH['hw']) & ((y <= ARCH['spring']) | (dx ** 2 + (y - ARCH['spring']) ** 2 <= ARCH['hw'] ** 2))

def full_profile(prof):
    half = np.array(prof['half'])              # (0,0) .. right side .. (0,top)
    left = half[::-1].copy(); left[:, 0] *= -1  # (0,top) .. left side .. (0,0)
    loop = np.vstack([left, half[1:]])         # top center -> left -> floor -> right -> top center
    loop[:, 0] += prof['xc']
    seg = np.diff(loop, axis=0); L = np.linalg.norm(seg, axis=1)
    s = np.concatenate([[0], np.cumsum(L)])
    return loop, s

def project_to_profile(xy, loop, s):
    """nearest point on the polyline: arc length, signed distance (+ = outside)"""
    best_d = np.full(len(xy), np.inf); best_s = np.zeros(len(xy)); best_sd = np.zeros(len(xy)); best_n = np.zeros((len(xy), 2))
    for i in range(len(loop) - 1):
        a, b = loop[i], loop[i+1]; ab = b - a; L2 = (ab ** 2).sum()
        t = np.clip(((xy - a) @ ab) / L2, 0, 1)
        q = a + t[:, None] * ab; dv = xy - q; dist = np.linalg.norm(dv, axis=1)
        # loop runs clockwise seen from +z (top -> left -> bottom -> right); outward normal = (-ab_y, ab_x)?
        nrm = np.array([ab[1], -ab[0]]) / np.sqrt(L2)
        sd = dv @ nrm
        m = dist < best_d
        best_d[m] = dist[m]; best_s[m] = s[i] + t[m] * np.sqrt(L2); best_sd[m] = sd[m]; best_n[m] = nrm
    return best_s, best_sd, best_n

def splat(H, W, iu, iv, col, w):
    acc = np.zeros((H, W, 3)); ws = np.zeros((H, W))
    m = (iu >= 0) & (iu < W) & (iv >= 0) & (iv < H)
    np.add.at(acc, (iv[m], iu[m]), col[m] * w[m, None]); np.add.at(ws, (iv[m], iu[m]), w[m])
    return acc, ws

def pullpush(img, known):
    """fill unknown texels from coarser averages (smooth, no streaks)"""
    if known.all() or min(img.shape[:2]) < 2:
        if not known.any(): return img
        _, (iy, ix) = ndimage.distance_transform_edt(~known, return_indices=True)
        return img[iy, ix]
    H, W = known.shape; h2, w2 = (H + 1) // 2, (W + 1) // 2
    pad = np.zeros((h2 * 2, w2 * 2, 3)); pk = np.zeros((h2 * 2, w2 * 2))
    pad[:H, :W] = img * known[..., None]; pk[:H, :W] = known
    cs = pad.reshape(h2, 2, w2, 2, 3).sum((1, 3)); ck = pk.reshape(h2, 2, w2, 2).sum((1, 3))
    coarse = cs / np.maximum(ck, 1e-9)[..., None]
    coarse = pullpush(coarse, ck > 0)
    up = np.repeat(np.repeat(coarse, 2, 0), 2, 1)[:H, :W]
    up = ndimage.uniform_filter(up, size=(3, 3, 1))
    return np.where(known[..., None], img, up)

def pullpush_axis(img, known, axis):
    """pull-push that only coarsens along one axis: fills gaps from averages
    of known texels in the same row/column, smoothly"""
    im = np.moveaxis(img, axis, 0); kn = np.moveaxis(known, axis, 0)
    def rec(im, kn):
        n = kn.shape[0]
        if n < 2 or kn.all():
            return im, kn
        h = (n + 1) // 2
        pad = np.zeros((h * 2,) + im.shape[1:]); pk = np.zeros((h * 2,) + kn.shape[1:])
        pad[:n] = im * kn[..., None]; pk[:n] = kn
        cs = pad.reshape((h, 2) + im.shape[1:]).sum(1); ck = pk.reshape((h, 2) + kn.shape[1:]).sum(1)
        coarse = cs / np.maximum(ck, 1e-9)[..., None]
        coarse, ckn = rec(coarse, ck > 0)
        up = np.repeat(coarse, 2, 0)[:n]; upk = np.repeat(ckn, 2, 0)[:n]
        up = ndimage.uniform_filter1d(up, 3, axis=0)
        return np.where(kn[..., None], im, up), kn | upk
    out, ok = rec(im, kn)
    return np.moveaxis(out, 0, axis), np.moveaxis(ok, 0, axis)

def fill_along(img, known, axis):
    """copy the nearest known texel along one axis (rows or columns)"""
    im = np.moveaxis(img, axis, 0).copy(); kn = np.moveaxis(known, axis, 0)
    n = kn.shape[0]; idx = np.arange(n)[:, None] * np.ones(kn.shape[1], int)[None, :]
    fwd = np.where(kn, idx, -1); fwd = np.maximum.accumulate(fwd, axis=0)
    bwd = np.where(kn, idx, n); bwd = np.minimum.accumulate(bwd[::-1], axis=0)[::-1]
    df = np.where(fwd >= 0, idx - fwd, 10 ** 9); db = np.where(bwd < n, bwd - idx, 10 ** 9)
    src = np.where(df <= db, fwd, bwd); ok = np.minimum(df, db) < 10 ** 9
    cols = np.arange(kn.shape[1])[None, :] * np.ones(n, int)[:, None]
    out = im.copy(); out[ok] = im[np.clip(src, 0, n - 1)[ok], cols[ok]]
    return np.moveaxis(out, 0, axis), np.moveaxis(kn | ok, 0, axis)

def fill(img, known, mirror_axis=None):
    img = img.copy(); known = known.copy()
    if mirror_axis is not None:
        mir = np.flip(img, axis=mirror_axis); mk = np.flip(known, axis=mirror_axis)
        take = ~known & mk; img[take] = mir[take]; known |= take
    return pullpush(img, known), known

def main(outdir):
    prof = json.load(open(os.path.join(outdir, 'profile.json')))
    loop, s = full_profile(prof); S = s[-1]
    vs, cl = clouds(step=1)
    W = int(np.ceil(S / RES)); H = int(np.ceil((Z1 - Z0) / RES))
    accS = np.zeros((H, W, 3)); wsS = np.zeros((H, W)); holeS = np.zeros((H, W))
    ends = {}
    for zend, sign in ((Z0, 1), (Z1, -1)):
        xs0 = loop[:, 0].min(); xs1 = loop[:, 0].max(); ys1 = loop[:, 1].max()
        ends[zend] = dict(x0=xs0, y0=0.0, W=int(np.ceil((xs1 - xs0) / RES)), H=int(np.ceil(ys1 / RES)), sign=sign)
        ends[zend]['acc'] = np.zeros((ends[zend]['H'], ends[zend]['W'], 3)); ends[zend]['ws'] = np.zeros((ends[zend]['H'], ends[zend]['W']))
    # end walls, pass 1: how close to each wall plane anything gets, per texel
    for zend, e in ends.items():
        e['near'] = np.full((e['H'], e['W']), np.inf)
        gx = e['x0'] + (np.arange(e['W']) + 0.5) * RES; gy = (np.arange(e['H']) + 0.5) * RES
        GX, GY = np.meshgrid(gx, gy)
        e['target'] = np.where(in_arch(GX, GY), ZDOOR, zend) if zend == Z0 else np.full(GX.shape, zend)
    for c in cl:
        ok = ~c['edge'] & np.isfinite(c['d'])
        P = c['P'][ok]; n = c['n'][ok]
        for zend, e in ends.items():
            m = (np.abs(P[:, 2] - zend) < 4.5) & (n[:, 2] * e['sign'] > 0.6)
            iu = ((P[m, 0] - e['x0']) / RES).astype(int); iv = (P[m, 1] / RES).astype(int)
            k = (iu >= 0) & (iu < e['W']) & (iv >= 0) & (iv < e['H'])
            np.minimum.at(e['near'], (iv[k], iu[k]), np.abs(P[m, 2][k] - e['target'][iv[k], iu[k]]))
    for zend, e in ends.items():
        # a texel belongs to the wall only if its nearest point is close to the plane
        e['near'] = np.where(e['near'] < 1.3, e['near'], -1.0)
    for c in cl:
        ok = ~c['edge'] & np.isfinite(c['d'])
        P = c['P'][ok]; n = c['n'][ok]; col = c['rgb'][ok].astype(float); d = c['d'][ok]
        ray = P - c['cam']; ray /= np.linalg.norm(ray, axis=1)[:, None]
        cos = np.abs((n * ray).sum(1))
        w = (cos ** 2) / np.maximum(d, 1) ** 2
        # side shell
        sp, sd, nrm = project_to_profile(P[:, :2], loop, s)
        inz = (P[:, 2] > Z0 + 0.3) & (P[:, 2] < Z1 - 0.3)
        agree = -(n[:, 0] * nrm[:, 0] + n[:, 1] * nrm[:, 1])   # point normal vs inward shell normal
        m = inz & (np.abs(sd) < 0.9) & (agree > 0.7)
        a, ww = splat(H, W, (sp[m] / RES).astype(int), ((P[m, 2] - Z0) / RES).astype(int), col[m], w[m])
        accS += a; wsS += ww
        hole = c['hole'][ok]
        _, hw = splat(H, W, (sp[m] / RES).astype(int), ((P[m, 2] - Z0) / RES).astype(int), col[m], w[m] * hole[m])
        holeS += hw
        # end walls: points near the plane facing into the cabin
        for zend, e in ends.items():
            m = (np.abs(P[:, 2] - zend) < 2.5) & (n[:, 2] * e['sign'] > 0.6)
            iu = ((P[:, 0] - e['x0']) / RES).astype(int); iv = (P[:, 1] / RES).astype(int)
            inb = (iu >= 0) & (iu < e['W']) & (iv >= 0) & (iv < e['H'])
            near = np.full(len(P), -1.0); near[inb] = e['near'][iv[inb], iu[inb]]
            tgt = np.full(len(P), zend); tgt[inb] = e['target'][iv[inb], iu[inb]]
            m = (np.abs(P[:, 2] - tgt) < 2.5) & (n[:, 2] * e['sign'] > 0.6)
            m &= inb & (near >= 0) & (np.abs(P[:, 2] - tgt) < near + 0.4)
            a, ww = splat(e['H'], e['W'], iu[m], iv[m], col[m], w[m])
            e['acc'] += a; e['ws'] += ww
    known = wsS > 0
    tex = accS / np.maximum(wsS, 1e-12)[..., None]
    # window glass: the painted sky seen through the windows differs from view
    # to view; replace it with a calm, blurred version of itself
    win = known & (holeS > 0.5 * wsS)
    win = ndimage.binary_closing(win, iterations=2) & known
    if win.any():
        sky = ndimage.gaussian_filter(np.where(win[..., None], tex, 0), (6, 6, 0))
        skw = ndimage.gaussian_filter(win.astype(float), 6)
        calm = sky / np.maximum(skw, 1e-6)[..., None]
        tex[win] = calm[win]
        print('  window texels %d' % win.sum())
    Image.fromarray((win * 255).astype(np.uint8)).save(os.path.join(outdir, 'shell_win.png'), optimize=True)
    print('shell texture %dx%d, observed %.0f%%' % (W, H, 100 * known.mean()))
    # mirror: arc length s <-> S - s
    mir = np.flip(tex, axis=1); mk = np.flip(known, axis=1)
    take = ~known & mk; tex[take] = mir[take]; k2 = known | take
    print('  after mirror %.0f%%' % (100 * k2.mean()))
    tex, k3 = pullpush_axis(tex, k2, axis=0)     # along the cabin's length
    tex = pullpush(tex, k3)
    Image.fromarray(np.clip(tex, 0, 255).astype(np.uint8)[::-1]).save(os.path.join(outdir, 'shell.jpg'), quality=90)
    Image.fromarray((known * 255).astype(np.uint8)[::-1]).save(os.path.join(outdir, 'shell_known.png'))
    for zend, e in ends.items():
        known = e['ws'] > 0
        t = e['acc'] / np.maximum(e['ws'], 1e-12)[..., None]
        # mirror about the cabin center line
        e['known'] = known
        cx = int(round((prof['xc'] - e['x0']) / RES))
        t2, k2 = t.copy(), known.copy()
        for xi in range(e['W']):
            xm = 2 * cx - xi
            if 0 <= xm < e['W']:
                take = ~k2[:, xi] & known[:, xm]; t2[take, xi] = t[take, xm]; k2[take, xi] = True
        t2, k3 = pullpush_axis(t2, k2, axis=0)   # down/up the column
        t2 = pullpush(t2, k3)
        name = 'front' if zend == Z0 else 'rear'
        print('%s wall %dx%d observed %.0f%%' % (name, e['W'], e['H'], 100 * known.mean()))
        Image.fromarray(np.clip(t2, 0, 255).astype(np.uint8)[::-1]).save(os.path.join(outdir, name + '.jpg'), quality=90)
    json.dump({'loop': loop.tolist(), 's': s.tolist(), 'Z0': Z0, 'Z1': Z1, 'ZDOOR': ZDOOR, 'ARCH': ARCH, 'RES': RES,
               'ends': {('front' if z == Z0 else 'rear'): dict(x0=e['x0'], W=e['W'], H=e['H']) for z, e in ends.items()}},
              open(os.path.join(outdir, 'shell.json'), 'w'))

if __name__ == '__main__':
    main(sys.argv[1])
