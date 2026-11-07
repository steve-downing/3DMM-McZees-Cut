"""Per-view colored point clouds with normals, in world space.

    python cloud.py <out.npz> [background number, default 10 = airplane] [step]"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from bkgd import Bkgd, depth
from fuse import fill_windows, focal

def clouds(cno=10, step=1):
    B = Bkgd()
    vs = B.views(cno)
    out = []
    for k, v in enumerate(vs):
        d, hole = fill_windows(depth(v))
        h, w = d.shape; f = focal(v)
        ys, xs = np.mgrid[0:h, 0:w]
        P = np.stack([(xs+0.5-w/2)*d/f, -(ys+0.5-h/2)*d/f, -d], -1)
        gx = np.gradient(P, axis=1); gy = np.gradient(P, axis=0)
        n = np.cross(gx, gy); n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)
        # orient toward camera
        n *= np.where((n * P).sum(-1, keepdims=True) > 0, -1, 1)
        # flag depth edges (unreliable)
        dd = np.maximum(np.abs(np.gradient(d, axis=0)), np.abs(np.gradient(d, axis=1)))
        edge = dd > 0.04 * d
        R = v['mat'][:3]; T = v['mat'][3]
        Pw = P @ R + T; nw = n @ R
        sl = (slice(None, None, step), slice(None, None, step))
        out.append(dict(view=k, P=Pw[sl].reshape(-1,3), n=nw[sl].reshape(-1,3), rgb=v['rgb'][sl].reshape(-1,3),
                        d=d[sl].ravel(), edge=edge[sl].ravel(), hole=hole[sl].ravel(), cam=T, R=R,
                        px=np.stack([xs, ys], -1)[sl].reshape(-1, 2)))
    return vs, out


def main(out, cno=10, step=2):
    """save every view's points (world space) to one npz: P points, N normals,
    C colors, H whether the point is a filled-in window hole; depth edges dropped"""
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    vs, cl = clouds(cno, step)
    keep = [~c['edge'] for c in cl]
    cat = lambda key: np.concatenate([c[key][k] for c, k in zip(cl, keep)])
    np.savez_compressed(out, P=cat('P').astype(np.float32), N=cat('n').astype(np.float32), C=cat('rgb'), H=cat('hole'))

if __name__ == '__main__':
    main(sys.argv[1], *(int(a) for a in sys.argv[2:]))
