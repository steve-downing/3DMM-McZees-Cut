"""The cartoon airplane cabin (AD-Airplane Background) for VR.

    python toon.py [data_dir] [out.glb]

Reads the measured shell (shell.json, shell.jpg, shell_win.png, front.jpg,
rear.jpg from shell.py) and writes one glTF with the cabin, 12 seats, the jump
seat and two side tables. Shapes and colors follow ../STYLE.md."""
import sys, os, json, colorsys
import numpy as np
import trimesh
import mapbox_earcut as earcut
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from PIL import Image
from scipy import ndimage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from layout import INST, R, TABLES

from toonkit import *
from toonkit import CARTOON

# ----------------------------------------------------------------- seat
PAL = dict(fabric=half('#3b5bdb', (28, 30, 66)), fabric_hi=half('#5c7cfa', (44, 47, 92)), piping=(half('#d6a00f', (128, 106, 58)) + half('#a3abb5', (84, 84, 86))) / 2,
           wood=half('#eab676', (100, 91, 67)), metal=half('#b8c0c8', (70, 76, 80)), pocket=half('#e6b673', (124, 104, 74)),
           glass=half('#bfe3ff', (180, 174, 247)), frame=half('#fff3dc', (160, 150, 130)), door=half('#8fa3b8', (88, 92, 98)),
           porthole=half('#5f7389', (30, 32, 40)), winedge=half('#7d725c', (88, 82, 68)), handle=half('#e8e2d8', (150, 146, 140)), psu=half('#4a4a52', (40, 40, 44)), readlight=hexc('#fff6e0'), shade=half('#b3a382', (104, 96, 76)), dark=hexc('#2c2a36'), table=half('#eab676', (66, 59, 51)),
           wall=half('#f4e3c3', (104, 96, 81)), stripe=half('#6b85f0', (55, 58, 106)), recess=half('#e9cf9f', (104, 96, 81)),
           locker=half('#a3abb5', (84, 84, 86)), armframe=half('#d9c9a0', (112, 104, 82)), locker_in=half('#8a929c', (62, 62, 66)))

HW = 2.05            # headrest half-width
PW = 1.75            # light center panel half-width; gold stripes run just outside it
THK = 0.85           # backrest thickness
SW = 3.45            # seat half-width
BEV = 0.14           # backrest front bevel

def seat_back_outline():
    """front view of the backrest: shoulders, a concave scoop, then the headrest"""
    top, rc = 10.5, 0.95                                  # shoulder height, outer corner radius
    right = [(SW, 4.5), (SW - 0.08, top - rc)]
    right += [(SW - 0.08 - rc + rc * np.cos(a), top - rc + rc * np.sin(a)) for a in np.linspace(0, np.pi / 2, 6)][1:]   # big rounded corner
    right += [(HW + 0.3, top)]                                                                                     # flat top
    right += bezier((HW + 0.3, top), (HW, top), (HW, top + 0.45), 5)[1:].tolist()                                  # scoop up to the headrest
    right += [(HW, 11.7)] + [(HW - 0.9 + 0.9 * np.cos(a), 11.7 + 0.9 * np.sin(a)) for a in np.linspace(0, np.pi / 2, 6)][1:]   # big corner
    left = [(-x, y) for x, y in right[::-1]]
    return np.array(right + left[1:])

