"""Fuse a 3DMM background's views into one textured mesh (GLB)."""
import sys, os, time, io, json
import numpy as np
from scipy.sparse import lil_matrix, csr_matrix
from scipy.sparse.linalg import spsolve
from skimage import measure
import trimesh, subprocess
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from bkgd import Bkgd, depth

def fill_windows(d):
    """Empty pixels (sky through windows) get a surface: inverse depth is
    linear across a plane in screen space, so solve Laplace on 1/d."""
    h, w = d.shape
    hole = ~np.isfinite(d)
    if not hole.any(): return d, hole
    inv = np.where(hole, 0, 1 / np.where(hole, 1, d))
    idx = -np.ones((h, w), int); ys, xs = np.nonzero(hole); idx[ys, xs] = np.arange(len(ys))
    A = lil_matrix((len(ys), len(ys))); b = np.zeros(len(ys))
    for k, (y, x) in enumerate(zip(ys, xs)):
        n = 0
        for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
            yy, xx = y+dy, x+dx
            if 0 <= yy < h and 0 <= xx < w:
                n += 1
                if hole[yy, xx]: A[k, idx[yy, xx]] -= 1
                else: b[k] += inv[yy, xx]
        A[k, k] = n
    sol = spsolve(csr_matrix(A), b)
    out = d.copy(); out[ys, xs] = 1 / np.maximum(sol, 1e-4)
    return out, hole

def view_cos(v):
    """|cos| between each pixel's surface normal and its view ray"""
    h, w = v['d'].shape; f = focal(v); d = v['d']
    ys, xs = np.mgrid[0:h, 0:w]
    P = np.stack([(xs+0.5-w/2)*d/f, -(ys+0.5-h/2)*d/f, -d], -1)
    gx = np.gradient(P, axis=1); gy = np.gradient(P, axis=0)
    n = np.cross(gx, gy); n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)
    r = P / np.linalg.norm(P, axis=-1, keepdims=True)
    return np.clip(np.abs((n * r).sum(-1)), 0.15, 1.0).astype(np.float32)

def sample(img, x, y):
    """bilinear, falling back to nearest across depth discontinuities"""
    h, w = img.shape
    x0 = np.clip(np.floor(x - 0.5).astype(int), 0, w-2); y0 = np.clip(np.floor(y - 0.5).astype(int), 0, h-2)
    fx = np.clip(x - 0.5 - x0, 0, 1); fy = np.clip(y - 0.5 - y0, 0, 1)
    a = img[y0, x0]; b = img[y0, x0+1]; c = img[y0+1, x0]; d = img[y0+1, x0+1]
    bil = (a*(1-fx) + b*fx)*(1-fy) + (c*(1-fx) + d*fx)*fy
    lo = np.minimum(np.minimum(a, b), np.minimum(c, d)); hi = np.maximum(np.maximum(a, b), np.maximum(c, d))
    near = img[np.clip(y.astype(int), 0, h-1), np.clip(x.astype(int), 0, w-1)]
    return np.where(hi - lo > 0.05 * lo + 0.1, near, bil)

def cam_space(v, P):
    M = v['mat']; R = M[:3]; T = M[3]
    return (P - T) @ np.linalg.inv(R)

def focal(v): return (v['z'].shape[0] / 2) / np.tan(v['fov'] / 2)

