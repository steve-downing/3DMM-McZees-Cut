"""One seat model from every observation of every seat: each (camera view,
seat instance) pair is treated as a camera looking at the same object."""
import sys, os, json, time
import numpy as np
from skimage import measure
import trimesh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from bkgd import Bkgd, depth
from fuse import fill_windows, focal, view_cos, sample

BOX = dict(x=(-4.35, 4.35), y=(0.15, 14.8), z=(-2.0, 7.6))
from layout import XS, ROWS, INST, SMALL, R, TABLES

def views():
    B = Bkgd()
    vs = B.views(10)
    for v in vs:
        v['d'], _ = fill_windows(depth(v)); v['cos'] = view_cos(v)
    return vs

def main(out, voxel=0.05, mu=0.15, box=None, inst=None):
    box = box or BOX
    inst = inst or [(R(f), t) for t, f in INST]
    t0 = time.time()
    vs = views()
    lo = np.array([box['x'][0], box['y'][0], box['z'][0]]); hi = np.array([box['x'][1], box['y'][1], box['z'][1]])
    dims = np.ceil((hi - lo) / voxel).astype(int)
    print('grid', dims, dims.prod() / 1e6, 'M')
    gx = lo[0] + (np.arange(dims[0]) + 0.5) * voxel
    gy = lo[1] + (np.arange(dims[1]) + 0.5) * voxel
    gz = lo[2] + (np.arange(dims[2]) + 0.5) * voxel
    tsdf = np.ones(dims, np.float32); wsum = np.zeros(dims, np.float32)
    YY, ZZ = np.meshgrid(gy, gz, indexing='ij')
    for ix in range(dims[0]):
        L = np.stack([np.full(YY.size, gx[ix]), YY.ravel(), ZZ.ravel()], -1)
        acc = np.zeros(len(L), np.float32); wacc = np.zeros(len(L), np.float32)
        for A, t in inst:
            Pw = L @ A.T + t
            for v in vs:
                M = v['mat']; Pc = (Pw - M[3]) @ np.linalg.inv(M[:3]); dv = -Pc[:, 2]
                h, w = v['d'].shape; f = focal(v)
                ok = dv > 0.5
                x = np.where(ok, Pc[:, 0] * f / np.where(ok, dv, 1) + w/2, -1)
                y = np.where(ok, -Pc[:, 1] * f / np.where(ok, dv, 1) + h/2, -1)
                ok &= (x >= 1) & (x < w - 1) & (y >= 1) & (y < h - 1)
                if not ok.any(): continue
                xs_ = np.where(ok, x, 2.0); ys_ = np.where(ok, y, 2.0)
                ds = sample(v['d'], xs_, ys_)
                cs = v['cos'][ys_.astype(int), xs_.astype(int)]
                sdf = (ds - dv) * cs
                ok &= sdf > -mu
                tt = np.clip(sdf / mu, -1, 1); wt = cs / np.maximum(dv, 1.0)
                acc[ok] += (tt * wt)[ok]; wacc[ok] += wt[ok]
        m = wacc > 0
        sl = tsdf[ix].reshape(-1); ws = wsum[ix].reshape(-1)
        sl[m] = acc[m] / wacc[m]; ws[m] = wacc[m]
        if ix % 40 == 0: print('  slice', ix, '%.0fs' % (time.time() - t0), flush=True)
    np.savez_compressed(out + '.tsdf.npz', tsdf=tsdf, wsum=wsum, lo=lo, voxel=voxel)
    verts, faces, _, _ = measure.marching_cubes(tsdf, 0.0, spacing=(voxel,) * 3, mask=wsum > 0)
    verts += lo + voxel / 2
    mesh = trimesh.Trimesh(verts, faces, process=True)
    parts = mesh.split(only_watertight=False)
    big = max(len(p.faces) for p in parts)
    mesh = trimesh.util.concatenate([p for p in parts if len(p.faces) > 0.01 * big])
    mesh.export(out + '.raw.ply')
    print('seat mesh', len(mesh.vertices), len(mesh.faces), '%.0fs' % (time.time() - t0))

TABLE_BOX = dict(x=(-1.72, 2.3), y=(0.15, 5.2), z=(-2.7, 2.7))

if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[2] == 'table':
        main(sys.argv[1], voxel=0.04, mu=0.12, box=TABLE_BOX, inst=TABLES)
    else:
        main(sys.argv[1])
