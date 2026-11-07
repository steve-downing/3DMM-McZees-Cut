import struct, sys
def tag(v): return struct.pack('>I', v).decode('latin1')
class CFL:
    def __init__(s, path):
        d = s.d = open(path,'rb').read()
        magic, creator = struct.unpack('<II', d[:8])
        fpMac, fpIndex, cbIndex = struct.unpack('<iii', d[16:28])
        g = d[fpIndex:fpIndex+cbIndex]
        bo, osk, ilocMac, bvMac, clocFree, cbFixed = struct.unpack('<hhiiii', g[:20])
        data = g[20:20+bvMac]; locs = g[20+bvMac:]
        s.chunks = {}
        for i in range(ilocMac):
            bv, cb = struct.unpack('<ii', locs[i*8:i*8+8])
            if bv < 0 or cb == 0: continue
            e = data[bv:bv+cb]
            if cbFixed == 20:
                ctg, cno, fp, lu, ckid, cref = struct.unpack('<IIIIHH', e[:20]); cbd = lu >> 8; grf = lu & 0xff
            else:
                ctg, cno, fp, cbd, ckid, cref, rti, grf = struct.unpack('<IIiiiiiI', e[:32])
            kids = []
            for k in range(ckid):
                kc, kn, chid = struct.unpack('<III', e[cbFixed+k*12:cbFixed+k*12+12]); kids.append((tag(kc), kn, chid))
            rest = e[cbFixed+ckid*12:]
            nm = rest[3:3+rest[2]].decode('latin1') if len(rest) > 3 else ''
            s.chunks[(tag(ctg), cno)] = dict(fp=fp, cb=cbd, grf=grf, kids=kids, packed=bool(grf & 4), name=nm)
    def data(s, ctg, cno):
        c = s.chunks[(ctg, cno)]; return s.d[c['fp']:c['fp']+c['cb']], c['packed']

    def name(s, ctg, cno): return s.chunks[(ctg, cno)]['name']
