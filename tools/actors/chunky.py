"""Write Kauai chunky files (.3cn content, .3th browser thumbnails) and the
small structures inside them. The reader is tools/sets/lib/cfl.py; the format
is kauai/src/chunk.cpp (version 5, compact index).

    w = Chunky()
    w.add('TMPL', 0x4d430000, data, name='McZee', loner=True)
    w.add('GLPI', 0x4d430001, data)
    w.adopt(('TMPL', 0x4d430000), ('GLPI', 0x4d430001), chid=0)
    w.save('mczee.3cn')
"""
import struct
import numpy as np

OSK = 0x0303                        # Windows, as every stock file says


def ctg(s):
    return int.from_bytes(s.encode('latin1'), 'big')


class Chunky:
    def __init__(s, creator='CHMP'):
        s.creator = creator; s.chunks = {}; s.kids = {}; s.refs = {}

    def add(s, tag, cno, data, name='', loner=False):
        key = (tag, cno)
        assert key not in s.chunks, 'chunk %s %#x added twice' % key
        s.chunks[key] = dict(data=bytes(data), name=name, loner=loner)
        s.kids[key] = []; s.refs.setdefault(key, 0)
        return key

    def adopt(s, parent, child, chid=0):
        assert parent in s.chunks and child in s.chunks, (parent, child)
        s.kids[parent].append((child, chid)); s.refs[child] = s.refs.get(child, 0) + 1

    def save(s, path):
        keys = sorted(s.chunks, key=lambda k: (ctg(k[0]), k[1]))
        body = bytearray(); fp = {}
        for k in keys:
            fp[k] = 128 + len(body); body += s.chunks[k]['data']
        entries = []
        for k in keys:
            c = s.chunks[k]; cb = len(c['data'])
            assert cb <= 0xFFFFFF
            kids = sorted(s.kids[k], key=lambda kc: (kc[1], ctg(kc[0][0]), kc[0][1]))
            e = struct.pack('<IIIIHH', ctg(k[0]), k[1], fp[k], (cb << 8) | (2 if c['loner'] else 0), len(kids), s.refs[k])
            for (kt, kn), chid in kids:
                e += struct.pack('<III', ctg(kt), kn, chid)
            if c['name']:
                n = c['name'].encode('latin1'); assert len(n) < 256
                e += struct.pack('<hB', OSK, len(n)) + n + b'\0'
            entries.append(e)
        data = bytearray(); locs = bytearray()
        for e in entries:
            locs += struct.pack('<ii', len(data), len(e)); data += e
            data += b'\0' * (-len(data) % 4)            # Kauai keeps group entries long-aligned
        index = struct.pack('<hhiiii', 1, OSK, len(entries), len(data), -1, 20) + data + locs
        fpIndex = 128 + len(body); fpMac = fpIndex + len(index)
        head = struct.pack('<4s4shhhhiiiii', b'CHN2', s.creator.encode()[::-1], 5, 4, 1, OSK,
                           fpMac, fpIndex, len(index), fpMac, 0)
        head += b'\0' * (128 - len(head))
        with open(path, 'wb') as f:
            f.write(head + body + index)


# ---- structures inside chunks -------------------------------------------

def fixed(x):
    return int(round(x * 65536))


def gl(entries, cb):
    """generic list: header then fixed-size entries"""
    return struct.pack('<hhii', 1, OSK, cb, len(entries)) + b''.join(entries)


def gg(entries, cb_fixed):
    """generic group: entries of (fixed bytes, variable bytes)"""
    data = bytearray(); locs = bytearray()
    for f, v in entries:
        e = f + v; assert len(f) == cb_fixed
        locs += struct.pack('<ii', len(data), len(e)); data += e
        data += b'\0' * (-len(data) % 4)
    return struct.pack('<hhiiii', 1, OSK, len(entries), len(data), -1, cb_fixed) + bytes(data) + bytes(locs)


def mat34(M_row):
    """a 4x4 row-vector matrix as BRender's 3x4 fixed point (4 rows of 3)"""
    return struct.pack('<12i', *[fixed(M_row[r, c]) for r in range(4) for c in range(3)])


def bmdl(V, UV, F, smooth):
    """BRender model: vertices (position, uv) and faces (3 indices, smoothing group)"""
    assert len(V) < 32768 and len(F) < 32768, 'model too big for 3DMM'
    out = bytearray(struct.pack('<hhhh', 1, OSK, len(V), len(F)) + b'\0' * 40)
    for (x, y, z), (u, v) in zip(V, UV):
        out += struct.pack('<5i', fixed(x), fixed(y), fixed(z), fixed(u), fixed(v)) + b'\0' * 12
    for (a, b, c), sm in zip(F, smooth):
        out += struct.pack('<3H', a, b, c) + b'\0' * 10 + struct.pack('<H', sm) + b'\0' * 14
    return bytes(out)


def mtrl(base, rng, textured):
    """BRender material: kd 1, the palette ramp for lighting, power 50"""
    return struct.pack('<hhIHHHBBi', 1, OSK, 0, 0, 0xFFFF, 0, base, rng, fixed(50))


def tmap(index):
    """8-bit texture: palette indices, rows padded to 4 bytes"""
    h, w = index.shape; row = (w + 3) & ~3
    px = np.zeros((h, row), np.uint8); px[:, :w] = index
    return struct.pack('<hhhBBhhhhhh', 1, OSK, row, 3, 2, 0, 0, w, h, 0, 0) + px.tobytes()


def txxf(uvxf):
    """texture transform: [u v 1] @ uvxf (3x2)"""
    return struct.pack('<hh', 1, OSK) + struct.pack('<6i', *[fixed(x) for x in np.asarray(uvxf).ravel()])


def mbmp(index, alpha):
    """Kauai masked bitmap: runs of opaque pixels per row"""
    h, w = index.shape
    rows = []
    for y in range(h):
        r = bytearray(); x = 0
        while x < w:
            skip = 0
            while x < w and not alpha[y, x]: x += 1; skip += 1
            if x >= w: break
            n = 0
            while x + n < w and alpha[y, x + n] and n < 255: n += 1
            while skip > 255: r += bytes([255, 0]); skip -= 255
            r += bytes([skip, n]) + bytes(index[y, x:x + n]); x += n
        rows.append(bytes(r))
    body = struct.pack('<%dh' % h, *[len(r) for r in rows]) + b''.join(rows)
    cb = 28 + len(body)
    return struct.pack('<hhBBhiiiii', 1, OSK, 0, 0, 0, 0, 0, w, h, cb) + body
