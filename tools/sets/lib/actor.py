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
        # 3DMM reads one entry per body part; a few stock cels carry extras
        cps = [struct.unpack('<hh', var[i * 4:i * 4 + 4]) for i in range(len(s.parent))]
        return [(None if ch == -1 else ch, xf[im]) for ch, im in cps], len(cels)

    def material(s, ref):
        """a MTRL chunk: solid color (palette ramp) or texture (RGB image, uv transform)"""
        d = s.B.get(*ref)
        _, _, brc, ka, kd, ks, base, rng, power = struct.unpack('<hhIHHHBBi', d[:20])
        mkids = s.B.c.chunks[ref]['kids']
        tm = s._kid('TMAP', 0, mkids)
        out = dict(ref=ref, base=base, range=rng, brc=brc, ka=ka / 65536, kd=kd / 65536, ks=ks / 65536)
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
            # the cel's model wins; a costume accessory shows only where the cel names none
            ref = s._kidref('BMDL', chid) if chid is not None else acc[i]
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

def part_mesh(V, UV, F, sm, m, cache=None, M=np.eye(4)):
    """one trimesh piece (unindexed corners) for a model with its material, placed by M.
    Materials are shared through cache (keyed by MTRL chunk) so exports don't repeat textures."""
    import trimesh
    from PIL import Image
    cache = {} if cache is None else cache
    Vw = np.c_[V, np.ones(len(V))] @ M.T
    N = smooth_by_groups(V, F, sm) @ M[:3, :3].T
    P = Vw[F][:, :, :3].reshape(-1, 3); N = N.reshape(-1, 3)
    T = np.arange(len(P)).reshape(-1, 3)
    key = m['ref'] if m else None
    if key not in cache:
        if m and 'image' in m:
            cache[key] = trimesh.visual.material.PBRMaterial(baseColorTexture=Image.fromarray(m['image']), roughnessFactor=0.85, metallicFactor=0.0)
        else:
            ramp = m['ramp'] if m else np.array([[200, 200, 200]])
            col = ramp[min(len(ramp) - 1, int(len(ramp) * 0.72))]     # a lit shade from the palette ramp
            cache[key] = trimesh.visual.material.PBRMaterial(baseColorFactor=list(col / 255.0) + [1.0], roughnessFactor=0.85, metallicFactor=0.0)
    if m and 'image' in m:
        uv = np.c_[UV, np.ones(len(UV))] @ m['uvxf'] if 'uvxf' in m else UV
        uvc = uv[F].reshape(-1, 2); uvc = np.c_[uvc[:, 0], 1 - uvc[:, 1]]
    else:
        uvc = np.zeros((len(P), 2))
    vis = trimesh.visual.TextureVisuals(uv=uvc, material=cache[key])
    return trimesh.Trimesh(P, T, vertex_normals=N, visual=vis, process=False)

def to_meshes(parts, M=np.eye(4), name='actor'):
    """trimesh pieces for posed parts (from Template.pose), placed by M"""
    cache = {}
    return [('%s_part%02d' % (name, i), part_mesh(V, UV, F, sm, m, cache, M)) for V, UV, F, sm, m, i in parts]

