"""Read a 3DMM actor template (TMPL in tmpls.3cn) and pose it.

An actor is a tree of body parts. Each part has a BRender model (BMDL), and
each action cel says which model and which matrix (relative to the parent
part) every part uses. Costumes are custom materials (CMTL) per body part
set, either solid palette colors or 8-bit texture maps (TMAP).

    python actor.py <name> [action] [cel]     prints a summary of the actor
"""
import sys, os, struct
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bkgd import Bkgd, base_palette
from paths import ROOT

TMPLS = os.path.join(ROOT, 'content-files', 'tmpls.3cn')
FX = 1 / 65536.0

def gl(d):
    """generic list on file: header, then ivMac fixed-size entries"""
    bo, osk, cb, n = struct.unpack('<hhii', d[:12])
    return [d[12 + i * cb:12 + (i + 1) * cb] for i in range(n)]

def gg(d):
    """generic group on file: header, data, then (bv, cb) per entry; each entry is cbFixed + variable bytes"""
    bo, osk, n, bvMac, clocFree, cbFixed = struct.unpack('<hhiiii', d[:20])
    data = d[20:20 + bvMac]; locs = d[20 + bvMac:]
    out = []
    for i in range(n):
        bv, cb = struct.unpack('<ii', locs[i * 8:i * 8 + 8])
        e = data[bv:bv + cb]; out.append((e[:cbFixed], e[cbFixed:]))
    return out

def mat34(b):
    """BRender 3x4 fixed-point matrix (row-vector convention): 4 rows of 3"""
    m = np.array(struct.unpack('<12i', b), float).reshape(4, 3) * FX
    M = np.eye(4); M[:4, :3] = m; M[:3, 3] = 0; M[3, 3] = 1
    return M

def model(d):
    """BMDL: header, then BRender vertices (position, uv) and faces (3 indices + smoothing group)"""
    bo, osk, cver, cfac = struct.unpack('<hhhh', d[:8])
    off = 48
    V = np.zeros((cver, 3)); UV = np.zeros((cver, 2))
    for i in range(cver):
        x, y, z, u, v = struct.unpack('<5i', d[off + i * 32:off + i * 32 + 20])
        V[i] = (x * FX, y * FX, z * FX); UV[i] = (u * FX, v * FX)
    off += cver * 32
    F = np.zeros((cfac, 3), int); smooth = np.zeros(cfac, int)
    for i in range(cfac):
        a, b, c = struct.unpack('<3H', d[off + i * 32:off + i * 32 + 6])
        F[i] = (a, b, c); smooth[i] = struct.unpack('<H', d[off + i * 32 + 16:off + i * 32 + 18])[0]
    assert off + cfac * 32 == len(d), 'unexpected BMDL size'
    return V, UV, F, smooth