def build_small_seat():
    """the jump seat at the end of the aisle (measured): a cushion on four legs, a separate
    short backrest above it, and a grab bar across the top behind the backrest"""
    b = Builder()
    hw = 2.4
    out = np.array([(hw, 5.0), (hw, 8.5)] + [(hw - 0.5 + 0.5 * np.cos(a), 8.5 + 0.5 * np.sin(a)) for a in np.linspace(0, np.pi / 2, 4)][1:] +
                   [(-hw + 0.5 - 0.5 * np.cos(a), 8.5 + 0.5 * np.sin(a)) for a in np.linspace(np.pi / 2, 0, 4)][:-1] + [(-hw, 8.5), (-hw, 5.0)])
    zb_lo, zb_hi, th = 1.25, 0.75, 0.85
    V, F = reclined_extrusion(out, 5.0, 9.0, zb_lo, zb_hi, th, 0.15)
    n = len(out); F = np.asarray(F)
    tag = np.r_[np.zeros(4 * n), np.ones(len(F) - 4 * n)].astype(int)      # 0 rim, 1 front/back
    V, F, tag = split_x(np.asarray(V, float), F, tag, [-1.12, -0.85, 0.85, 1.12])
    cen = V[F].mean(1); cx = np.abs(cen[:, 0]); painted = (tag > 0) | (cen[:, 1] > 7.0)   # faces, back, and the top
    band = painted & (cx > 0.85) & (cx < 1.12); pan = painted & (cx < 0.85)
    b.add(V, F[band], PAL['piping'], kind=1); b.add(V, F[pan], PAL['fabric_hi'], kind=1)
    b.add(V, F[~band & ~pan], PAL['fabric'], kind=1)
    # frame: two uprights behind the backrest carrying the grab bar, and a crosspiece
    # in the gap between backrest and cushion
    for sx in (-1, 1):
        b.add_mesh(cbox(sx * 1.4 - 0.12, sx * 1.4 + 0.12, 4.3, 9.7, 0.2, 0.45, 0.04), PAL['metal'], kind=4)
    b.add_mesh(cbox(-1.52, 1.52, 9.25, 9.75, 0.2, 0.45, 0.06), PAL['metal'], kind=4)
    b.add_mesh(cbox(-1.55, 1.55, 4.35, 5.0, 0.2, 1.65, 0.05), PAL['metal'], kind=4)
    # cushion with lighter panel and grey stripes
    b.add_mesh(hull([(sx * 2.6, y, z) for sx in (-1, 1) for (y, z) in ((2.8, 1.3), (4.25, 1.3), (4.3, 4.9), (4.0, 5.45), (3.2, 5.45), (2.8, 5.05))]), PAL['fabric'], kind=1)
    wrap_strips(b, [(4.254, 1.6), (4.3, 4.9), (4.0, 5.45), (3.2, 5.45), (2.85, 5.1)],
                [(-0.85, 0.85, 0.0, 0.08, PAL['fabric_hi'], 1), (0.85, 1.12, -0.01, 0.11, PAL['piping'], 1), (-1.12, -0.85, -0.01, 0.11, PAL['piping'], 1)])
    b.add_mesh(cbox(-1.6, 1.6, 2.45, 2.8, 1.5, 4.6, 0.05), PAL['metal'], kind=4)
    # four legs with crossbars
    for sx in (-1, 1):
        for z in (1.5, 4.1):
            b.add_mesh(cbox(sx * 1.9 - 0.13, sx * 1.9 + 0.13, 0.0, 2.85, z - 0.13, z + 0.13, 0.04), PAL['metal'], kind=4)
        b.add_mesh(cbox(sx * 1.9 - 0.1, sx * 1.9 + 0.1, 0.45, 0.68, 1.5, 4.1, 0.03), PAL['metal'], kind=4)
    for z in (1.5, 4.1):
        b.add_mesh(cbox(-1.9, 1.9, 2.3, 2.55, z - 0.1, z + 0.1, 0.03), PAL['metal'], kind=4)
    return b.meshes()['lit']

def build_seat():
    b = Builder()
    # Backrest. The panel and gold stripes are painted on (mesh split along their edges),
    # front and back. The stripes sit at the edge of the headrest, so above the shoulders they
    # flow around the bevel onto its sides, stopping short of the top. The headrest keeps
    # the same thickness and is just nudged forward.
    P = seat_back_outline()
    if 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]) < 0: P = P[::-1]
    V, F = reclined_extrusion(P, 4.5, 12.6, 0.85, 0.35, THK, BEV)
    n = len(P); F = np.asarray(F)
    tag = np.r_[np.zeros(4 * n), np.full(n - 2, 2), np.full(len(F) - 4 * n - (n - 2), 1)].astype(int)   # 0 rim, 1 front, 2 back
    GO = HW + 0.2; YEND = 11.75
    V, F, tag = split_x(np.asarray(V, float), F, tag, [-GO, -PW, PW, GO])
    V, F, tag = split_x(V, F, tag, list(np.linspace(10.5, 11.3, 4)) + [YEND], axis=1)
    bulge = lambda y: 0.15 * float(np.clip((y - 10.5) / 0.8, 0, 1)) ** 2 * (3 - 2 * float(np.clip((y - 10.5) / 0.8, 0, 1)))
    V[:, 2] += np.array([bulge(y) for y in V[:, 1]])
    cen = V[F].mean(1); cx = np.abs(cen[:, 0])
    gold = (cx > PW) & (cx < GO)
    pan = (cx < PW) & ((tag > 0) | (cen[:, 1] > 10.0))           # front, back, and over the top
    b.add(V, F[gold], PAL['piping'], kind=1); b.add(V, F[pan], PAL['fabric_hi'], kind=1)
    b.add(V, F[~gold & ~pan], PAL['fabric'], kind=1)
    # back pocket on the rear
    pocket = hull([(sx * 2.5, y, 0.85 - (y - 4.5) / 8.05 * 0.5 - dz) for sx in (-1, 1) for y in (5.2, 9.2) for dz in (0.0, 0.24)])
    b.add_mesh(pocket, PAL['pocket'], kind=3)
    # cushion with a rounded front
    cush = hull([(sx * (SW - 0.05), y, z) for sx in (-1, 1) for (y, z) in ((3.3, 1.2), (4.7, 1.2), (4.75, 5.6), (4.45, 6.15), (3.75, 6.15), (3.3, 5.7))])
    b.add_mesh(cush, PAL['fabric'], kind=1)
    xi = PW
    wrap_strips(b, [(4.709, 2.0), (4.75, 5.6), (4.45, 6.15), (3.75, 6.15), (3.35, 5.75)],
                [(-xi, xi, 0.0, 0.1, PAL['fabric_hi'], 1), (xi, xi + 0.3, -0.01, 0.14, PAL['piping'], 1), (-xi - 0.3, -xi, -0.01, 0.14, PAL['piping'], 1)])
    # armrests and their front posts
    for sx in (-1, 1):
        b.add_mesh(cbox(SW - 0.2 if sx > 0 else -SW - 0.62, SW + 0.62 if sx > 0 else -SW + 0.2, 6.8, 7.1, 0.9, 5.1, 0.08), PAL['wood'], kind=3)
        xa = sx * (SW + 0.21)
        b.add_mesh(cbox(xa - 0.1, xa + 0.1, 3.4, 6.82, 1.1, 1.34, 0.04), PAL['metal'], kind=4)          # back post
        b.add_mesh(hull([(xa + dx, y, z) for dx in (-0.1, 0.1) for y, z in ((3.85, 3.2), (3.85, 3.45), (6.82, 4.05), (6.82, 4.3))]), PAL['metal'], kind=4)   # angled front strut
        b.add_mesh(cbox(xa - 0.12, xa + 0.12, 3.4, 3.85, 1.1, 5.1, 0.06), PAL['metal'], kind=4)           # bottom rail
    # legs and crossbars
    for sx in (-1, 1):
        for z, lean in ((1.9, -0.45), (4.65, 0.45)):
            b.add_mesh(hull([(sx * 2.05 + dx, y, z + dz + (lean if y == 0.0 else 0.0)) for dx in (-0.14, 0.14) for dz in (-0.14, 0.14) for y in (0.0, 3.35)]), PAL['metal'], kind=4)
    return b.meshes()['lit']

