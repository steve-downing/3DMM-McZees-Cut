"""Texture a fused background mesh with the original 3DMM renders.

Each face is rendered into a face-ID buffer from every original camera
(headless Chromium); a face takes its texture from the view where it covers
the most pixels whose depth matches the original depth map. Faces too small
to cover a pixel fall back to a geometric test. Faces no camera saw get the
color of nearby faces; faces some camera sees straight through are dropped."""
import sys, os, json, subprocess
import numpy as np
import trimesh
from PIL import Image
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(__file__))
from fuse import cam_space, focal, fill_windows
from bkgd import Bkgd, depth
VIEWER = os.path.join(os.path.dirname(__file__), '..', 'viewer')

def build(bkgd_cno, meshfile, out_glb, meta_json):
    B = Bkgd()
    vs = B.views(bkgd_cno)
    for v in vs:
        v['d'], v['hole'] = fill_windows(depth(v))
    m = np.load(meshfile); V, F = m['V'].astype(np.float64), m['F']
    tri = V[F]; nf = len(F)
    c = tri.mean(1)
    n = np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    meta = {'views': [{'chid': int(v['chid']), 'fov': float(np.degrees(v['fov'])),
                       'pos': v['mat'][3].tolist(), 'rot': v['mat'][:3].tolist()} for v in vs]}
    work = os.path.dirname(os.path.abspath(out_glb))
    tri.astype(np.float32).tofile(os.path.join(work, 'ids.bin'))
    json.dump(meta, open(os.path.join(work, 'ids.json'), 'w'))
    # viewpoints for "is this face visible from anywhere inside?": a grid
    # through the open space every original camera saw as empty
    lo = V.min(0); hi = V.max(0)
    g = np.stack(np.meshgrid(np.arange(lo[0], hi[0], 2.5), np.arange(lo[1] + 3, hi[1] - 1, 3.0),
                             np.arange(lo[2], hi[2], 2.5), indexing='ij'), -1).reshape(-1, 3)
    free = np.zeros(len(g), bool)
    for v in vs:
        h, w = v['d'].shape; f = focal(v)
        Pc = cam_space(v, g); dv = -Pc[:, 2]
        x = Pc[:, 0] * f / np.maximum(dv, 1e-6) + w/2; y = -Pc[:, 1] * f / np.maximum(dv, 1e-6) + h/2
        ok = (dv > 0.5) & (x >= 0) & (x < w) & (y >= 0) & (y < h)
        ds = np.full(len(g), -1.0); ds[ok] = v['d'][y[ok].astype(int), x[ok].astype(int)]
        free |= ok & (dv < ds - 1.0)
    samples = np.concatenate([g[free], np.array([v['mat'][3] for v in vs])])
    print('sample viewpoints', len(samples))
    json.dump(samples.round(3).tolist(), open(os.path.join(work, 'samples.json'), 'w'))
    if not os.environ.get('REUSE'):
        subprocess.run(['node', 'idrender.js', work], cwd=VIEWER, check=True)

    good = np.zeros((len(vs), nf)); geo = np.zeros((len(vs), nf)); contra = np.zeros(nf)
    uvs = []
    for k, v in enumerate(vs):
        h, w = v['d'].shape; f = focal(v); R = v['mat'][:3]; T = v['mat'][3]
        px = np.fromfile(os.path.join(work, 'id%d.rgba' % k), np.uint8).reshape(h, w, 4)[::-1]
        ids = px[..., 0].astype(np.int64) | px[..., 1].astype(np.int64) << 8 | px[..., 2].astype(np.int64) << 16
        ys, xs = np.nonzero(ids > 0); fi = ids[ys, xs] - 1
        ok = fi < nf; ys, xs, fi = ys[ok], xs[ok], fi[ok]
        dirc = np.stack([(xs + 0.5 - w/2) / f, -(ys + 0.5 - h/2) / f, -np.ones(len(xs))], -1)
        dirw = dirc @ R
        nn = n[fi]; den = (nn * dirw).sum(1)
        t = (nn * (V[F[fi, 0]] - T)).sum(1) / np.where(np.abs(den) > 1e-9, den, 1e-9)
        dorig = v['d'][ys, xs]
        agree = np.abs(t - dorig) < 0.02 * dorig + 0.08
        good[k] = np.bincount(fi[agree], minlength=nf)
        contra += np.bincount(fi[dorig > t * 1.04 + 0.3], minlength=nf)
        # projection of every vertex into this view (for UVs and the fallback test)
        Pc = cam_space(v, tri.reshape(-1, 3)).reshape(nf, 3, 3); dv = -Pc[..., 2]
        x = Pc[..., 0] * f / np.maximum(dv, 1e-6) + w/2
        y = -Pc[..., 1] * f / np.maximum(dv, 1e-6) + h/2
        uvs.append(np.stack([x / w, 1 - y / h], -1))
        inside = (dv > 0.3).all(1) & (x >= 0).all(1) & (x <= w).all(1) & (y >= 0).all(1) & (y <= h).all(1)
        xc = np.clip(x.mean(1).astype(int), 0, w-1); yc = np.clip(y.mean(1).astype(int), 0, h-1)
        dc = dv.mean(1)
        ray = c - T; ray /= np.linalg.norm(ray, axis=1)[:, None]
        cos = -(n * ray).sum(1)
        geo[k] = np.where(inside & (np.abs(v['d'][yc, xc] - dc) < 0.03 * dc + 0.1) & (cos > 0.1), f * cos / dc, 0)
        good[k][~inside] = 0
    reach = np.fromfile(os.path.join(work, 'seen.bin'), np.uint8)[1:nf+1] > 0
    best = np.where(good.max(0) > 0, good.argmax(0), np.where(geo.max(0) > 0, geo.argmax(0), -1))
    drop = (best < 0) & ((contra > 0) | ~reach)
    print('faces %d: by pixels %.1f%%, by geometry %.1f%%, unseen %.1f%%, dropped %d' % (
        nf, 100 * (good.max(0) > 0).mean(), 100 * ((good.max(0) == 0) & (best >= 0)).mean(),
        100 * ((best < 0) & ~drop).mean(), drop.sum()))
    print('per view', np.bincount(best[best >= 0], minlength=len(vs)))

    scene = trimesh.Scene()
    bypix = good.max(0) > 0
    for k, v in enumerate(vs):
      for grp, gsel in (('', bypix), ('g', ~bypix)):
        sel = np.nonzero((best == k) & gsel)[0]
        if not len(sel): continue
        img = Image.fromarray(v['rgb'])
        verts = tri[sel].reshape(-1, 3); faces = np.arange(len(verts)).reshape(-1, 3)
        mat = trimesh.visual.material.SimpleMaterial(image=img, diffuse=[255, 255, 255, 255])
        mesh = trimesh.Trimesh(verts, faces, process=False,
                               visual=trimesh.visual.TextureVisuals(uv=uvs[k][sel].reshape(-1, 2), image=img, material=mat))
        mesh.merge_vertices()
        scene.add_geometry(mesh, node_name='view%d%s' % (v['chid'], grp), geom_name='view%d%s' % (v['chid'], grp))
    rest = np.nonzero((best < 0) & ~drop)[0]
    if len(rest):
        # never seen by a camera: spread colors along the surface from the
        # seen faces around them (harmonic fill over the mesh graph)
        import scipy.sparse as sp
        nv = len(V)
        vcol = np.zeros((nv, 3)); vcnt = np.zeros(nv)
        seen = np.nonzero(best >= 0)[0]
        for k, v in enumerate(vs):
            sk = seen[best[seen] == k]
            if not len(sk): continue
            h, w = v['d'].shape
            uv = uvs[k][sk].reshape(-1, 2)
            col = v['rgb'][np.clip(((1 - uv[:, 1]) * h).astype(int), 0, h-1), np.clip((uv[:, 0] * w).astype(int), 0, w-1)]
            np.add.at(vcol, F[sk].ravel(), col); np.add.at(vcnt, F[sk].ravel(), 1)
        known = vcnt > 0
        vcol[known] /= vcnt[known][:, None]
        live = F[~drop]
        e = np.concatenate([live[:, [0, 1]], live[:, [1, 2]], live[:, [2, 0]]])
        A = sp.coo_matrix((np.ones(len(e) * 2), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(nv, nv)).tocsr()
        A.data[:] = 1
        deg = np.asarray(A.sum(1)).ravel()
        x = np.where(known[:, None], vcol, vcol[known].mean(0))
        for _ in range(400):
            nx = (A @ x) / np.maximum(deg, 1)[:, None]
            x = np.where(known[:, None], vcol, nx)
        # prefer seen faces on the same plane nearby (floor stays floor)
        fcol = np.zeros((len(seen), 3))
        for k, v in enumerate(vs):
            sk = best[seen] == k
            if not sk.any(): continue
            h, w = v['d'].shape; uv = uvs[k][seen[sk]].mean(1)
            fcol[sk] = v['rgb'][np.clip(((1 - uv[:, 1]) * h).astype(int), 0, h-1), np.clip((uv[:, 0] * w).astype(int), 0, w-1)]
        dd, nb = cKDTree(c[seen]).query(c[rest], k=256, distance_upper_bound=8.0)
        valid = np.isfinite(dd)
        nbc = np.where(valid, nb, 0)
        cop = valid & ((n[seen][nbc] * n[rest][:, None, :]).sum(-1) > 0.9) & \
              (np.abs((n[rest][:, None, :] * (c[seen][nbc] - c[rest][:, None, :])).sum(-1)) < 0.4)
        planar = np.full((len(rest), 3), np.nan)
        for i in np.nonzero(cop.sum(1) >= 3)[0]:
            planar[i] = np.median(fcol[nbc[i][cop[i]]], axis=0)
        print('unseen faces filled from coplanar neighbors: %.0f%%' % (100 * np.isfinite(planar[:, 0]).mean()))
        verts = tri[rest].reshape(-1, 3); faces = np.arange(len(verts)).reshape(-1, 3)
        mesh = trimesh.Trimesh(verts, faces, process=False)
        vc = x[F[rest].ravel()]
        pl = np.repeat(planar, 3, axis=0); okp = np.isfinite(pl[:, 0])
        vc[okp] = pl[okp]
        # glTF vertex colors are linear; these were sampled from sRGB images
        vc = np.clip(vc, 0, 255) / 255.0
        vc = np.where(vc <= 0.04045, vc / 12.92, ((vc + 0.055) / 1.055) ** 2.4)
        vc = np.round(vc * 255).astype(np.uint8)
        mesh.visual.vertex_colors = np.concatenate([vc, np.full((len(vc), 1), 255, np.uint8)], 1)
        scene.add_geometry(mesh, node_name='unseen', geom_name='unseen')
    # a plain shell just outside the cabin, so holes where no camera ever
    # looked show the color of the surface they're in, not the void
    live = ~drop
    seen = np.nonzero(best >= 0)[0]
    scol = np.zeros((len(seen), 3))
    for k, v in enumerate(vs):
        sk = best[seen] == k
        if not sk.any(): continue
        h, w = v['d'].shape; uv = uvs[k][seen[sk]].mean(1)
        scol[sk] = v['rgb'][np.clip(((1 - uv[:, 1]) * h).astype(int), 0, h-1), np.clip((uv[:, 0] * w).astype(int), 0, w-1)]
    sn = n[seen]; sc = c[seen]
    def ext(axis, sign):
        sel = (sn[:, axis] * sign) < -0.7      # faces looking back into the cabin
        vals = sc[sel, axis]
        edge = np.percentile(vals, 98 if sign > 0 else 2)
        near = sel & (np.abs(sc[:, axis] - edge) < 1.5)
        return edge + 0.3 * sign, np.median(scol[near], axis=0) if near.any() else np.median(scol, axis=0)
    box = {}
    for axis in range(3):
        for sign in (-1, 1):
            box[(axis, sign)] = ext(axis, sign)
    lo_ = np.array([box[(a, -1)][0] for a in range(3)]); hi_ = np.array([box[(a, 1)][0] for a in range(3)])
    hv, hf, hc = [], [], []
    for (axis, sign), (pos, col) in box.items():
        a1, a2 = [a for a in range(3) if a != axis]
        q = np.zeros((4, 3)); q[:, axis] = pos
        for i, (u, w_) in enumerate(((lo_[a1], lo_[a2]), (hi_[a1], lo_[a2]), (hi_[a1], hi_[a2]), (lo_[a1], hi_[a2]))):
            q[i, a1] = u; q[i, a2] = w_
        b0 = len(hv); hv.extend(q); hf.extend([[b0, b0+1, b0+2], [b0, b0+2, b0+3]]); hc.extend([col] * 4)
    hc = np.array(hc) / 255.0
    hc = np.where(hc <= 0.04045, hc / 12.92, ((hc + 0.055) / 1.055) ** 2.4)
    hull = trimesh.Trimesh(np.array(hv), np.array(hf), process=False)
    hull.visual.vertex_colors = np.concatenate([np.round(hc * 255).astype(np.uint8), np.full((len(hv), 1), 255, np.uint8)], 1)
    scene.add_geometry(hull, node_name='shell', geom_name='shell')
    meta['bounds'] = [lo_.tolist(), hi_.tolist()]
    print('shell', lo_.round(1), hi_.round(1))
    scene.export(out_glb)
    json.dump(meta, open(meta_json, 'w'))
    print('glb %.1f MB' % (os.path.getsize(out_glb) / 1e6))

if __name__ == '__main__':
    build(int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4])