class Template:
    def __init__(s, name, path=TMPLS):
        s.B = Bkgd(path); c = s.B.c
        k = [k for k in c.chunks if k[0] == 'TMPL' and c.name(*k) == name]
        if not k: raise KeyError(name)
        s.key = k[0]; s.kids = c.chunks[s.key]['kids']
        d = s.B.get(*s.key)
        _, _, xa, ya, za, _, grf = struct.unpack('<hhhhhhI', d[:16])
        s.rest = (xa, ya, za)                                   # BRA: 65536 = full turn
        s.parent = [struct.unpack('<h', e)[0] for e in gl(s._kid('GLPI', 0))]
        s.bset = [struct.unpack('<h', e)[0] for e in gl(s._kid('GLBS', 0))]
        s.costumes = [list(struct.unpack('<%di' % (len(v) // 4), v)) for f, v in gg(s._kid('GGCM', 0))]
        s.actions = {chid: s.B.c.name(kc, kn) for kc, kn, chid in s.kids if kc == 'ACTN'}
        s.pal = base_palette()

    def _kidref(s, ctg, chid, kids=None):
        for kc, kn, ch in (kids if kids is not None else s.kids):
            if kc == ctg and ch == chid: return (kc, kn)
        return None
    def _kid(s, ctg, chid, kids=None):
        r = s._kidref(ctg, chid, kids)
        return s.B.get(*r) if r else None

    def cel(s, anid=0, icel=0):
        """per body part: (model chid or None, matrix relative to its parent)"""
        a = s._kidref('ACTN', anid); akids = s.B.c.chunks[a]['kids']
        cels = gg(s._kid('GGCL', 0, akids)); xf = [mat34(e) for e in gl(s._kid('GLXF', 0, akids))]
        fixed, var = cels[icel % len(cels)]
        cps = [struct.unpack('<hh', var[i * 4:i * 4 + 4]) for i in range(len(var) // 4)]
        return [(None if ch == -1 else ch, xf[im]) for ch, im in cps], len(cels)

    def material(s, ref):
        """a MTRL chunk: solid color (palette ramp) or texture (RGB image, uv transform)"""
        d = s.B.get(*ref)
        _, _, brc, ka, kd, ks, base, rng, power = struct.unpack('<hhIHHHBBi', d[:20])
        mkids = s.B.c.chunks[ref]['kids']
        tm = s._kid('TMAP', 0, mkids)
        out = dict(base=base, range=rng, brc=brc, ka=ka / 65536, kd=kd / 65536, ks=ks / 65536)
        if tm:
            _, _, cbRow, typ, grf, xl, yt, dxp, dyp, xo, yo = struct.unpack('<hhhBBhhhhhh', tm[:20])
            px = np.frombuffer(tm[20:20 + cbRow * dyp], np.uint8).reshape(dyp, cbRow)[:, :dxp]
            out['image'] = s.pal[px]; out['index'] = px
            tx = s._kid('TXXF', 0, mkids)
            if tx: out['uvxf'] = np.array(struct.unpack('<6i', tx[4:28]), float).reshape(3, 2) * FX
        else:
            ramp = s.pal[base:base + max(rng, 1)]
            out['ramp'] = ramp
        return out

    def costume(s, choice=None):
        """per body part: material dict and an accessory model chid (or None)"""
        choice = choice or {}
        mats = [None] * len(s.parent); acc = [None] * len(s.parent)
        for ibset, cmids in enumerate(s.costumes):
            cmid = choice.get(ibset, cmids[0])
            ref = s._kidref('CMTL', cmid); ckids = s.B.c.chunks[ref]['kids']
            parts = [i for i, b in enumerate(s.bset) if b == ibset]
            for k, ibprt in enumerate(parts):
                m = s._kidref('MTRL', k, ckids)
                if m: mats[ibprt] = s.material(m)
                a = s._kidref('BMDL', k, ckids)
                if a: acc[ibprt] = a
        return mats, acc

    def pose(s, anid=0, icel=0, choice=None):
        """posed body parts in actor space: list of (V, UV, F, smooth, material, part index)"""
        cel, _ = s.cel(anid, icel)
        mats, acc = s.costume(choice)
        world = [None] * len(cel)
        def W(i):
            if world[i] is None:
                M = cel[i][1]; p = s.parent[i]
                world[i] = M @ W(p) if p >= 0 else M        # row vectors: v * local * parent
            return world[i]
        out = []
        for i, (chid, M) in enumerate(cel):
            ref = acc[i] if acc[i] else (s._kidref('BMDL', chid) if chid is not None else None)
            if not ref: continue
            V, UV, F, sm = model(s.B.get(*ref))
            if len(F) == 0: continue
            Vh = np.c_[V, np.ones(len(V))] @ W(i)
            out.append((Vh[:, :3], UV, F, sm, mats[i], i))
        return out

def smooth_by_groups(V, F, smooth):
    """per-corner normals the way BRender smooths: average the faces sharing a
    vertex whose smoothing-group bits overlap"""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros((len(F), 3, 3))
    by_v = {}
    for fi, f in enumerate(F):
        for v in f: by_v.setdefault(v, []).append(fi)
    for fi, f in enumerate(F):
        for c, v in enumerate(f):
            acc = sum(fn[g] for g in by_v[v] if g == fi or (smooth[g] & smooth[fi]))
            N[fi, c] = acc / (np.linalg.norm(acc) + 1e-12)
    return N

def to_meshes(parts, M=np.eye(4), name='actor'):
    """trimesh pieces (unindexed corners, textured or vertex-colored) for posed parts, placed by M"""
    import trimesh
    from PIL import Image
    out = []
    R = M[:3, :3]
    for V, UV, F, sm, m, i in parts:
        Vw = np.c_[V, np.ones(len(V))] @ M.T
        N = smooth_by_groups(V, F, sm) @ R.T
        P = Vw[F][:, :, :3].reshape(-1, 3); N = N.reshape(-1, 3)
        T = np.arange(len(P)).reshape(-1, 3)
        if m and 'image' in m:
            uv = UV
            if 'uvxf' in m: uv = np.c_[UV, np.ones(len(UV))] @ m['uvxf']
            uvc = uv[F].reshape(-1, 2)
            mat = trimesh.visual.material.PBRMaterial(baseColorTexture=Image.fromarray(m['image']), roughnessFactor=0.85, metallicFactor=0.0)
            vis = trimesh.visual.TextureVisuals(uv=np.c_[uvc[:, 0], 1 - uvc[:, 1]], material=mat)
        else:
            ramp = m['ramp'] if m else np.array([[200, 200, 200]])
            col = ramp[min(len(ramp) - 1, int(len(ramp) * 0.72))]
            mat = trimesh.visual.material.PBRMaterial(baseColorFactor=list(col / 255.0) + [1.0], roughnessFactor=0.85, metallicFactor=0.0)
            vis = trimesh.visual.TextureVisuals(uv=np.zeros((len(P), 2)), material=mat)
        mesh = trimesh.Trimesh(P, T, vertex_normals=N, visual=vis, process=False)
        out.append(('%s_part%02d' % (name, i), mesh))
    return out

if __name__ == '__main__':
    t = Template(sys.argv[1])
    an = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    print('rest', t.rest, 'parts', len(t.parent), 'sets', len(t.costumes), 'actions', len(t.actions))
    parts = t.pose(an, int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    allV = np.vstack([p[0] for p in parts])
    print('bounds', allV.min(0).round(2), allV.max(0).round(2), 'tris', sum(len(p[2]) for p in parts))
    for V, UV, F, sm, m, i in parts:
        desc = ('tex %dx%d' % m['image'].shape[1::-1]) if m and 'image' in m else ('ramp %d+%d %s' % (m['base'], m['range'], m['ramp'][len(m['ramp']) * 3 // 4]) if m else 'no material')
        print('  part %2d set %d parent %2d: %3d tris, %s' % (i, t.bset[i], t.parent[i], len(F), desc))