# ----------------------------------------------------------------- shell
def build(d, out):
    sh = json.load(open(os.path.join(d, 'shell.json')))
    loop = np.array(sh['loop']); s = np.array(sh['s']); S = s[-1]
    Z0, Z1, ZD, RES, A = sh['Z0'], sh['Z1'], sh['ZDOOR'], sh['RES'], sh['ARCH']
    tex = np.asarray(Image.open(os.path.join(d, 'shell.jpg')), float)[::-1]    # rows = z, cols = s
    win = np.asarray(Image.open(os.path.join(d, 'shell_win.png'))) > 127
    b = Builder()

    # color bands across the cross-section: per-s median color, segmented into runs
    cols = np.zeros((tex.shape[1], 3))
    for i in range(tex.shape[1]):
        m = ~win[:, i]
        cols[i] = np.median(tex[m, i] if m.sum() > 10 else tex[:, i], axis=0)
    cols = ndimage.median_filter(cols, size=(15, 1))
    # k-means on column colors
    rng = np.random.default_rng(0); K = 7
    cent = cols[rng.choice(len(cols), K, replace=False)]
    for _ in range(30):
        lab = np.argmin(((cols[:, None] - cent[None]) ** 2).sum(-1), 1)
        cent = np.array([cols[lab == k].mean(0) if (lab == k).any() else cent[k] for k in range(K)])
    lab = ndimage.median_filter(lab, size=9, mode='nearest')
    # runs, merging short ones; symmetric: use the left half mirrored onto the right
    nhalf = len(lab) // 2
    lab[len(lab) - nhalf:] = lab[:nhalf][::-1]
    runs = []; st = 0
    for i in range(1, len(lab) + 1):
        if i == len(lab) or lab[i] != lab[st]:
            runs.append([st, i, lab[st]]); st = i
    minlen = int(1.0 / RES)
    merged = []
    for r in runs:
        if merged and (r[1] - r[0] < minlen or r[2] == merged[-1][2]):
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    def run_y(r):
        sv = (r[0] + r[1]) / 2 * RES; i = int(np.clip(np.searchsorted(s, sv) - 1, 0, len(s) - 2))
        return (loop[i] + (sv - s[i]) / (s[i + 1] - s[i]) * (loop[i + 1] - loop[i]))[1]
    changed = True
    while changed:
        changed = False
        for i in range(1, len(merged) - 1):
            if run_y(merged[i]) > 0.6 or (merged[i][1] - merged[i][0]) * RES > 2.0: continue
            a_, m_, c_ = cent[merged[i - 1][2]], cent[merged[i][2]], cent[merged[i + 1][2]]
            dd = c_ - a_; t = np.dot(m_ - a_, dd) / max(np.dot(dd, dd), 1e-9)
            if 0.15 < t < 0.85 and np.linalg.norm(m_ - a_ - t * dd) < 12:
                j = i - 1 if np.linalg.norm(m_ - a_) <= np.linalg.norm(m_ - c_) else i + 1
                lo, hi = min(i, j), max(i, j)
                merged[lo] = [merged[lo][0], merged[hi][1], merged[j][2]]; del merged[hi]
                changed = True; break
    mi = next(i for i, r in enumerate(merged) if r[0] <= len(lab) // 2 < r[1])     # the aisle runner
    grow = int(0.35 / RES)
    merged[mi][0] -= grow; merged[mi - 1][1] -= grow; merged[mi][1] += grow; merged[mi + 1][0] += grow
    print('shell bands:', len(merged))
    # simplified profile, with vertices added at band boundaries
    mid_i = len(loop) // 2
    simp = np.vstack([dp(loop[:mid_i + 1], 0.3)[:-1], dp(loop[mid_i:], 0.3)])
    # the lower side walls run straight down to the floor (no kick step)
    for sg in (-1, 1):
        side = loop[sg * loop[:, 0] > 20]
        def xat(yv):
            k_ = np.argmin(np.abs(side[:, 1] - yv)); return side[k_, 0]
        x6, x0 = xat(6.15), side[np.argmin(np.abs(side[:, 1]) + 10 * (side[:, 1] > 0.02))][0]
        m_ = (sg * simp[:, 0] > 20) & (simp[:, 1] > 0.02) & (simp[:, 1] < 6.15)
        simp[m_, 0] = x0 + (x6 - x0) * simp[m_, 1] / 6.15
    ss = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(simp, axis=0), axis=1))]) * S / np.sum(np.linalg.norm(np.diff(simp, axis=0), axis=1))
    extra = []
    for yc in (0.9, 6.15, 7.0):                       # band edges on the side walls
        for i in range(len(simp) - 1):
            p_, q_ = simp[i], simp[i + 1]
            if abs(p_[0]) > 20 and (p_[1] - yc) * (q_[1] - yc) < 0:
                extra.append(ss[i] + (yc - p_[1]) / (q_[1] - p_[1]) * (ss[i + 1] - ss[i]))
    cuts = sorted(set([r[0] * RES for r in merged] + ss.tolist() + extra + [S]))
    green = cent[max(merged, key=lambda r: (r[1] - r[0]) if run_y(r) < 0.6 else -1)[2]]
    carpet = half(toon(green), green)
    def at(sv):
        i = np.clip(np.searchsorted(ss, sv) - 1, 0, len(simp) - 2)
        t = (sv - ss[i]) / max(ss[i + 1] - ss[i], 1e-9)
        return simp[i] + t * (simp[i + 1] - simp[i]), simp[i + 1] - simp[i]
    # windows: six per side. Their openings are cut out of the wall.
    s_lo, s_hi = 30.1, 34.65; zc = [23.67 - 7.2 * k for k in range(6)]; zl = 2.75
    win_s = [(s_lo, s_hi), (S - s_hi, S - s_lo)]
    win_out = {sd: [Polygon(rrect(lo_ - 0.14, hi_ + 0.14, z, zl + 0.14, 1.0)) for z in zc] for sd, (lo_, hi_) in enumerate(win_s)}
    holes = unary_union([p_ for v in win_out.values() for p_ in v])
    floor_segs = []
    for a_, b_ in zip(cuts[:-1], cuts[1:]):
        if b_ - a_ < 1e-6: continue
        mid = (a_ + b_) / 2
        k = int(np.clip(mid / RES, 0, len(lab) - 1))
        band = [r for r in merged if r[0] <= k < r[1]]
        c = toon(cent[band[0][2]] if band else cols[k])
        pa, _ = at(a_); pb, _ = at(b_)
        # walls, bins and ceiling: lean toward a warm cream; the floor keeps its colors
        ym = (pa[1] + pb[1]) / 2
        cream = hexc('#f6e8cf')
        if ym > 15.5:
            c = c * 0.25 + cream * 0.75
        elif ym > 0.6:
            c = c * 0.55 + cream * 0.45
        V = [[pa[0], pa[1], Z0], [pb[0], pb[1], Z0], [pb[0], pb[1], Z1], [pa[0], pa[1], Z1]]
        orig = cent[band[0][2]] if band else cols[k]
        bright = colorsys.rgb_to_hsv(*(orig / 255))[2] > 0.82 and ym > 15
        if bright: c = hexc('#fffaf0')
        else: c = half(c, orig)
        is_floor = max(pa[1], pb[1]) < 0.05
        if abs(pa[0] + pb[0]) / 2 > 20 and 14.0 < ym < 16.6:            # grey wall above the windows
            o_ = np.array([101, 93, 85.]); c = half(toon(o_) * 0.55 + cream * 0.45, o_)
        kd = 2 if is_floor else 0
        if not is_floor and abs(pa[0] + pb[0]) / 2 > 20 and ym < 7.0:     # lower side wall
            if ym > 6.15: c = half('#3b3936', (38, 37, 36))                 # dark band under the tan panel
            elif ym < 0.9: c = half('#2f312f', (26, 28, 27))                # dark baseboard, down to the floor
            else: c, kd = carpet, 2                                         # same carpet as the floor
        strip = box(a_, Z0, b_, Z1)
        if not is_floor and strip.intersects(holes):
            g_ = strip.difference(holes)
            for poly in (getattr(g_, 'geoms', None) or [g_]):
                v2, tr = tri_poly(poly)
                t_ = ((v2[:, 0] - a_) / (b_ - a_))[:, None]
                xy = pa[None] + t_ * (pb - pa)[None]
                b.add(np.c_[xy, v2[:, 1]], tr, c, 'glow' if bright else 'lit', kind=kd)
        else:
            b.add(V, [[0, 1, 2], [0, 2, 3]], c, 'glow' if bright else 'lit', kind=kd)
        if is_floor: floor_segs.append((min(pa[0], pb[0]), max(pa[0], pb[0]), c))

    def surf(sv, z, off):
        p, t = at(sv); n = np.array([-t[1], t[0]]); n /= np.linalg.norm(n)   # inward for this loop direction
        q = p + n * off
        return [q[0], q[1], z]
    def rounded(s0, s1, z0, z1, r, off):
        pts = []
        for (cs, cz, a0) in ((s1 - r, z1 - r, 0), (s0 + r, z1 - r, 90), (s0 + r, z0 + r, 180), (s1 - r, z0 + r, 270)):
            for a in np.radians(np.arange(a0, a0 + 91, 45)):
                pts.append((cs + r * np.cos(a), cz + r * np.sin(a)))
        return pts
    def pane(s0, s1, zc_, zh, r, off, color, group, n=10, round_bottom=True):
        """rounded rectangle on the wall, as strips across s so it hugs the curve"""
        svals = np.linspace(s0, s1, n + 1)
        def half(sv):
            dist = min(sv - s0, s1 - sv) if round_bottom else sv - s0
            return zh - r + np.sqrt(max(r * r - max(r - dist, 0) ** 2, 0)) if dist < r else zh
        V = []; F = []
        for sv in svals:
            h = half(sv); V += [surf(sv, zc_ - h, off), surf(sv, zc_ + h, off)]
        for i in range(n):
            a = 2 * i; F += [[a, a + 2, a + 3], [a, a + 3, a + 1]]
        b.add(V, F, color, group)
    shade_rng = np.random.default_rng(5)
    for side in (0, 1):
        for z in zc:
            fr = float(shade_rng.uniform(0.06, 0.25))
            lo_, hi_ = win_s[side]
            outer = rrect(lo_ - 0.14, hi_ + 0.14, z, zl + 0.14, 1.0)
            ring = Polygon(outer).difference(Polygon(rrect(lo_, hi_, z, zl, 0.9)))
            v2, tr = tri_poly(ring)                                   # thin dark surround
            b.add([surf(sv_, zz_, 0.04) for sv_, zz_ in v2], tr, PAL['winedge'])
            Vr = []                                                   # the reveal, out through the wall
            for sv_, zz_ in outer: Vr += [surf(sv_, zz_, 0.04), surf(sv_, zz_, -0.35)]
            m_ = len(outer)
            b.add(Vr, [[2 * i, 2 * ((i + 1) % m_), 2 * ((i + 1) % m_) + 1] for i in range(m_)] + [[2 * i, 2 * ((i + 1) % m_) + 1, 2 * i + 1] for i in range(m_)], PAL['winedge'])
            # the shade: fills the opening's top edge to edge (tucked under the surround)
            hgt = hi_ - lo_
            band_ = box(lo_ - 0.2, Z0 - 1, lo_ + fr * hgt, Z1 + 1) if side == 0 else box(hi_ - fr * hgt, Z0 - 1, hi_ + 0.2, Z1 + 1)
            shade = Polygon(rrect(lo_ - 0.07, hi_ + 0.07, z, zl + 0.07, 0.95, 9)).intersection(band_)
            v2, tr = tri_poly(shade)
            b.add([surf(sv_, zz_, 0.08) for sv_, zz_ in v2], tr, PAL['shade'])
    # blue stripe along the length of the cabin, high on each side of the raised ceiling
    for s0_, s1_ in ((11.2, 11.9), (S - 11.9, S - 11.2)):
        sv = np.linspace(s0_, s1_, 3); Vb = []
        for sv_ in sv: Vb += [surf(sv_, Z0, 0.03), surf(sv_, Z1, 0.03)]
        b.add(Vb, [[0, 2, 3], [0, 3, 1], [2, 4, 5], [2, 5, 3]], PAL['stripe'])
    # overhead bins: a handle on each bin door (above the blue stripe), and a dark service
    # panel with two reading lights under the bins above each row of seats
    for sg in (-1, 1):
        for z in [(zc[i] + zc[i + 1]) / 2 for i in (0, 2, 4)]:
            p0 = np.array(surf(12.55 if sg < 0 else S - 12.55, z, 0.0)); p1 = np.array(surf(12.55 if sg < 0 else S - 12.55, z, 0.12))
            nrm_ = p1 - p0
            pts = [p0 + nrm_ * t + np.array([0, dy, dz]) for t in (0.0, 1.0) for dy in (-0.16, 0.16) for dz in (-0.75, 0.75)]
            b.add_mesh(hull(pts), PAL['handle'], kind=4)
        for zr in (-16.4 + 1.6, -1.0 + 1.6, 26.56 - 1.6):
            xm_ = sg * 14.3
            b.add_mesh(cbox(xm_ - 1.9, xm_ + 1.9, 19.88, 20.02, zr - 1.1, zr + 1.1, 0.03), PAL['psu'], kind=4)
            for dx in (-0.8, 0.8):
                b.add_mesh(cbox(xm_ + dx - 0.25, xm_ + dx + 0.25, 19.84, 19.9, zr - 0.25, zr + 0.25, 0.02), PAL['readlight'], 'glow')
    # light rail along each side wall under the windows, at a seated shoulder height
    def wall_x(y):
        xs_ = [p[0] + (y - p[1]) / (q[1] - p[1]) * (q[0] - p[0]) for p, q in zip(simp[:-1], simp[1:]) if (p[1] - y) * (q[1] - y) <= 0 and abs(q[1] - p[1]) > 1e-9]
        return min(xs_), max(xs_)
    rail = half('#f2ede6', (156, 151, 144))
    (l0, r0), (l1, r1) = wall_x(8.85), wall_x(9.3)
    xl, xr = max(l0, l1), min(r0, r1)
    for xw, sg in ((xl, 1), (xr, -1)):                  # a round bar, eight-sided
        cyl = [(xw + sg * 0.12 + 0.25 * np.cos(a), 9.07 + 0.25 * np.sin(a), z_) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False) + np.pi / 8 for z_ in (Z0, Z1)]
        b.add_mesh(hull(cyl), rail, kind=4)

    # end walls
    simp_ring = simp[:-1]
    def stripes(img_path, e, zwall, normal_z, hole=None):
        img = np.asarray(Image.open(os.path.join(d, img_path)), float)[::-1]
        base = PAL['wall']
        blue = img[..., 2] - (img[..., 0] + img[..., 1]) / 2
        band = blue[int(7 / RES):int(16 / RES)].mean(0)
        on = ndimage.median_filter(band > 12, size=3)
        out = []
        st = None
        for i in range(len(on) + 1):
            if i < len(on) and on[i] and st is None: st = i
            if (i == len(on) or not on[i]) and st is not None:
                if i - st >= 2:
                    x0 = e['x0'] + st * RES; x1 = e['x0'] + i * RES
                    col = blue[:, st:i].mean(1); ys = np.nonzero(ndimage.median_filter(col > 12, size=9))[0]
                    if len(ys): out.append((x0, x1, ys.min() * RES, (ys.max() + 1) * RES))
                st = None
        stripe_color = PAL['stripe']
        return base, out, stripe_color
    def wall(zw, holes, base):
        verts = np.vstack([simp_ring] + holes); ends = np.cumsum([len(simp_ring)] + [len(h) for h in holes]).astype(np.uint32)
        T = earcut.triangulate_float64(verts, ends).reshape(-1, 3)
        b.add(np.c_[verts, np.full(len(verts), zw)], T, base)
    def arch_pts(n=12):
        xc, hw, sp = A['xc'], A['hw'], A['spring']
        return np.array([(xc + hw, 0.0), (xc + hw, sp)] + [(xc + hw * np.cos(t), sp + hw * np.sin(t)) for t in np.linspace(0, np.pi, n)[1:-1]] + [(xc - hw, sp), (xc - hw, 0.0)])
    arch = arch_pts()
    def inside_profile_y(x):
        # top of the cabin at x (from the simplified ring)
        ys = []
        for p, q in zip(simp_ring, np.roll(simp_ring, -1, 0)):
            if (p[0] - x) * (q[0] - x) <= 0 and abs(q[0] - p[0]) > 1e-9:
                ys.append(p[1] + (x - p[0]) / (q[0] - p[0]) * (q[1] - p[1]))
        return max(ys) if ys else 0
    # rear wall compartments (measured from the renders): four overhead
    # lockers and a tall panel behind the small seat, recessed 0.7
    cx_ = -0.4; ZR = Z1 + 0.69
    lockers = [(cx_ + c - 3.95, cx_ + c + 3.95, 13.4, 17.15) for c in (-14.62, -4.74, 4.74, 14.62)]
    lower = (cx_ - 6.8, cx_ + 6.8, 1.05, 10.8)
    rects = lockers + [lower]
    for name, zw, nz in (('front', Z0, 1), ('rear', Z1, -1)):
        e = sh['ends'][name]
        base, strs, scol = stripes(name + '.jpg', e, zw, nz)
        if name == 'front':
            rb, rstr, _ = stripes('rear.jpg', sh['ends']['rear'], Z1, -1)
            centers = np.array(sorted((a + c) / 2 for a, c, _, _ in rstr)); widths = [c - a for a, c, _, _ in rstr]
            d_ = np.diff(centers); period = float(np.median(d_[(d_ > 0.8) & (d_ < 3.5)]))
            sw = max(float(np.median(widths)), 0.44)
            phase = float(np.median((centers - cx_) % period))
            xmin, xmax = simp_ring[:, 0].min(), simp_ring[:, 0].max()
            even = [cx_ + phase + k * period for k in range(int((xmin - cx_) / period) - 2, int((xmax - cx_) / period) + 3)]
            even = [c for c in even if xmin + 0.3 < c < xmax - 0.3]
            print('stripe period %.2f width %.2f count %d' % (period, sw, len(even)))
        if name == 'front':
            fc = sorted((a + c) / 2 for a, c, _, _ in strs if c - a > 0.2)
            fc = [c for k, c in enumerate(fc) if (k == 0 or c - fc[k - 1] > 0.8) and abs(c) < 23.0]
            even_fc = []
            for sd in (-1, 1):                                  # fit c = a + p*k on each side of the door
                cs = np.array(sorted([c for c in fc if c * sd > 0], key=lambda c: abs(c)))
                k_ = np.arange(len(cs)); pf = np.polyfit(k_, cs, 1)
                even_fc += list(np.polyval(pf, k_))
            fc = sorted(even_fc)
            fw = max(float(np.median([c - a for a, c, _, _ in strs if c - a > 0.2])), 0.44)
            strs = [(c - fw / 2, c + fw / 2, 0.05, 99.0) for c in fc]
            print('front stripes at', np.round(fc, 2))
        else:
            strs = [(c - sw / 2, c + sw / 2, 0.05, 99.0) for c in even]
        holes = [arch] if name == 'front' else [np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]) for x0, x1, y0, y1 in rects]
        wall(zw, holes, base)
        for (x0, x1, y0, y1) in strs:
            if name == 'front' and abs((x0 + x1) / 2 - A['xc']) < A['hw'] + 3.7: continue
            zz = zw + nz * 0.03
            xm = (x0 + x1) / 2; hw_ = max((x1 - x0) / 2, 0.22); x0, x1 = xm - hw_, xm + hw_
            t0, t1 = inside_profile_y(x0) - 0.02, inside_profile_y(x1) - 0.02
            ytop = min(t0, t1)
            if ytop - y0 < 1: continue
            # keep stripes out of the compartment openings
            pieces = [(x0, x1, y0, ytop)]
            if name == 'rear':
                for rx0, rx1, ry0, ry1 in rects:
                    nxt = []
                    for xa, xb, ya, yb in pieces:
                        if not (xb > rx0 and xa < rx1 and yb > ry0 and ya < ry1): nxt.append((xa, xb, ya, yb)); continue
                        nxt += [(xa, xb, ya, ry0), (xa, xb, ry1, yb), (xa, min(xb, rx0), max(ya, ry0), min(yb, ry1)), (max(xa, rx1), xb, max(ya, ry0), min(yb, ry1))]
                    pieces = [q for q in nxt if q[1] - q[0] > 0.08 and q[3] - q[2] > 0.08]
            for xa, xb, ya, yb in pieces:
                if yb >= ytop - 1e-6:
                    lerp = lambda x: t0 + (t1 - t0) * (x - x0) / (x1 - x0)
                    ta, tb_ = lerp(xa), lerp(xb)
                else: ta, tb_ = yb, yb
                b.add([[xa, ya, zz], [xb, ya, zz], [xb, tb_, zz], [xa, ta, zz]], [[0, 1, 2], [0, 2, 3]], scol)
        print(name, 'stripes', len(strs))
    for i, (x0, x1, y0, y1) in enumerate(rects):
        # recess sides, back panel, handle
        for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
            b.add([[ax, ay, Z1], [bx, by, Z1], [bx, by, ZR], [ax, ay, ZR]], [[0, 1, 2], [0, 2, 3]], PAL['locker_in'])
        b.add([[x0, y0, ZR], [x1, y0, ZR], [x1, y1, ZR], [x0, y1, ZR]], [[0, 1, 2], [0, 2, 3]], PAL['locker'])
        xm_ = (x0 + x1) / 2
        if i >= len(lockers): continue
        hy = y0 + 0.45
        b.add_mesh(cbox(xm_ - 0.9, xm_ + 0.9, hy - 0.12, hy + 0.12, ZR - 0.28, ZR, 0.05), PAL['metal'], kind=4)
    # door recess, door, porthole
    fimg = np.asarray(Image.open(os.path.join(d, 'front.jpg')), float)[::-1]
    e = sh['ends']['front']
    def fcol(x, y): return fimg[int(np.clip(y / RES, 0, fimg.shape[0] - 1)), int(np.clip((x - e['x0']) / RES, 0, fimg.shape[1] - 1))]
    frame = toon(np.median([fcol(A['xc'] + A['hw'] + 0.4, y) for y in np.arange(2, 16, 0.5)], axis=0))
    for i in range(len(arch) - 1):
        a_, b_ = arch[i], arch[i + 1]
        b.add([[a_[0], a_[1], Z0], [b_[0], b_[1], Z0], [b_[0], b_[1], ZD], [a_[0], a_[1], ZD]], [[0, 1, 2], [0, 2, 3]], PAL['recess'])
    runner = toon(np.median([fcol(A['xc'], 0.2)] * 1, axis=0))
    x0r, x1r = A['xc'] - A['hw'], A['xc'] + A['hw']
    for xa, xb, c in floor_segs:                     # the carpet bands run on into the doorway
        xa, xb = max(xa, x0r), min(xb, x1r)
        if xb - xa > 1e-3: b.add([[xa, 0.01, Z0], [xb, 0.01, Z0], [xb, 0.01, ZD], [xa, 0.01, ZD]], [[0, 1, 2], [0, 2, 3]], c, kind=2)
    T = earcut.triangulate_float64(arch, np.array([len(arch)], np.uint32)).reshape(-1, 3)
    b.add(np.c_[arch, np.full(len(arch), ZD)], T, PAL['door'], kind=5)
    pc = (A['xc'], 16.5, ZD)
    hx = A['xc'] - A['hw'] + 0.95                        # door handle, near the door's left edge
    b.add_mesh(cbox(hx - 0.12, hx + 0.12, 9.6, 12.2, ZD + 0.12, ZD + 0.3, 0.05), PAL['metal'], kind=4)
    for hy_ in (9.85, 11.95):
        b.add_mesh(cbox(hx - 0.07, hx + 0.07, hy_ - 0.07, hy_ + 0.07, ZD, ZD + 0.14, 0.02), PAL['metal'], kind=4)
    V, F = disk(pc, [0, 0, 1], 2.1, 16, 0.03); b.add(V, F, half('#56657a', (52, 56, 68)), kind=4)

    scene = trimesh.Scene()
    for k, m in b.meshes().items():
        scene.add_geometry(m, geom_name='cabin_' + k, node_name='cabin_' + k)
    seat = build_seat()
    print('seat triangles', len(seat.faces))
    placements = [(R(f), t) for t, f in INST]
    for i, (Aff, t) in enumerate(placements):
        M = np.eye(4); M[:3, :3] = Aff; M[:3, 3] = t
        scene.add_geometry(seat, geom_name='seat', node_name='seat_%02d' % i, transform=M)
    small = build_small_seat(); print('small seat triangles', len(small.faces))
    M = np.eye(4); M[:3, :3] = R(True); M[:3, 3] = [-0.4, 0.0, 27.0]
    scene.add_geometry(small, geom_name='small_seat', node_name='small_seat', transform=M)
    # side table
    tb = Builder()
    V, F = slab_with_holes(rounded_rect(-1.72, 1.86, -2.3, 2.3, 0.35), [circle(0.95, zc_, 0.5, 14)[::-1] for zc_ in (-1.1, 1.1)], 4.32, 4.52, 0.06)
    tb.add(V, F, PAL['table'], kind=3)
    for zl_ in (-2.0, 2.0):
        tb.add_mesh(prism(1.25, zl_, 0.12, 0.0, 4.32, 6), PAL['metal'], kind=4)
    table = tb.meshes()['lit']
    for i, (Aff, t) in enumerate(TABLES):
        M = np.eye(4); M[:3, :3] = Aff; M[:3, 3] = t
        scene.add_geometry(table, geom_name='table', node_name='table_%d' % i, transform=M)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    scene.export(out)
    ntri = sum(len(scene.geometry[g].faces) for g in [scene.graph[n][1] for n in scene.graph.nodes_geometry])
    print('wrote', out, '%.2f MB' % (os.path.getsize(out) / 1e6), 'triangles placed', ntri)

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'data'),
          sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, 'out', 'toon.glb'))

