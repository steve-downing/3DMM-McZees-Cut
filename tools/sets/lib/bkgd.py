"""Extract a 3DMM background: per camera view RGB, depth and camera pose."""
import sys, struct, subprocess, json, os, re
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import cfl
from paths import BKGDS, BASEPAL
KCD = os.path.join(os.path.dirname(__file__), 'kcd')

def _kcd():
    """the Kauai chunk decompressor (kcd.c), built on first use"""
    src = KCD + '.c'
    if not os.path.exists(KCD) or os.path.getmtime(KCD) < os.path.getmtime(src):
        subprocess.run(['cc', '-O2', '-o', KCD, src], check=True)
    return KCD

def base_palette():
    t = open(BASEPAL).read()
    t = t[t.index('kclrBasePalette'):]
    nums = [tuple(map(int, m)) for m in re.findall(r'\{(\d+), (\d+), (\d+), \d+\}', t)]
    return np.array([[r, g, b] for b, g, r in nums[:256]], np.uint8)

def fx(v): return v / 65536.0

class Bkgd:
    def __init__(s, path=BKGDS):
        s.c = cfl.CFL(path)
    def get(s, ctg, cno):
        d, p = s.c.data(ctg, cno)
        if p:
            r = subprocess.run([_kcd()], input=d, capture_output=True)
            if r.returncode: raise RuntimeError(r.stderr)
            d = r.stdout
        return d
    def names(s):
        out = {}
        for (ctg, cno) in s.c.chunks:
            if ctg == 'BKGD': out[cno] = s.c.name(ctg, cno)
        return out
    def views(s, cno):
        b = s.c.chunks[('BKGD', cno)]
        hdr = s.get('BKGD', cno)
        base = hdr[4]
        pal = base_palette().copy()
        for kc, kn, ch in b['kids']:
            if kc == 'GLCR':
                g = s.get(kc, kn)
                cbe, n = struct.unpack('<ii', g[4:12])
                for i in range(n):
                    bb, gg, rr, _ = g[12 + i*4:16 + i*4]
                    pal[base + i] = (rr, gg, bb)
        views = []
        for kc, kn, ch in sorted(b['kids'], key=lambda k: k[2]):
            if kc != 'CAM ': continue
            cam = s.get(kc, kn)
            hither, yon = [fx(v) for v in struct.unpack('<ii', cam[4:12])]
            afov = struct.unpack('<H', cam[12:14])[0]
            m = np.array([fx(v) for v in struct.unpack('<12i', cam[28:76])]).reshape(4, 3)
            kids = {k[0]: k[1] for k in s.c.chunks[(kc, kn)]['kids']}
            mb = s.get('MBMP', kids['MBMP'])
            l, t, r, bt = struct.unpack('<4i', mb[8:24])
            w, h = r - l, bt - t
            rowcb = struct.unpack('<%dh' % h, mb[28:28 + 2*h])
            p = 28 + 2*h
            idx = np.zeros((h, w), np.uint8)
            for y in range(h):
                row = mb[p:p + rowcb[y]]; p += rowcb[y]
                x = 0; i = 0; trans = True
                while i < len(row):
                    n = row[i]; i += 1
                    if not trans:
                        idx[y, x:x+n] = np.frombuffer(row[i:i+n], np.uint8); i += n
                    x += n; trans = not trans
            z = s.get('ZBMP', kids['ZBMP'])
            zw, zh = struct.unpack('<hh', z[8:12])
            zz = np.frombuffer(z[12:12 + zw*zh*2], np.uint16).reshape(zh, zw)
            views.append(dict(chid=ch, hither=hither, yon=yon, fov=afov * 2*np.pi / 65536,
                              mat=m, rgb=pal[idx], z=zz))
        return views

    def lights(s, cno):
        """the set's lights: type (0 point, 1 directional, 2 spot), intensity, 4x3 matrix
        (BRender rows; a light shines along its -z axis)"""
        b = s.c.chunks[('BKGD', cno)]
        out = []
        for kc, kn, ch in b['kids']:
            if kc != 'GLLT': continue
            g = s.get(kc, kn)
            cb, n = struct.unpack('<ii', g[4:12])
            for i in range(n):
                e = g[12 + i * cb:12 + (i + 1) * cb]
                m = np.array([fx(v) for v in struct.unpack('<12i', e[:48])]).reshape(4, 3)
                out.append(dict(type=struct.unpack('<i', e[52:56])[0], intensity=fx(struct.unpack('<i', e[48:52])[0]), mat=m))
        return out


def depth(v):
    a = (v['yon'] + v['hither']) / (v['yon'] - v['hither'])
    b = 2 * v['yon'] * v['hither'] / (v['yon'] - v['hither'])
    z = v['z'].astype(np.float64)
    d = b / (a - z / 32768.0)
    d[v['z'] >= 0x8000] = np.inf
    return d

def world_points(v):
    """camera-space -> world for every pixel; returns (H,W,3), valid mask"""
    h, w = v['z'].shape
    f = (h / 2) / np.tan(v['fov'] / 2)
    d = depth(v)
    ys, xs = np.mgrid[0:h, 0:w]
    xc = (xs + 0.5 - w/2) * d / f
    yc = -(ys + 0.5 - h/2) * d / f
    zc = -d
    P = np.stack([xc, yc, zc], -1)
    M = v['mat']
    W = P @ M[:3] + M[3]
    return W, np.isfinite(d)
