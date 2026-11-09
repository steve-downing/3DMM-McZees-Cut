"""The cartoon dining room (HH-Dining Background, number 8) for VR.

    python toon.py [out.glb]                  -> out/toon.glb

The haunted mansion's dining room: a long table on two trestles, eight
spiderweb chairs and two armchairs at the ends, a purple rug on a flagstone
floor, damask walls with a gold dado rail, four curtained window bays with
seats along one side, a deeper bay at the far end, the arched door, the
painting over the sideboard, five timber trusses under a hipped ceiling and
an iron chandelier.

Everything is in 3DMM's own world units (the scene player's coordinates), so
actors and the movie's cameras line up without any transform. Every number
was measured from the 9 original views' point cloud (lib/cloud.py); colors
are the well-lit medians, mixed 90/10 toward a cartoon color (../STYLE.md).
Mansion pieces that the other mansion sets will reuse (wall layers, window
bays, trusses, the door) are written as functions of where they go."""
import sys, os
import numpy as np
import trimesh
from shapely.geometry import Polygon, box, Point
from shapely.ops import unary_union
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
from toonkit import *

# ----------------------------------------------------------------- measurements
X0, X1 = 136.3, 210.4          # end walls: door end, far window end
Z0, Z1 = -149.8, -90.4         # long walls: window bays, wallpaper
WALL_TOP = 26.0                # walls; the cornice above, then the ceiling slopes in
CORNICE = (26.0, 26.8, 0.6)    # y0, y1, how far it stands out
CEIL = 33.5                    # flat middle of the ceiling (above what the cameras see)
RUN = 6.5                      # the sloping band of ceiling all round, measured in from each wall
BASE = (0.0, 1.6, 0.45)        # baseboard: y0, y1, depth
DADO = (9.2, 11.0, 0.4)        # gold dado rail
BAYS = [151.3, 165.5, 179.85, 193.8]       # window bay centers along the window wall (side faces, 9.1 apart)
BAY_HW, BAY_SPRING, BAY_DEPTH = 4.55, 19.55, 4.75   # half-width, where the arch starts (top 24.1), glass 4.75 behind the wall
MUNTINS_Y = [10.2, 15.1, 19.9]                       # horizontal glazing bars (plus one vertical, centered)
SEAT = dict(hw=6.25, front=2.2, top=6.6, cushion=0.6)   # window seats: 12.5 wide, 2.2 out from the wall
END_BAY = dict(zc=-120.3, hw=5.9, spring=20.4, depth=7.1, seat_top=7.1, seat_front=2.95, seat_hw=6.4,
               muntins=[15.8, 20.9])                 # the far end's bay (glass at x 217.5)
DOOR = dict(z0=-108.4, z1=-96.2, top=22.6, inset=0.3)   # arched door, door end
TRUSSES = [145.3, 158.8, 172.5, 186.6, 200.9]        # from the timber feet on both long walls
TRUSS_W = 3.6
TABLE = dict(x0=156.5, x1=185.8, z0=-126.9, z1=-113.5, top=7.32, thick=0.66, trestles=[162.2, 180.8])
ROW1 = dict(z=-132.55, facing=+1, xs=[158.2, 167.1, 175.5, 183.2])   # chairs with their backs to the windows
ROW2 = dict(z=-108.75, facing=-1, xs=[158.1, 166.0, 174.25, 182.5])  # chairs with their backs to the wallpaper wall
ARMCHAIRS = [((151.9, -120.6), +1), ((189.1, -120.3), -1)]          # head and foot of the table
RUG = dict(x0=147.0, x1=192.3, z0=-136.5, z1=-102.0, border=4.0)
CHANDELIER = dict(x=169.8, z=-120.5, bottom=17.7, arms_y=21.3, r=3.4, n=5)
SIDEBOARD = dict(x0=136.8, x1=143.95, z0=-129.6, z1=-109.5, top=9.5)
PAINTING = dict(z0=-129.0, z1=-111.8, y0=12.4, y1=24.3, canvas_z=(-127.2, -114.0), canvas_y=(14.6, 23.0))
PILLAR = dict(x0=205.4, z1=-95.3, top=17.2)   # in the far corner, against both walls
IRON = dict(z=-147.5, x0=138.2, x1=141.8, top=8.0)   # wrought-iron rack against the window wall

# ----------------------------------------------------------------- colors (cartoon, measured original)
PAL = dict(
    stone=half('#4e4c56', (38, 36, 41)), grout=hexc('#1c1a20'),
    rug=half('#8a2aa0', (66, 22, 62)), rug_border=half('#5a5478', (51, 44, 56)), rug_motif=half('#8a84a8', (78, 72, 90)),
    curtain=half('#f2efe6', (73, 73, 68)), reveal=half('#a07856', (69, 51, 41)),
    cushion=half('#c0262a', (56, 23, 22)), seatbox=half('#7a4a1c', (45, 29, 8)),
    paper=half('#9a8088', (80, 64, 66)), paper_low=half('#7a5458', (62, 44, 44)),
    gold=half('#c89a2e', (84, 63, 24)), trim=half('#8a5a1a', (63, 44, 9)),
    timber=half('#a8682a', (89, 53, 21)), ceiling=half('#9a9086', (84, 76, 66)),
    table=half('#a8541a', (98, 46, 12)), door=half('#7a5a36', (47, 35, 19)), sideboard=half('#6a3410', (45, 19, 5)),
    chair=half('#d07a20', (146, 69, 16)), seat=half('#c42a16', (127, 28, 12)), back=half('#d0302a', (143, 33, 20)),
    web=half('#d0bf90', (150, 136, 100)), skull=half('#e8c860', (165, 135, 64)), socket=hexc('#3a2a10'),
    claw=half('#efe6cc', (170, 160, 140)), iron=half('#3a3430', (47, 35, 23)), candle=hexc('#f4eedc'),
    flame=hexc('#ffd27a'), pillar=half('#7a6a58', (51, 43, 33)), cup=half('#9a9aa0', (90, 90, 96)),
    frame=half('#d4a63a', (120, 92, 30)), glass_bar=half('#6a4a2a', (60, 42, 22)))