def rig(t):
    """Everything needed to play an actor in any costume. Returns a trimesh scene and a
    description (JSON-able):

    Scene: meshes m0, m1, ... = every (body part, model) pair any cel or costume uses,
    in the model's own space, with the model's raw texture coordinates; and one tiny
    placeholder mesh mat0, mat1, ... per costume material, to carry its color or texture.

      parents[part]            parent part, or -1 for the actor root
      meshes                   how many m<k> meshes there are
      mats[k].uvxf             that material's texture transform (6 numbers, rows of a
                               3x2 matrix: [u v 1] @ M) or null
      sets[s].label            where the body part set sits (Head, Top, Bottom, ...)
      sets[s].parts            its body parts, in order
      sets[s].options[o]       a costume: mats (material per part in the set, -1 none) and
                               acc (accessory mesh per part, shown where a cel says so, or -1)
      actions[k].xf            base64 little-endian float16, 12 per matrix: BRender 3x4
                               matrices, 4 rows of 3 (row-vector convention)
      actions[k].cels[c][part] [mesh, xf index]: mesh is m<k>, -1 for none, or -2 for the
                               part's costume accessory"""
    import trimesh, base64
    scene = trimesh.Scene(); meshes = {}
    plain = trimesh.visual.material.PBRMaterial(baseColorFactor=[1, 1, 1, 1], roughnessFactor=0.85, metallicFactor=0.0)
    def mesh_index(part, ref):
        if (part, ref) not in meshes:
            V, UV, F, sm = model(t.B.get(*ref))
            if len(F) == 0: meshes[(part, ref)] = -1
            else:
                k = sum(1 for v in meshes.values() if v >= 0)
                N = smooth_by_groups(V, F, sm).reshape(-1, 3)
                P = V[F].reshape(-1, 3); uv = UV[F].reshape(-1, 2)
                vis = trimesh.visual.TextureVisuals(uv=np.c_[uv[:, 0], 1 - uv[:, 1]], material=plain)
                m = trimesh.Trimesh(P, np.arange(len(P)).reshape(-1, 3), vertex_normals=N, visual=vis, process=False)
                scene.add_geometry(m, geom_name='m%d' % k, node_name='m%d' % k)
                meshes[(part, ref)] = k
        return meshes[(part, ref)]
    # costumes: every option of every body part set
    mats, mat_index, cache = [], {}, {}
    def material_index(ref):
        if ref not in mat_index:
            m = t.material(ref); k = len(mats)
            tri = trimesh.Trimesh([[0, -50, 0], [0.01, -50, 0], [0, -49.99, 0]], [[0, 1, 2]], process=False)
            stub = part_mesh(np.array(tri.vertices), np.zeros((3, 2)), np.array([[0, 1, 2]]), np.zeros(1, int), m, cache)
            scene.add_geometry(stub, geom_name='mat%d' % k, node_name='mat%d' % k)
            mats.append(dict(uvxf=[round(float(v), 6) for v in m['uvxf'].ravel()] if 'uvxf' in m else None))
            mat_index[ref] = k
        return mat_index[ref]
    rest, _ = t.cel(0, 0)
    world = {}
    def W(i):
        if i not in world: world[i] = rest[i][1] @ W(t.parent[i]) if t.parent[i] >= 0 else rest[i][1]
        return world[i]
    ys = [W(i)[3, 1] for i in range(len(t.parent))]; top = max(ys) or 1
    sets = []
    for ibset, cmids in enumerate(t.costumes):
        parts = [i for i, b in enumerate(t.bset) if b == ibset]
        opts = []
        for cmid in cmids:
            ref = t._kidref('CMTL', cmid); ckids = t.B.c.chunks[ref]['kids']
            mi, ai = [], []
            for k, p in enumerate(parts):
                m = t._kidref('MTRL', k, ckids); a = t._kidref('BMDL', k, ckids)
                mi.append(material_index(m) if m else -1)
                ai.append(mesh_index(p, a) if a else -1)
            opts.append(dict(mats=mi, acc=ai))
        h = np.mean([ys[p] for p in parts]) / top
        label = 'Head' if h > 0.8 else 'Top' if h > 0.5 else 'Bottom' if h > 0.2 else 'Feet'
        sets.append(dict(label=label, parts=parts, options=opts))
    seen = {}
    for st in sets:                                   # Head, Head 2, ...
        seen[st['label']] = seen.get(st['label'], 0) + 1
        if seen[st['label']] > 1: st['label'] += ' %d' % seen[st['label']]
    actions = []
    for anid in sorted(t.actions):
        a = t._kidref('ACTN', anid); akids = t.B.c.chunks[a]['kids']
        cels = gg(t._kid('GGCL', 0, akids))
        xf = np.array([struct.unpack('<12i', e) for e in gl(t._kid('GLXF', 0, akids))], float) * FX
        out = []
        for fixed, var in cels:
            row = []
            for part in range(len(t.parent)):         # 3DMM ignores extra entries
                chid, im = struct.unpack('<hh', var[part * 4:part * 4 + 4])
                if chid == -1: row.append([-2, im]); continue
                ref = t._kidref('BMDL', chid)
                row.append([mesh_index(part, ref) if ref else -1, im])
            out.append(row)
        actions.append(dict(name=t.actions[anid].rstrip(' *'), xf=base64.b64encode(xf.astype('<f2').tobytes()).decode(), cels=out))
    return scene, dict(parents=t.parent, meshes=sum(1 for v in meshes.values() if v >= 0), mats=mats, sets=sets, actions=actions)

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
