"""Point a movie's actors at a different actor template.

    python retarget_movie.py <in.3mm> <out.3mm> --from <actor or 0xcno> --to <actor.3cn or 0xcno>

Every actor in the movie made from --from is played by --to instead: an
add-on actor (its .3cn, or its chunk number) or another stock actor. Actions
and costumes are referred to by number, so the new actor should have them in
the same order (an exported copy of the same actor does; a different one
plays whatever action has the same number).

Used by CI to check add-on actors: a sample movie, with its actor swapped
for an exported copy of itself, has to render the same frames.
"""
import sys, os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'sets', 'lib'))
import cfl  # noqa: E402
from paths import ROOT  # noqa: E402

SID_3DMM = 2                                   # the source id stock and add-on content both load under


def template_cno(spec):
    if spec.startswith('0x') or spec.isdigit(): return int(spec, 0)
    path = spec if spec.lower().endswith('.3cn') else os.path.join(ROOT, 'content-files', 'tmpls.3cn')
    c = cfl.CFL(path)
    found = [k[1] for k in c.chunks if k[0] == 'TMPL' and (path == spec or c.name(*k) == spec)]
    if len(found) != 1: raise SystemExit('%s: found %d actor templates' % (spec, len(found)))
    return found[0]


def retarget(src, dst, cno_from, cno_to):
    c = cfl.CFL(src); d = bytearray(c.d); n = 0
    for k, v in c.chunks.items():
        if k[0] != 'ACTR': continue
        if v['packed']: raise SystemExit('actor chunk %d is compressed; save the movie again from 3DMM first' % k[1])
        sid, pcrf, ctg, cno = struct.unpack_from('<iiII', d, v['fp'] + 28)
        if sid == SID_3DMM and ctg == int.from_bytes(b'TMPL', 'big') and cno == cno_from:
            struct.pack_into('<I', d, v['fp'] + 40, cno_to); n += 1
    if not n: raise SystemExit('no actors made from %#x in %s' % (cno_from, src))
    open(dst, 'wb').write(d)
    return n


if __name__ == '__main__':
    a = sys.argv[1:]
    src, dst = a[0], a[1]
    f = template_cno(a[a.index('--from') + 1]); t = template_cno(a[a.index('--to') + 1])
    print('%s: %d actors now use %#x (were %#x)' % (dst, retarget(src, dst, f, t), t, f))
