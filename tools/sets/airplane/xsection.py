"""The cabin's cross-section: one half-profile, measured from the point cloud.

    python xsection.py <dir>        reads <dir>/cloud.npz, writes <dir>/profile.json
                                    and <dir>/xsec.png (points + fitted profile)

Every point between the end walls is put in polar coordinates around the cabin
axis (folded left onto right); the 90th-percentile radius per angle is the wall.
The result is simplified to a polyline (Douglas-Peucker, 0.06 units)."""
import sys, os, json
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import median_filter

XC, YC = -0.55, 11.0          # cabin center line (x) and the height the angles are taken around

def dp(p, eps):
    if len(p) < 3: return p
    a, b = p[0], p[-1]; ab = b - a; L = np.linalg.norm(ab) + 1e-12
    dist = np.abs(ab[0] * (p[:, 1] - a[1]) - ab[1] * (p[:, 0] - a[0])) / L
    i = np.argmax(dist)
    if dist[i] > eps: return np.vstack([dp(p[:i + 1], eps)[:-1], dp(p[i:], eps)])
    return np.vstack([a, b])

def main(d):
    c = np.load(os.path.join(d, 'cloud.npz')); P = c['P']
    sel = (P[:, 2] > -12) & (P[:, 2] < 22)
    X = P[sel, 0]; Y = P[sel, 1]
    xs = np.abs(X - XC)
    th = np.arctan2(Y - YC, xs); r = np.hypot(xs, Y - YC)
    nb = 360; bins = np.linspace(-np.pi / 2, np.pi / 2, nb + 1)
    idx = np.clip(np.digitize(th, bins) - 1, 0, nb - 1)
    prof = np.array([np.percentile(r[idx == b], 90) if (idx == b).sum() >= 10 else np.nan for b in range(nb)])
    ang = (bins[:-1] + bins[1:]) / 2
    ok = np.isfinite(prof); prof = np.interp(ang, ang[ok], prof[ok])
    prof = median_filter(prof, size=5, mode='nearest')
    px = prof * np.cos(ang); py = YC + prof * np.sin(ang)
    py = np.where(py < 0.3, 0.0, py)
    pts = np.vstack([[0, 0], np.stack([px, py], 1), [0, py[-1]]])
    s = dp(pts, 0.06)
    print(len(pts), '->', len(s))
    json.dump({'xc': XC, 'half': s.tolist()}, open(os.path.join(d, 'profile.json'), 'w'))
    # debug picture: points (grey) and the fitted profile (orange), 20 px per unit
    W, H = int(54 / 0.05), int(30 / 0.05)
    to_px = lambda x, y: ((x + 27) / 0.05, (29 - y) / 0.05)
    im = Image.new('RGB', (W, H), (16, 16, 20)); dr = ImageDraw.Draw(im)
    for x, y in zip(X[::7], Y[::7]): dr.point(to_px(x, y), fill=(150, 150, 150))
    full = np.vstack([s[::-1] * [-1, 1], s]) + [XC, 0]
    dr.line([to_px(x, y) for x, y in full], fill=(255, 120, 40), width=2)
    im.save(os.path.join(d, 'xsec.png'))

if __name__ == '__main__':
    main(sys.argv[1])