# ----------------------------------------------------------------- small helpers
def to_world(plane, pts):
    """(u, y, d) on a wall -> world. plane = (axis, value, inward sign): u runs along
    the wall (x or z), d is how far in front of the wall face."""
    axis, val, s = plane
    pts = np.asarray(pts, float)
    if axis == 'z': return np.c_[pts[:, 0], pts[:, 1], val + s * pts[:, 2]]
    return np.c_[val + s * pts[:, 2], pts[:, 1], pts[:, 0]]

def flat_poly(b, plane, poly, d, color, kind=PLAIN, warp=None):
    """a shapely polygon (u, y) lying on a wall at depth d (warp(u, y) -> extra depth)"""
    for g in getattr(poly, 'geoms', [poly]):
        if g.is_empty or g.area < 1e-6: continue
        V2, T = tri_poly(g)
        dd = np.full(len(V2), d, float) + (warp(V2[:, 0], V2[:, 1]) if warp else 0)
        b.add(to_world(plane, np.c_[V2, dd]), T, color, kind=kind)

def extrude_poly(b, plane, poly, d0, d1, color, kind=PLAIN):
    """a shapely polygon (u, y) pushed out from the wall between depths d0 and d1"""
    for g in getattr(poly, 'geoms', [poly]):
        if g.is_empty or g.area < 1e-6: continue
        flat_poly(b, plane, g, d1, color, kind)
        for ring in [g.exterior] + list(g.interiors):
            c = np.asarray(ring.coords)
            for i in range(len(c) - 1):
                q = [(c[i][0], c[i][1], d0), (c[i + 1][0], c[i + 1][1], d0), (c[i + 1][0], c[i + 1][1], d1), (c[i][0], c[i][1], d1)]
                b.add(to_world(plane, q), [[0, 1, 2], [0, 2, 3]], color, kind=kind)

def arch(u0, u1, y0, spring, n=14):
    """an opening: straight sides from y0 up to the spring line, then a half circle"""
    r = (u1 - u0) / 2; c = (u0 + u1) / 2
    return Polygon([(u0, y0)] + [(c - r * np.cos(t), spring + r * np.sin(t)) for t in np.linspace(0, np.pi, n)] + [(u1, y0)])

