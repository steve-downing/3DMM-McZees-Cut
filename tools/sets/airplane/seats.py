"""Find seat instances and align them to a common local frame."""
import sys, os, json
import numpy as np
from scipy.spatial import cKDTree

BOX = dict(x=(-4.3, 4.3), y=(0.08, 15.0), z=(-1.8, 9.0))   # local seat frame: x across, y up, z forward (+z), origin at back

def rot(flip):  # world = R @ local; flip = 180 deg about y
    return np.diag([-1.0, 1, -1]) if flip else np.eye(3)

def crop(P, t, flip, margin=0.0):
    L = (P - t) @ rot(flip)          # world -> local (R orthonormal, R^T = R here)
    m = ((L[:, 0] > BOX['x'][0] - margin) & (L[:, 0] < BOX['x'][1] + margin) &
         (L[:, 1] > BOX['y'][0]) & (L[:, 1] < BOX['y'][1]) &
         (L[:, 2] > BOX['z'][0] - margin) & (L[:, 2] < BOX['z'][1] + margin))
    return L[m]

def score(tree, L, tol=0.15):
    d, _ = tree.query(L, distance_upper_bound=tol)
    return np.isfinite(d).sum()

def icp(ref, P, t, flip, iters=8, search=1.6, step=0.1):
    """grid search over x/z offsets for the most inliers, then gated refinement"""
    tree = cKDTree(ref)
    L0 = crop(P, t, flip, margin=search + 0.2)
    if len(L0) < 100: return t, 0.0
    sub = L0[np.random.default_rng(1).choice(len(L0), min(len(L0), 3000), replace=False)]
    best = (-1, 0, 0)
    offs = np.arange(-search, search + 1e-6, step)
    for dx in offs:
        for dz in offs:
            sc = score(tree, sub + np.array([dx, 0, dz]))
            if sc > best[0]: best = (sc, dx, dz)
    t = t - rot(flip) @ np.array([best[1], 0, best[2]])
    for _ in range(iters):
        L = crop(P, t, flip)
        d, i = tree.query(L, distance_upper_bound=0.3)
        ok = np.isfinite(d)
        if ok.sum() < 50: break
        delta = (ref[i[ok]] - L[ok]).mean(0); delta[1] = 0
        t = t - rot(flip) @ (-delta)
        if np.linalg.norm(delta) < 1e-3: break
    L = crop(P, t, flip)
    return t, score(tree, L, 0.15) / max(len(L), 1)

def main(outdir):
    d = np.load(os.path.join(outdir, 'cloud.npz')); P = d['P']
    P = P[(P[:, 1] > 0.08) & (np.abs(P[:, 0] + 0.55) < 23.0) & (P[:, 2] > -16.8) & (P[:, 2] < 27.0)]
    xs = [-18.6, -10.2, 9.1, 17.5]; zs = [-15.9, -1.2, 20.4]
    init = [(np.array([x, 0, z]), False) for z in zs for x in xs]
    init.append((np.array([-0.3, 0, 26.5]), True))     # rear wall seat, facing the cabin
    # reference: the most-observed instance
    counts = [len(crop(P, t, f)) for t, f in init]
    r = int(np.argmax(counts)); print('points per instance', counts, 'ref', r)
    ref = crop(P, *init[r])
    inst = []
    for k, (t, f) in enumerate(init):
        best = None
        for flip in ([f] if k != len(init) - 1 else [False, True]):
            tt, fit = icp(ref, P, t, flip)
            if best is None or fit > best[2]: best = (tt, flip, fit)
        inst.append(best); print(k, 'pos', best[0].round(2), 'flip', best[1], 'inlier frac %.2f' % best[2], 'pts', len(crop(P, best[0], best[1])))
    # second pass against a reference built from all aligned instances
    ref = np.concatenate([crop(P, t, f) for t, f, e in inst if e > 0.5])
    ref = ref[np.random.default_rng(0).choice(len(ref), min(len(ref), 200000), replace=False)]
    inst2 = []
    for t, f, e in inst:
        tt, err = icp(ref, P, t, f, search=0.4, step=0.05); inst2.append((tt, f, err))
        print('refined', tt.round(3), f, '%.3f' % err)
    json.dump([dict(t=t.tolist(), flip=bool(f), err=float(e)) for t, f, e in inst2], open(os.path.join(outdir, 'seats.json'), 'w'), indent=1)

if __name__ == '__main__':
    main(sys.argv[1])