def main(bkgd_cno, out, voxel=0.125, mu=0.3, target_tris=160000):
    t0 = time.time()
    B = Bkgd()
    name = B.names()[bkgd_cno]
    vs = B.views(bkgd_cno)
    for v in vs:
        v['d'], v['hole'] = fill_windows(depth(v))
        v['cos'] = view_cos(v)
    print('views', len(vs), 'filled', '%.1fs' % (time.time()-t0))

    # bounds from all view points
    pts = []
    for v in vs:
        h, w = v['d'].shape; f = focal(v)
        ys, xs = np.mgrid[0:h:4, 0:w:4]; d = v['d'][::4, ::4]
        P = np.stack([(xs+0.5-w/2)*d/f, -(ys+0.5-h/2)*d/f, -d], -1).reshape(-1, 3)
        pts.append(P @ v['mat'][:3] + v['mat'][3])
    P = np.concatenate(pts)
    lo = np.percentile(P, 0.2, axis=0) - 1; hi = np.percentile(P, 99.8, axis=0) + 1
    dims = np.ceil((hi - lo) / voxel).astype(int)
    print('grid', dims, dims.prod()/1e6, 'M voxels')
    tsdf = np.ones(dims, np.float32); wsum = np.zeros(dims, np.float32)
    gx = lo[0] + (np.arange(dims[0]) + 0.5) * voxel
    gy = lo[1] + (np.arange(dims[1]) + 0.5) * voxel
    gz = lo[2] + (np.arange(dims[2]) + 0.5) * voxel
    YY, ZZ = np.meshgrid(gy, gz, indexing='ij')
    for ix in range(dims[0]):
        Pw = np.stack([np.full(YY.size, gx[ix]), YY.ravel(), ZZ.ravel()], -1)
        acc = np.zeros(YY.size, np.float32); wacc = np.zeros(YY.size, np.float32)
        for v in vs:
            Pc = cam_space(v, Pw); dv = -Pc[:, 2]
            h, w = v['d'].shape; f = focal(v)
            ok = dv > 0.5
            x = np.where(ok, Pc[:, 0] * f / np.where(ok, dv, 1) + w/2, -1)
            y = np.where(ok, -Pc[:, 1] * f / np.where(ok, dv, 1) + h/2, -1)
            ok &= (x >= 0) & (x < w) & (y >= 0) & (y < h)
            xs_ = np.where(ok, x, 1.0); ys_ = np.where(ok, y, 1.0)
            ds = sample(v['d'], xs_, ys_)
            cs = v['cos'][np.clip(ys_.astype(int), 0, h-1), np.clip(xs_.astype(int), 0, w-1)]
            sdf = (ds - dv) * cs           # roughly perpendicular to the surface
            ok &= sdf > -mu
            tt = np.clip(sdf / mu, -1, 1)
            wt = cs / np.maximum(dv, 1.0)  # trust close, head-on views more
            acc[ok] += (tt * wt)[ok]; wacc[ok] += wt[ok]
        m = wacc > 0
        sl = tsdf[ix].reshape(-1); ws = wsum[ix].reshape(-1)
        sl[m] = acc[m] / wacc[m]; ws[m] = wacc[m]
    print('fused %.1fs' % (time.time()-t0))
    verts, faces, normals, _ = measure.marching_cubes(tsdf, 0.0, spacing=(voxel,)*3, mask=wsum > 0)
    verts += lo + voxel/2
    print('mc', len(verts), len(faces), '%.1fs' % (time.time()-t0))
    # drop tiny floating pieces
    mesh = trimesh.Trimesh(verts, faces, process=True)
    parts = mesh.split(only_watertight=False)
    keep = [p for p in parts if len(p.faces) > 200]
    mesh = trimesh.util.concatenate(keep)
    raw = out + '.raw.glb'; small = out + '.small.glb'
    mesh.export(raw)
    ratio = min(1.0, target_tris / len(mesh.faces))
    viewer = os.path.join(os.path.dirname(__file__), '..', 'viewer')
    subprocess.run(['npx', 'gltfpack', '-i', os.path.abspath(raw), '-o', os.path.abspath(small), '-si', '%.4f' % ratio, '-noq'],
                   cwd=viewer, check=True, capture_output=True)
    sm = trimesh.load(small, force='mesh')
    V, F = np.asarray(sm.vertices), np.asarray(sm.faces)
    print('simplified', len(V), len(F), '%.1fs' % (time.time()-t0))
    np.savez_compressed(out + '.mesh.npz', V=V, F=F)
    return name, vs, V, F

if __name__ == '__main__':
    main(int(sys.argv[1]), sys.argv[2])