def bar(p, q, r, n=4):
    """a thin square rod from p to q (for the spiderwebs, the chandelier, the iron rack)"""
    p, q = np.asarray(p, float), np.asarray(q, float)
    a = q - p; a /= np.linalg.norm(a)
    u = np.cross(a, [0, 1, 0] if abs(a[1]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(a, u)
    ring = [r * (np.cos(t) * u + np.sin(t) * v) for t in np.linspace(0, 2 * np.pi, n, endpoint=False) + np.pi / n]
    return hull([p + o for o in ring] + [q + o for o in ring])

def sphere(c, r, sub=1, scale=(1, 1, 1)):
    m = trimesh.creation.icosphere(subdivisions=sub, radius=r)
    m.vertices = m.vertices * np.asarray(scale) + np.asarray(c)
    return m

def xform(m, M):
    m = m.copy(); m.apply_transform(M); return m

def place(x, z, yaw):
    """local (x across, y up, z forward) -> world, turned yaw about y"""
    M = np.eye(4); c, s = np.cos(yaw), np.sin(yaw)
    M[:3, :3] = [[c, 0, s], [0, 1, 0], [-s, 0, c]]; M[:3, 3] = [x, 0, z]
    return M

# ----------------------------------------------------------------- the room
def wall_layers(b, plane, u0, u1, holes, paper=True, pleats=False):
    """one wall: baseboard, lower panel, dado rail, upper wallpaper (or curtain), cornice,
    all cut around the openings (shapely polygons in (u, y))"""
    cut = unary_union(holes) if holes else Polygon()
    if paper:
        flat_poly(b, plane, box(u0, BASE[1], u1, DADO[0]).difference(cut), 0, PAL['paper_low'], DAMASK)
        flat_poly(b, plane, box(u0, DADO[1], u1, WALL_TOP).difference(cut), 0, PAL['paper'], DAMASK)
        extrude_poly(b, plane, box(u0, DADO[0], u1, DADO[1]).difference(cut), 0, DADO[2], PAL['gold'], METAL)
    else:
        # the window wall is hung with white curtains: soft vertical folds, 1.0 apart
        w = box(u0, BASE[1], u1, WALL_TOP).difference(cut)
        strips = [w.intersection(box(u, BASE[1], min(u + 0.5, u1), WALL_TOP)) for u in np.arange(u0, u1, 0.5)]
        fold = lambda u, y: 0.12 * (1 - np.cos(2 * np.pi * (u - u0) / 1.0))
        for s in strips: flat_poly(b, plane, s, 0, PAL['curtain'], FABRIC, warp=fold)
    extrude_poly(b, plane, box(u0, BASE[0], u1, BASE[1]).difference(cut), 0, BASE[2], PAL['trim'], WOOD)
    # the cornice: a deep top step and a smaller one under it
    extrude_poly(b, plane, box(u0, CORNICE[0] + 0.35, u1, CORNICE[1]).difference(cut), 0, CORNICE[2], PAL['gold'], METAL)
    extrude_poly(b, plane, box(u0, CORNICE[0], u1, CORNICE[0] + 0.35).difference(cut), 0, CORNICE[2] * 0.55, PAL['trim'], WOOD)

def ceiling(b):
    """a hipped ceiling: from the top of the cornice it slopes in RUN on every side,
    then a flat middle"""
    y0 = CORNICE[1]
    a, c = X0 + RUN, X1 - RUN; e, f = Z0 + RUN, Z1 - RUN
    quads = [[(X0, y0, Z0), (X1, y0, Z0), (c, CEIL, e), (a, CEIL, e)],
             [(X1, y0, Z1), (X0, y0, Z1), (a, CEIL, f), (c, CEIL, f)],
             [(X0, y0, Z1), (X0, y0, Z0), (a, CEIL, e), (a, CEIL, f)],
             [(X1, y0, Z0), (X1, y0, Z1), (c, CEIL, f), (c, CEIL, e)],
             [(a, CEIL, e), (c, CEIL, e), (c, CEIL, f), (a, CEIL, f)]]
    for q in quads: b.add(q, [[0, 1, 2], [0, 2, 3]], PAL['ceiling'])

def window_bay(b, plane, c, hw, y_bottom, spring, depth, muntins, seat):
    """a recess behind an arched opening: plastered reveal, glazing bars at the back (open
    to the sky), a trim band round the arch on the wall face and a cushioned window seat
    that stands out into the room"""
    top = spring + hw
    # reveal: the two sides and the arched soffit, from the wall face to the glass
    n = 14
    side = [(c - hw, y_bottom), (c - hw, spring)] + [(c - hw * np.cos(t), spring + hw * np.sin(t)) for t in np.linspace(0, np.pi, n)][1:] + [(c + hw, y_bottom)]
    for i in range(len(side) - 1):
        (u_a, y_a), (u_b, y_b) = side[i], side[i + 1]
        q = [(u_a, y_a, 0), (u_b, y_b, 0), (u_b, y_b, -depth), (u_a, y_a, -depth)]
        b.add(to_world(plane, q), [[0, 1, 2], [0, 2, 3]], PAL['reveal'], kind=HAMMERED)
    # glazing: a frame round the opening and the bars, at the glass
    opening = arch(c - hw, c + hw, y_bottom, spring)
    inner = opening.buffer(-0.32, join_style=2)
    frame = opening.difference(inner)
    bars = [box(c - 0.14, y_bottom, c + 0.14, top)] + [box(c - hw, y - 0.14, c + hw, y + 0.14) for y in muntins]
    glazing = unary_union([frame] + [g.intersection(opening) for g in bars])
    extrude_poly(b, plane, glazing, -depth - 0.15, -depth + 0.18, PAL['glass_bar'], WOOD)
    # trim round the arch, on the wall face
    band = arch(c - hw - 0.6, c + hw + 0.6, seat['top'], spring).difference(arch(c - hw, c + hw, seat['top'] - 1, spring))
    extrude_poly(b, plane, band, 0, 0.38, PAL['reveal'], HAMMERED)
    # the seat: a box that fills the recess and stands out into the room, a cushion on top
    st, sh = seat['top'], seat['top'] - seat['cushion']
    outline = unary_union([box(c - seat['hw'], 0, c + seat['hw'], seat['front']), box(c - hw, -depth, c + hw, 0.01)])
    outline = outline.buffer(0.0)
    # box (in plan: u along the wall, d out from it)
    def plan_solid(poly, y0, y1, color, kind, bevel=0.0):
        V2, T = tri_poly(poly)
        top_pts = [(u, y1, d) for u, d in V2]; bot_pts = [(u, y0, d) for u, d in V2]
        b.add(to_world(plane, top_pts), T, color, kind=kind)
        ring = np.asarray(poly.exterior.coords)
        for i in range(len(ring) - 1):
            (ua, da), (ub, db) = ring[i], ring[i + 1]
            b.add(to_world(plane, [(ua, y0, da), (ub, y0, db), (ub, y1, db), (ua, y1, da)]), [[0, 1, 2], [0, 2, 3]], color, kind=kind)
    plan_solid(outline, 0, sh, PAL['seatbox'], WOOD)
    plan_solid(outline.buffer(-0.12, join_style=1).union(outline.buffer(0.08, join_style=1).intersection(box(c - seat['hw'] - 1, 0.5, c + seat['hw'] + 1, seat['front'] + 0.2))), sh, st, PAL['cushion'], FABRIC)
    # a raised panel on the seat front
    p = (c - seat['hw'] + 0.7, c + seat['hw'] - 0.7)
    q = [(p[0], 1.0, seat['front'] + 0.08), (p[1], 1.0, seat['front'] + 0.08), (p[1], sh - 0.9, seat['front'] + 0.08), (p[0], sh - 0.9, seat['front'] + 0.08)]
    b.add(to_world(plane, q), [[0, 1, 2], [0, 2, 3]], half('#8a5824', (55, 35, 12)), kind=WOOD)
    return opening

def door(b, plane):
    """the arched plank door, a little back from the wall face, with its trim and a ring pull"""
    z0, z1, top, inset = DOOR['z0'], DOOR['z1'], DOOR['top'], DOOR['inset']
    r = (z1 - z0) / 2; spring = top - r
    opening = arch(z0, z1, 0, spring)
    # planks: vertical strips with a dark seam between
    nplank = 7; w = (z1 - z0) / nplank
    for i in range(nplank):
        s = opening.intersection(box(z0 + i * w + 0.05, 0, z0 + (i + 1) * w - 0.05, top + 1))
        shade = PAL['door'] * (0.92 + 0.16 * ((i * 37) % 5) / 4)
        flat_poly(b, plane, s, -inset, shade, WOOD)
    flat_poly(b, plane, opening, -inset - 0.06, PAL['door'] * 0.45)
    # reveal between the wall face and the door
    ring = np.asarray(opening.exterior.coords)
    for i in range(len(ring) - 1):
        (ua, ya), (ub, yb) = ring[i], ring[i + 1]
        if ya < 0.01 and yb < 0.01: continue
        b.add(to_world(plane, [(ua, ya, 0), (ub, yb, 0), (ub, yb, -inset), (ua, ya, -inset)]), [[0, 1, 2], [0, 2, 3]], PAL['trim'], kind=WOOD)
    # iron straps and the ring pull
    for y in (4.5, 13.5):
        extrude_poly(b, plane, box(z0 + 0.4, y - 0.25, z1 - 0.4, y + 0.25), -inset, -inset + 0.08, PAL['iron'], HAMMERED)
    knob = to_world(plane, [(z1 - 1.5, 10.5, -inset + 0.25)])[0]
    b.add_mesh(sphere(knob, 0.42, 1), PAL['gold'], kind=METAL)
    # trim on the wall face
    band = arch(z0 - 0.7, z1 + 0.7, 0, spring).difference(arch(z0, z1, -1, spring))
    extrude_poly(b, plane, band, 0, 0.3, PAL['trim'], WOOD)
    return opening

def trusses(b):
    """timber arches across the room under the ceiling: from a foot on each long wall they
    curve up to a tie beam just under the flat ceiling"""
    span = Z1 - Z0
    def under(s):    # height of the underside, s = distance from the window wall
        t = min(s, span - s)
        if t >= 11: return 32.0
        a = t / 11
        return (1 - a) ** 2 * 22.4 + 2 * (1 - a) * a * 26.0 + a ** 2 * 32.0      # quadratic bezier (22.4 -> 32.0)
    def ceil_at(s): return min(CORNICE[1] + (CEIL - CORNICE[1]) * min(s, span - s) / RUN, CEIL)
    ss = np.r_[np.linspace(0, 11, 12), np.linspace(span - 11, span, 12)]
    bottom = [(s, under(s)) for s in ss]
    top = [(s, min(under(s) + 2.4, ceil_at(s))) for s in ss[::-1]]
    prof = Polygon(bottom + top).buffer(0)
    for x in TRUSSES:
        for side in (-1, 1):
            plane = ('x', x + side * TRUSS_W / 2, side)
            V2, T = tri_poly(prof)
            b.add(to_world(plane, np.c_[V2[:, 0] + Z0, V2[:, 1], np.zeros(len(V2))]), T, PAL['timber'], kind=WOOD)
        ring = np.asarray(prof.exterior.coords)
        for i in range(len(ring) - 1):
            (sa, ya), (sb, yb) = ring[i], ring[i + 1]
            q = [(x - TRUSS_W / 2, ya, Z0 + sa), (x + TRUSS_W / 2, ya, Z0 + sa), (x + TRUSS_W / 2, yb, Z0 + sb), (x - TRUSS_W / 2, yb, Z0 + sb)]
            b.add(q, [[0, 1, 2], [0, 2, 3]], PAL['timber'], kind=WOOD)
        # a carved corbel under each foot
        for zw, s in ((Z0, 1), (Z1, -1)):
            pts = []
            for y, d in ((20.2, 0.0), (20.2, 0.5), (21.0, 1.1), (22.4, 1.4), (22.4, 0.0)):
                for xx in (x - TRUSS_W / 2 + 0.2, x + TRUSS_W / 2 - 0.2):
                    pts.append((xx, y, zw + s * d))
            b.add_mesh(hull(pts), PAL['timber'], kind=WOOD)

def rug(b):
    x0, x1, z0, z1, w = RUG['x0'], RUG['x1'], RUG['z0'], RUG['z1'], RUG['border']
    y0, y1 = 0.0, 0.08
    b.add_mesh(cbox(x0, x1, y0, y1, z0, z1, 0.04), PAL['rug_border'], kind=CARPET)
    b.add([(x0 + w, y1 + 0.005, z0 + w), (x1 - w, y1 + 0.005, z0 + w), (x1 - w, y1 + 0.005, z1 - w), (x0 + w, y1 + 0.005, z1 - w)], [[0, 2, 1], [0, 3, 2]], PAL['rug'], kind=CARPET)
    # a thin dark line round the field, and pale rosettes all along the border
    for (a, c, e, f) in ((x0 + w - 0.25, x1 - w + 0.25, z0 + w - 0.25, z0 + w), (x0 + w - 0.25, x1 - w + 0.25, z1 - w, z1 - w + 0.25),
                         (x0 + w - 0.25, x0 + w, z0 + w, z1 - w), (x1 - w, x1 - w + 0.25, z0 + w, z1 - w)):
        b.add([(a, y1 + 0.008, e), (c, y1 + 0.008, e), (c, y1 + 0.008, f), (a, y1 + 0.008, f)], [[0, 2, 1], [0, 3, 2]], PAL['rug'] * 0.55, kind=CARPET)
    def rosettes(p, q, n):
        for t in np.linspace(0, 1, n):
            c = p + (q - p) * t
            V, F = disk((c[0], y1, c[1]), [0, 1, 0], 0.95, 10, 0.012); b.add(V, F, PAL['rug_motif'], kind=CARPET)
            V, F = disk((c[0], y1, c[1]), [0, 1, 0], 0.4, 8, 0.016); b.add(V, F, PAL['rug_border'] * 0.8, kind=CARPET)
    m = w / 2
    rosettes(np.array([x0 + m, z0 + m]), np.array([x1 - m, z0 + m]), 11); rosettes(np.array([x0 + m, z1 - m]), np.array([x1 - m, z1 - m]), 11)
    rosettes(np.array([x0 + m, z0 + m + 3.8]), np.array([x0 + m, z1 - m - 3.8]), 6); rosettes(np.array([x1 - m, z0 + m + 3.8]), np.array([x1 - m, z1 - m - 3.8]), 6)
    # the field's central medallion
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    for r_, col in ((6.5, PAL['rug'] * 0.75), (4.6, PAL['rug_border']), (2.4, PAL['rug'] * 1.15)):
        V, F = disk((cx, y1, cz), [0, 1, 0], r_, 20, 0.02 + 0.004 * (6.5 - r_)); V[:, 0] = cx + (V[:, 0] - cx) * 1.5
        b.add(V, F, col, kind=CARPET)

def build_room():
    b = Builder()
    # floor
    b.add([(X0, 0, Z0), (X1, 0, Z0), (X1, 0, Z1), (X0, 0, Z1)], [[0, 2, 1], [0, 3, 2]], PAL['stone'], kind=STONE)
    # window wall: four bays in curtains
    win = ('z', Z0, 1)
    holes = [window_bay(b, win, c, BAY_HW, 0.0, BAY_SPRING, BAY_DEPTH, MUNTINS_Y, SEAT) for c in BAYS]
    wall_layers(b, win, X0, X1, holes, paper=False)
    # wallpaper wall
    wall_layers(b, ('z', Z1, -1), X0, X1, [], paper=True)
    # door end: door, painting, sideboard
    dend = ('x', X0, 1)
    wall_layers(b, dend, Z0, Z1, [door(b, dend)])
    # far end: the deep bay
    fend = ('x', X1, -1)
    e = END_BAY
    hole = window_bay(b, fend, e['zc'], e['hw'], 0.0, e['spring'], e['depth'], e['muntins'],
                      dict(hw=e['seat_hw'], front=e['seat_front'], top=e['seat_top'], cushion=0.6))
    wall_layers(b, fend, Z0, Z1, [hole])
    ceiling(b)
    trusses(b)
    rug(b)
    # painting frame (the canvas is a separate, textured mesh)
    P = PAINTING
    outer = box(P['z0'], P['y0'], P['z1'], P['y1'])
    inner = box(P['canvas_z'][0], P['canvas_y'][0], P['canvas_z'][1], P['canvas_y'][1])
    extrude_poly(b, dend, outer.difference(inner), 0, 1.2, PAL['frame'], METAL)
    extrude_poly(b, dend, outer.difference(outer.buffer(-0.45, join_style=2)), 1.2, 1.35, PAL['frame'] * 1.1, METAL)
    # corner pillar: base, shaft, cap
    p = PILLAR
    b.add_mesh(cbox(p['x0'] - 0.3, X1, 0, 1.2, Z1 - 0.01 - (Z1 - p['z1']) - 0.3, Z1, 0.1), PAL['pillar'] * 0.85, kind=HAMMERED)
    b.add_mesh(cbox(p['x0'], X1, 1.2, p['top'] - 1.0, p['z1'], Z1, 0.15), PAL['pillar'], kind=HAMMERED)
    b.add_mesh(cbox(p['x0'] - 0.35, X1, p['top'] - 1.0, p['top'], p['z1'] - 0.35, Z1, 0.12), PAL['pillar'] * 1.1, kind=HAMMERED)
    return b

# ----------------------------------------------------------------- furniture
def skull(c, r=0.42):
    """a gold skull finial: rounded cranium, a jaw, two dark eye sockets facing +z"""
    out = [(sphere(c, r, 1, (0.92, 0.95, 1.0)), PAL['skull']),
           (cbox(c[0] - r * 0.55, c[0] + r * 0.55, c[1] - r * 1.25, c[1] - r * 0.55, c[2] - r * 0.15, c[2] + r * 0.8, 0.08), PAL['skull'])]
    for sx in (-1, 1):
        V, F = disk((c[0] + sx * r * 0.38, c[1] - r * 0.1, c[2] + r * 0.88), [0.25 * sx, 0, 1], r * 0.26, 8, 0.0)
        out.append(((V, F), PAL['socket']))
    return out

def add_parts(b, parts, kind=PLAIN):
    for m, col in parts:
        if isinstance(m, tuple): b.add(m[0], m[1], col, kind=kind)
        else: b.add_mesh(m, col, kind=kind)

def cabriole(x, z, top, out=0.25, w=0.5):
    """a cabriole leg: a knee that bows out, an ankle that tucks in, a small foot"""
    sec = lambda y, dz, s: [(x + sx * s, y, z + dz + sz * s) for sx in (-1, 1) for sz in (-1, 1)]
    return [hull(sec(top, 0, w / 2) + sec(top - 1.0, out, w * 0.55)),
            hull(sec(top - 1.0, out, w * 0.55) + sec(1.0, -0.12, w * 0.32)),
            hull(sec(1.0, -0.12, w * 0.32) + sec(0.0, 0.2, w * 0.42))]

def build_side_chair():
    """local frame: x across, y up, z toward the table; origin on the floor under the seat"""
    b = Builder()
    lean = lambda y: -0.145 * (y - 4.5)              # the back leans 0.9 over its 6.2 height
    zb = -2.45                                        # back edge of the seat
    def post(sx):
        pts = []
        for y, x in ((4.4, 2.35), (10.4, 2.95)):
            for dx in (-0.27, 0.27):
                for dz in (-0.25, 0.25):
                    pts.append((sx * (x + dx), y, zb + lean(y) + dz))
        return hull(pts)
    for sx in (-1, 1):
        b.add_mesh(post(sx), PAL['chair'], kind=WOOD)
        b.add_mesh(cbox(sx * 2.35 - 0.23, sx * 2.35 + 0.23, 0, 4.4, zb - 0.23, zb + 0.23, 0.06), PAL['chair'], kind=WOOD)      # back leg
        for m in cabriole(sx * 2.3, 1.95, 4.0, 0.22, 0.48): b.add_mesh(m, PAL['chair'], kind=WOOD)
    # seat frame and cushion
    b.add_mesh(cbox(-2.6, 2.6, 3.95, 4.4, -2.55, 2.45, 0.1), PAL['chair'], kind=WOOD)
    V, F = slab_with_holes(rounded_rect(-2.45, 2.45, -2.4, 2.35, 0.35), [], 4.4, 4.64, 0.08)
    b.add(V, F, PAL['seat'], kind=FABRIC)
    # top rail with the bat crest
    yr0, yr1 = 9.6, 10.3
    rail = []
    for y in (yr0, yr1):
        for x in (-2.85, 2.85):
            for dz in (-0.22, 0.22): rail.append((x, y, zb + lean(y) + dz))
    b.add_mesh(hull(rail), PAL['chair'], kind=WOOD)
    bat = [(0, 9.15), (0.35, 9.55), (0.9, 9.6), (1.5, 9.75), (1.75, 10.15), (1.2, 10.05), (0.75, 10.3), (0.35, 10.3), (0.22, 10.55), (0.1, 10.4),
           (-0.1, 10.4), (-0.22, 10.55), (-0.35, 10.3), (-0.75, 10.3), (-1.2, 10.05), (-1.75, 10.15), (-1.5, 9.75), (-0.9, 9.6), (-0.35, 9.55)]
    V2, T = tri_poly(Polygon(bat))
    for dz in (-0.26, 0.26):
        b.add(np.c_[V2[:, 0], V2[:, 1], zb + lean(V2[:, 1]) + dz], T, PAL['chair'], kind=WOOD)
    ring = np.asarray(Polygon(bat).exterior.coords)
    for i in range(len(ring) - 1):
        (xa, ya), (xc, yc) = ring[i], ring[i + 1]
        q = [(xa, ya, zb + lean(ya) - 0.26), (xc, yc, zb + lean(yc) - 0.26), (xc, yc, zb + lean(yc) + 0.26), (xa, ya, zb + lean(ya) + 0.26)]
        b.add(q, [[0, 1, 2], [0, 2, 3]], PAL['chair'], kind=WOOD)
    # the spiderweb: spokes from the middle to the frame, two rings (ovals) across them
    cx, cy = 0.0, 6.35
    W = lambda x, y: (x, y, zb + lean(y))
    ends = [(-2.3, 6.45), (-2.2, 8.4), (0.0, 9.6), (2.2, 8.4), (2.3, 6.45), (2.1, 4.65), (0.0, 4.6), (-2.1, 4.65)]
    for ex, ey in ends: b.add_mesh(bar(W(cx, cy), W(ex, ey), 0.045), PAL['web'], kind=METAL)
    for k in (0.45, 0.85):
        pts = [W(cx + (ex - cx) * k, cy + (ey - cy) * k) for ex, ey in ends]
        for i in range(len(pts)): b.add_mesh(bar(pts[i], pts[(i + 1) % len(pts)], 0.04), PAL['web'], kind=METAL)
    # skull finials
    for sx in (-1, 1):
        add_parts(b, skull((sx * 3.05, 10.78, zb + lean(10.78))), METAL)
    return b.meshes()['lit']

def build_armchair():
    """the carvers at the table's ends: an upholstered shield back, arms, skulls, claw-and-ball feet"""
    b = Builder()
    lean = lambda y: -0.16 * (y - 4.5)
    zb = -2.3
    for sx in (-1, 1):
        pts = []
        for y, x in ((4.3, 3.0), (10.5, 3.35)):
            for dx in (-0.3, 0.3):
                for dz in (-0.28, 0.28): pts.append((sx * (x + dx), y, zb + lean(y) + dz))
        b.add_mesh(hull(pts), PAL['chair'], kind=WOOD)
        b.add_mesh(cbox(sx * 3.0 - 0.26, sx * 3.0 + 0.26, 0, 4.3, zb - 0.26, zb + 0.26, 0.06), PAL['chair'], kind=WOOD)
        for m in cabriole(sx * 2.95, 2.25, 3.95, 0.25, 0.55): b.add_mesh(m, PAL['chair'], kind=WOOD)
        b.add_mesh(sphere((sx * 2.95, 0.3, 2.45), 0.36, 1), PAL['claw'], kind=PLAIN)
        # arm and its support
        b.add_mesh(cbox(sx * 3.2 - 0.24, sx * 3.2 + 0.24, 5.8, 6.2, zb + lean(6.0), 2.6, 0.1), PAL['chair'], kind=WOOD)
        b.add_mesh(hull([(sx * 3.2 + dx, y, 2.15 + dz) for dx in (-0.2, 0.2) for dz in (-0.2, 0.2) for y in (4.4,)] +
                        [(sx * 3.2 + dx, 5.85, 2.3 + dz) for dx in (-0.2, 0.2) for dz in (-0.2, 0.2)]), PAL['chair'], kind=WOOD)
        add_parts(b, skull((sx * 3.25, 10.85, zb + lean(10.85)), 0.5), METAL)
    b.add_mesh(cbox(-3.3, 3.3, 3.9, 4.3, -2.45, 2.55, 0.1), PAL['chair'], kind=WOOD)
    V, F = slab_with_holes(rounded_rect(-3.1, 3.1, -2.3, 2.4, 0.4), [], 4.3, 4.6, 0.1)
    b.add(V, F, PAL['seat'], kind=FABRIC)
    # the back: a wooden shield, the red panel on it, a crest on top
    shield = Polygon([(-2.75, 10.45), (2.75, 10.45), (2.55, 8.0), (1.6, 5.6), (0.9, 4.9), (-0.9, 4.9), (-1.6, 5.6), (-2.55, 8.0)])
    panel = shield.buffer(-0.35, join_style=1)
    for poly, d0, d1, col, kind in ((shield, -0.2, 0.12, PAL['chair'], WOOD), (panel, 0.12, 0.34, PAL['back'], FABRIC)):
        V2, T = tri_poly(poly)
        b.add(np.c_[V2[:, 0], V2[:, 1], zb + lean(V2[:, 1]) + d1], T, col, kind=kind)
        b.add(np.c_[V2[:, 0], V2[:, 1], zb + lean(V2[:, 1]) + d0], T, col, kind=kind)
        ring = np.asarray(poly.exterior.coords)
        for i in range(len(ring) - 1):
            (xa, ya), (xc, yc) = ring[i], ring[i + 1]
            b.add([(xa, ya, zb + lean(ya) + d0), (xc, yc, zb + lean(yc) + d0), (xc, yc, zb + lean(yc) + d1), (xa, ya, zb + lean(ya) + d1)], [[0, 1, 2], [0, 2, 3]], col, kind=kind)
    for x, h in ((-0.75, 0.45), (0.0, 0.7), (0.75, 0.45)):
        b.add_mesh(hull([(x + dx, 10.4, zb + lean(10.4) + dz) for dx in (-0.3, 0.3) for dz in (-0.15, 0.15)] + [(x, 10.4 + h, zb + lean(10.4 + h))]), PAL['chair'], kind=WOOD)
    b.add_mesh(cbox(-2.9, 2.9, 10.2, 10.55, zb + lean(10.4) - 0.25, zb + lean(10.4) + 0.2, 0.08), PAL['chair'], kind=WOOD)
    return b.meshes()['lit']

def build_table():
    """the long table: a thick top on two trestles joined by a stretcher (world coordinates)"""
    b = Builder(); t = TABLE
    zc = (t['z0'] + t['z1']) / 2
    b.add_mesh(cbox(t['x0'], t['x1'], t['top'] - t['thick'], t['top'], t['z0'], t['z1'], 0.14), PAL['table'], kind=WOOD)
    for x in t['trestles']:
        b.add_mesh(cbox(x - 0.85, x + 0.85, 0, 0.75, zc - 4.65, zc + 4.65, 0.25), PAL['table'] * 0.85, kind=WOOD)      # foot
        b.add_mesh(hull([(x + dx, 0.75, zc + dz) for dx in (-0.55, 0.55) for dz in (-1.9, 1.9)] +
                        [(x + dx, 5.9, zc + dz) for dx in (-0.5, 0.5) for dz in (-1.2, 1.2)]), PAL['table'] * 0.9, kind=WOOD)   # post, wider at the foot
        b.add_mesh(cbox(x - 0.7, x + 0.7, 5.9, t['top'] - t['thick'], zc - 4.4, zc + 4.4, 0.15), PAL['table'] * 0.85, kind=WOOD)  # cleat
    a, c = t['trestles']
    b.add_mesh(cbox(a, c, 2.2, 3.0, zc - 0.4, zc + 0.4, 0.1), PAL['table'] * 0.85, kind=WOOD)
    return b.meshes()['lit']

def build_sideboard():
    b = Builder(); s = SIDEBOARD
    b.add_mesh(cbox(s['x0'], s['x1'], s['top'] - 0.45, s['top'], s['z0'], s['z1'], 0.1), PAL['sideboard'], kind=WOOD)
    b.add_mesh(cbox(s['x0'], s['x1'] - 0.4, s['top'] - 1.35, s['top'] - 0.45, s['z0'] + 0.4, s['z1'] - 0.4, 0.08), PAL['sideboard'] * 0.85, kind=WOOD)
    for x, z in ((s['x0'] + 0.6, s['z0'] + 0.7), (s['x1'] - 0.8, s['z0'] + 0.7), (s['x0'] + 0.6, s['z1'] - 0.7), (s['x1'] - 0.8, s['z1'] - 0.7)):
        for m in cabriole(x, z, s['top'] - 0.45, 0.3 * np.sign(z - (s['z0'] + s['z1']) / 2), 0.6): b.add_mesh(m, PAL['sideboard'], kind=WOOD)
    # a pewter cup on top (camera 2 sees it)
    b.add_mesh(prism(140.6, -122.8, 0.45, s['top'], s['top'] + 1.2, 10), PAL['cup'], kind=METAL)
    b.add_mesh(prism(140.6, -122.8, 0.55, s['top'] + 1.1, s['top'] + 1.4, 10), PAL['cup'], kind=METAL)
    return b.meshes()['lit']

def build_chandelier():
    """iron: a rod from the ceiling, a bowl, five curling arms with candle cups and candles"""
    b = Builder(); c = CHANDELIER; x, z = c['x'], c['z']
    b.add_mesh(bar((x, CEIL, z), (x, 19.5, z), 0.12, 6), PAL['iron'], kind=METAL)
    b.add_mesh(hull([(x + 0.9 * np.cos(t), 19.4, z + 0.9 * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 8, endpoint=False)] +
                    [(x + 0.3 * np.cos(t), c['bottom'], z + 0.3 * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 8, endpoint=False)]), PAL['iron'], kind=METAL)
    glow = []
    for i in range(c['n']):
        t = np.pi / 2 + i * 2 * np.pi / c['n']
        u = np.array([np.cos(t), 0, np.sin(t)])
        pts = [np.array([x, 19.2, z]) + u * r_ + np.array([0, dy, 0]) for r_, dy in ((0.6, 0.0), (1.6, -0.6), (2.6, -0.2), (3.2, 0.9), (c['r'], 2.0))]
        for p, q in zip(pts[:-1], pts[1:]): b.add_mesh(bar(p, q, 0.1, 4), PAL['iron'], kind=METAL)
        tip = pts[-1]
        b.add_mesh(prism(tip[0], tip[2], 0.38, tip[1] - 0.15, tip[1] + 0.12, 8), PAL['iron'], kind=METAL)
        b.add_mesh(prism(tip[0], tip[2], 0.17, tip[1] + 0.12, tip[1] + 1.25, 8), PAL['candle'])
        glow.append(hull([(tip[0] + 0.1 * np.cos(a), tip[1] + 1.3, tip[2] + 0.1 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)] + [(tip[0], tip[1] + 1.75, tip[2])]))
    for g in glow: b.add_mesh(g, PAL['flame'], group='glow')
    return b.meshes()

def build_iron_rack():
    """the wrought-iron rack against the window wall: two posts, rails, scrolls on top"""
    b = Builder(); r = IRON; z = r['z']
    for x in (r['x0'], r['x1']):
        b.add_mesh(bar((x, 0, z), (x, r['top'], z), 0.08), PAL['iron'], kind=METAL)
        for dx in (-0.5, 0.5): b.add_mesh(bar((x, 0.3, z), (x + dx, 0.0, z + 0.4), 0.06), PAL['iron'], kind=METAL)
    for y in (1.6, r['top']):
        b.add_mesh(bar((r['x0'] - 0.3, y, z), (r['x1'] + 0.3, y, z), 0.07), PAL['iron'], kind=METAL)
    for x, s in ((r['x0'] - 0.3, -1), (r['x1'] + 0.3, 1)):
        pts = [(x + s * 0.45 * np.sin(t), r['top'] - 0.45 + 0.45 * np.cos(t), z) for t in np.linspace(0, 1.6 * np.pi, 8)]
        for p, q in zip(pts[:-1], pts[1:]): b.add_mesh(bar(p, q, 0.06), PAL['iron'], kind=METAL)
    return b.meshes()['lit']

def painting():
    P = PAINTING; (z0, z1), (y0, y1) = P['canvas_z'], P['canvas_y']
    # facing into the room (+x); the image's columns run along z, its rows down from the top
    V = np.array([(X0 + 1.0, y0, z1), (X0 + 1.0, y0, z0), (X0 + 1.0, y1, z0), (X0 + 1.0, y1, z1)])
    uv = np.array([(1, 0), (0, 0), (0, 1), (1, 1)], float)
    img = Image.open(os.path.join(HERE, 'data', 'painting.png'))
    mat = trimesh.visual.material.PBRMaterial(baseColorTexture=img, roughnessFactor=0.9, metallicFactor=0.0)
    m = trimesh.Trimesh(V, [[0, 1, 2], [0, 2, 3]], visual=trimesh.visual.TextureVisuals(uv=uv, material=mat), process=False)
    return m

# ----------------------------------------------------------------- assemble
def build(out):
    scene = trimesh.Scene()
    for k, m in build_room().meshes().items():
        scene.add_geometry(m, geom_name='room_' + k, node_name='room_' + k)
    scene.add_geometry(painting(), geom_name='picture', node_name='picture')
    scene.add_geometry(build_table(), geom_name='table', node_name='table')
    scene.add_geometry(build_sideboard(), geom_name='sideboard', node_name='sideboard')
    scene.add_geometry(build_iron_rack(), geom_name='iron_rack', node_name='iron_rack')
    for k, m in build_chandelier().items():
        scene.add_geometry(m, geom_name='chandelier_' + k, node_name='chandelier_' + k)
    chair = build_side_chair(); arm = build_armchair()
    print('side chair triangles', len(chair.faces), '/ armchair', len(arm.faces))
    i = 0
    for row in (ROW1, ROW2):
        yaw = 0.0 if row['facing'] > 0 else np.pi
        for x in row['xs']:
            scene.add_geometry(chair, geom_name='chair', node_name='chair_%02d' % i, transform=place(x, row['z'], yaw)); i += 1
    for k, ((x, z), facing) in enumerate(ARMCHAIRS):
        scene.add_geometry(arm, geom_name='armchair', node_name='armchair_%d' % k, transform=place(x, z, np.pi / 2 * facing))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    scene.export(out)
    ntri = sum(len(scene.geometry[g].faces) for g in [scene.graph[n][1] for n in scene.graph.nodes_geometry])
    print('wrote', out, '%.2f MB' % (os.path.getsize(out) / 1e6), 'triangles placed', ntri)

if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'out', 'toon.glb'))
