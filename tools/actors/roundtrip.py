"""Round trip: stock actor -> Blender -> exported add-on, compared with the original.

    python roundtrip.py <actor name> <work folder>

Checks the imported armature against 3DMM's posing math (check_actor.py), then
compares the exported .3cn with tmpls.3cn: body parts, every cel of every
action (posed triangles, uvs, step distance, flags), and every costume
(colors, textures, texture transforms, accessories). Exits 1 on a difference.
"""
import sys, os, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'sets', 'lib'))
from actor import Template, gg, gl, mat34  # noqa: E402
import import_actor, export_actor  # noqa: E402


def tris(parts):
    """posed triangles per part: rows of (3 positions, 3 uvs)"""
    return {i: np.concatenate([V[F].reshape(len(F), 9), UV[F].reshape(len(F), 6)], 1)
            for V, UV, F, sm, m, i in parts}


def tri_diff(a, b):
    """order-free: the worst distance from a triangle to its closest match on the other side"""
    if a.shape != b.shape: return float('inf')
    d = np.abs(a[:, None, :] - b[None, :, :]).max(-1)
    return max(d.min(1).max(), d.min(0).max())


def costume_desc(t, cmid):
    ref = t._kidref('CMTL', cmid); ck = t.B.c.chunks[ref]['kids']
    out = []
    for kc, kn, ch in sorted(ck, key=lambda k: (k[2], k[0])):
        if kc == 'MTRL':
            m = t.material((kc, kn))
            d = ('MTRL', ch, m['base'], m['range'])
            if 'image' in m: d += (m['image'].shape, int(m['image'].astype(int).sum()))
            if 'uvxf' in m: d += (tuple(np.round(m['uvxf'].ravel(), 3)),)
            out.append(d)
        elif kc == 'BMDL':
            from actor import model
            V, UV, F, sm = model(t.B.get(kc, kn)); out.append(('BMDL', ch, len(F)))
    return out


def compare(name, path):
    a = Template(name); b = Template(name, path)
    errs = []
    def check(ok, msg):
        if not ok: errs.append(msg)
    check(a.parent == b.parent, 'parents differ')
    check(a.bset == b.bset, 'body part sets differ')
    check(a.rest == b.rest, 'rest orientation differs')
    check([len(c) for c in a.costumes] == [len(c) for c in b.costumes], 'costume counts differ')
    for ca, cb in zip(a.costumes, b.costumes):
        for x, y in zip(ca, cb):
            check(costume_desc(a, x) == costume_desc(b, y), 'costume %d/%d differs:\n  %s\n  %s' % (x, y, costume_desc(a, x), costume_desc(b, y)))
    check(sorted(a.actions) == sorted(b.actions), 'action numbers differ')
    ncel = 0
    for anid in sorted(a.actions):
        check(a.actions[anid] == b.actions[anid], 'action %d name: %r vs %r' % (anid, a.actions[anid], b.actions[anid]))
        fa = struct.unpack('<hhi', a.B.get(*a._kidref('ACTN', anid))[:8])[2]
        fb = struct.unpack('<hhi', b.B.get(*b._kidref('ACTN', anid))[:8])[2]
        check(fa == fb, '%s flags %d vs %d' % (a.actions[anid], fa, fb))
        def cels(t):
            r = t._kidref('ACTN', anid); return gg(t._kid('GGCL', 0, t.B.c.chunks[r]['kids']))
        A, B = cels(a), cels(b)
        check(len(A) == len(B), '%s: %d vs %d cels' % (a.actions[anid], len(A), len(B)))
        for c in range(min(len(A), len(B))):
            da = struct.unpack('<ii', A[c][0])[1]; db = struct.unpack('<ii', B[c][0])[1]
            check(abs(da - db) <= 2, '%s cel %d: step %d vs %d' % (a.actions[anid], c, da, db))
            ta = tris(a.pose(anid, c)); tb = tris(b.pose(anid, c))
            check(sorted(ta) == sorted(tb), '%s cel %d: parts shown %s vs %s' % (a.actions[anid], c, sorted(ta), sorted(tb)))
            for i in ta:
                if i in tb:
                    d = tri_diff(ta[i], tb[i])
                    check(d < 0.002, '%s cel %d part %d differs by %.4f' % (a.actions[anid], c, i, d))
            ncel += 1
    print('%s: %d cels, %d costumes compared, %d differences' % (name, ncel, sum(map(len, a.costumes)), len(errs)))
    for e in errs[:15]: print('  ' + e)
    return not errs


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    name, work = args[0], args[1]
    os.makedirs(work, exist_ok=True)
    blend = os.path.join(work, name + '.blend')
    arm = import_actor.import_actor(name, blend)
    base = export_actor.Export(arm).run(work)
    ok = compare(name, base + '.3cn')
    import check_actor
    ok = check_actor.check(name, blend, every=True) and ok
    sys.exit(0 if ok else 1)
