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
from shapely import affinity
from shapely.ops import unary_union
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
from toonkit import *

# ----------------------------------------------------------------- measurements
X0, X1 = 136.3, 210.4          # end walls: door end, far window end
Z0, Z1 = -149.8, -90.4         # long walls: window bays, wallpaper
WALL_TOP = 26.0                # walls; the cornice above, then the ceiling slopes in
CORNICE = (24.9, 26.8, 0.85)   # a deep stepped molding: y0, y1, how far its top stands out
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
TABLE = dict(x0=156.5, x1=185.8, z0=-126.9, z1=-113.5, top=7.32, thick=0.66, legs=[162.5, 180.7], leg_off=4.75)   # two legs per end, 4.75 either side of the middle
# the side chairs (x, z, degrees turned), measured from their skull finials in all nine views:
# not quite in line, as in the 1995 set; yaw 0 faces +z
CHAIRS = [(158.36, -132.78, 11.0), (167.11, -132.40, 2.4), (175.59, -132.21, 3.0), (183.25, -131.86, -5.4),   # backs to the windows
          (158.11, -109.05, -179.0), (165.82, -109.08, 176.9), (174.07, -109.00, -177.2), (182.15, -108.91, 178.9)]   # backs to the wallpaper
ARMCHAIRS = [((151.9, -120.6), +1), ((189.1, -120.3), -1)]          # head and foot of the table
RUG = dict(x0=147.0, x1=192.3, z0=-136.5, z1=-102.0, border=4.0)
CHANDELIER = dict(x=169.8, z=-120.5, bottom=17.7, arms_y=21.3, r=3.4, n=5)
SIDEBOARD = dict(x0=136.8, x1=143.95, z0=-129.6, z1=-109.5, top=9.5)
PAINTING = dict(canvas_z=(-127.2, -114.0), canvas_y=(14.6, 23.0))   # the frame round it is 0.9 wide (drawn thinner than 1995's)
PILLAR = dict(x0=205.4, z1=-95.3, top=17.2)   # in the far corner, against both walls
IRON = dict(z=-147.5, x0=138.2, x1=141.8, top=8.0)   # wrought-iron rack against the window wall

# ----------------------------------------------------------------- colors (cartoon, measured original)
# The woodwork is oak, a little browner than 1995's orange (Steve's call); the rest follows the original.
PAL = dict(
    stone=half('#4e4c56', (38, 36, 41)), grout=hexc('#1c1a20'),
    rug=half('#8a2aa0', (66, 22, 62)), rug_border=half('#5a5478', (51, 44, 56)), rug_motif=half('#8a84a8', (78, 72, 90)),
    curtain=half('#f2efe6', (73, 73, 68)), reveal=half('#a07856', (69, 51, 41)),
    cushion=half('#c0262a', (56, 23, 22)), seatbox=hexc('#513620'),
    paper=half('#9a8088', (80, 64, 66)), paper_low=half('#6c3f72', (60, 40, 64)),
    gold=half('#c89a2e', (84, 63, 24)), gilt=half('#d6b04c', (122, 102, 50)), trim=hexc('#4a321c'),
    timber=hexc('#5c3f24'), ceiling=half('#9a9086', (84, 76, 66)),
    table=hexc('#643f24'), door=hexc('#5c3e22'), sideboard=hexc('#4b331d'),
    chair=hexc('#6e4a28'), seat=half('#c42a16', (127, 28, 12)), back=half('#d0302a', (143, 33, 20)),
    web=half('#9a8540', (112, 98, 50)), skull=half('#e8c860', (165, 135, 64)), socket=hexc('#3a2a10'),
    claw=half('#efe6cc', (170, 160, 140)), iron=half('#1c1816', (30, 24, 18)), candle=hexc('#f4eedc'),
    flame=hexc('#ffd27a'), pillar=half('#7a6a58', (51, 43, 33)), cup=half('#9a9aa0', (90, 90, 96)),
    frame=half('#d4a63a', (120, 92, 30)), glass_bar=hexc('#47301c'))

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
        # below the dado: a deeper purple, striped across instead of up
        flat_poly(b, plane, box(u0, BASE[1], u1, DADO[0]).difference(cut), 0, PAL['paper_low'], DAMASK + TURNED)
        flat_poly(b, plane, box(u0, DADO[1], u1, WALL_TOP).difference(cut), 0, PAL['paper'], DAMASK)
        # the dado rail: gilt, a bead below and a cap above a frieze of egg-and-dart
        y0, y1, d = DADO
        extrude_poly(b, plane, box(u0, y0, u1, y1).difference(cut), 0, d, PAL['gilt'] * 0.8, METAL)
        extrude_poly(b, plane, box(u0, y0 - 0.12, u1, y0 + 0.22).difference(cut), 0, d + 0.16, PAL['gilt'], METAL)
        extrude_poly(b, plane, box(u0, y1 - 0.25, u1, y1 + 0.1).difference(cut), 0, d + 0.2, PAL['gilt'], METAL)
        ym, hh = (y0 + 0.22 + y1 - 0.25) / 2, (y1 - 0.25 - y0 - 0.22) / 2
        orn = []
        for u in np.arange(u0 + 0.6, u1 - 0.4, 1.1):
            orn.append(affinity.scale(Point(u, ym).buffer(1, 4), 0.36, hh * 0.82))
            orn.append(Polygon([(u + 0.55, ym + hh * 0.75), (u + 0.65, ym), (u + 0.55, ym - hh * 0.75), (u + 0.45, ym)]))
        extrude_poly(b, plane, unary_union(orn).difference(cut), d, d + 0.14, PAL['gilt'] * 1.12, METAL)
    else:
        # the window wall is hung with white curtains: soft vertical folds, 1.0 apart
        w = box(u0, BASE[1], u1, WALL_TOP).difference(cut)
        # (set back into the wall, not out from it: 3-D text in a movie can stand just in front of it)
        strips = [w.intersection(box(u, BASE[1], min(u + 0.27, u1), WALL_TOP)) for u in np.arange(u0, u1, 0.27)]
        fold = lambda u, y: -0.09 * (1 - np.cos(2 * np.pi * (u - u0) / 1.62))
        for s in strips: flat_poly(b, plane, s, 0, PAL['curtain'], FABRIC, warp=fold)
    extrude_poly(b, plane, box(u0, BASE[0], u1, BASE[1]).difference(cut), 0, BASE[2], PAL['gilt'] * 0.85, METAL)
    extrude_poly(b, plane, box(u0, BASE[1] - 0.25, u1, BASE[1] + 0.05).difference(cut), 0, BASE[2] + 0.12, PAL['gilt'], METAL)
    # the cornice: a deep, stepped molding: bead, frieze, ovolo, crown, top fillet
    # (gilt throughout, the recessed steps a little darker)
    for y0, y1, dd, col, kind in ((24.9, 25.15, 0.3, PAL['gilt'], METAL), (25.15, 25.75, 0.2, PAL['gilt'] * 0.75, METAL),
                                  (25.75, 26.15, 0.55, PAL['gilt'], METAL), (26.15, 26.55, 0.72, PAL['gilt'] * 0.8, METAL),
                                  (26.55, CORNICE[1], CORNICE[2], PAL['gilt'], METAL)):
        extrude_poly(b, plane, box(u0, y0, u1, y1).difference(cut), 0, dd, col, kind)

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
    extrude_poly(b, plane, band, 0, 0.12, PAL['reveal'], HAMMERED)      # nearly flush: actors pass close in front of it
    # the seat: a box that fills the recess and stands out into the room, a cushion on top
    st, sh = seat['top'], seat['top'] - seat['cushion']
    outline = unary_union([box(c - seat['hw'], 0, c + seat['hw'], seat['front']), box(c - hw, -depth, c + hw, 0.01)])
    outline = outline.buffer(0.0)
    # box (in plan: u along the wall, d out from it)
    def plan_solid(poly, y0, y1, color, kind, group='lit'):
        V2, T = tri_poly(poly)
        top_pts = [(u, y1, d) for u, d in V2]
        b.add(to_world(plane, top_pts), T, color, kind=kind, group=group)
        ring = np.asarray(poly.exterior.coords)
        for i in range(len(ring) - 1):
            (ua, da), (ub, db) = ring[i], ring[i + 1]
            b.add(to_world(plane, [(ua, y0, da), (ub, y0, db), (ub, y1, db), (ua, y1, da)]), [[0, 1, 2], [0, 2, 3]], color, kind=kind, group=group)
    plan_solid(outline, 0, sh, PAL['seatbox'], WOOD)
    cush = outline.buffer(-0.12, join_style=1).union(outline.buffer(0.08, join_style=1).intersection(box(c - seat['hw'] - 1, 0.5, c + seat['hw'] + 1, seat['front'] + 0.2)))
    plan_solid(cush, sh, st, PAL['cushion'], CARPET, group='velvet')
    return opening

def door(b, plane):
    """the arched door, a little back from the wall face: a pair of solid oak leaves meeting
    in the middle, a knob on each beside the meeting stiles, and its trim"""
    z0, z1, top, inset = DOOR['z0'], DOOR['z1'], DOOR['top'], DOOR['inset']
    r = (z1 - z0) / 2; spring = top - r
    opening = arch(z0, z1, 0, spring)
    zm = (z0 + z1) / 2
    for k, (a_, b_) in enumerate(((z0, zm - 0.04), (zm + 0.04, z1))):
        leaf = opening.intersection(box(a_, 0, b_, top + 1))
        extrude_poly(b, plane, leaf, -inset, -inset + 0.12, PAL['door'] * (1.0 if k else 0.94), WOOD + TURNED)   # grain runs up
    flat_poly(b, plane, opening, -inset - 0.06, PAL['door'] * 0.35)
    # reveal between the wall face and the door
    ring = np.asarray(opening.exterior.coords)
    for i in range(len(ring) - 1):
        (ua, ya), (ub, yb) = ring[i], ring[i + 1]
        if ya < 0.01 and yb < 0.01: continue
        b.add(to_world(plane, [(ua, ya, 0), (ub, yb, 0), (ub, yb, -inset), (ua, ya, -inset)]), [[0, 1, 2], [0, 2, 3]], PAL['trim'], kind=WOOD)
    for u in (zm - 0.75, zm + 0.75):
        knob = to_world(plane, [(u, 9.6, -inset + 0.45)])[0]
        b.add_mesh(sphere(knob, 0.36, 1), PAL['gilt'], kind=METAL)
        b.add_mesh(bar(to_world(plane, [(u, 9.6, -inset + 0.1)])[0], knob, 0.12), PAL['gilt'] * 0.8, kind=METAL)
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
        return (1 - a) ** 2 * 23.0 + 2 * (1 - a) * a * 26.3 + a ** 2 * 32.0      # quadratic bezier (23.0 -> 32.0)
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

def rug(b):
    """the rug's edges (its top is a textured mesh: rug_mesh, pattern from rug.py)"""
    b.add_mesh(cbox(RUG['x0'], RUG['x1'], 0.0, 0.075, RUG['z0'], RUG['z1'], 0.03), half('#3a3058', (40, 34, 56)), kind=CARPET)

def rug_mesh():
    x0, x1, z0, z1, y = RUG['x0'], RUG['x1'], RUG['z0'], RUG['z1'], 0.08
    V = np.array([(x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0)])
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)           # image rows run along z, columns along x
    img = Image.open(os.path.join(HERE, 'data', 'rug.png'))
    mat = trimesh.visual.material.PBRMaterial(baseColorTexture=img, roughnessFactor=1.0, metallicFactor=0.0)
    return trimesh.Trimesh(V, [[0, 2, 1], [0, 3, 2]], visual=trimesh.visual.TextureVisuals(uv=uv, material=mat), process=False)

def ornate_frame(b, plane):
    """the painting's frame: a narrow gilt molding (outer bead, raised torus, cove, inner
    lip), a row of beads along the torus, rosettes at the corners and a shell on top"""
    P = PAINTING
    (z0, z1), (y0, y1) = P['canvas_z'], P['canvas_y']
    M = 0.9                                                         # frame width
    outer = box(z0 - M, y0 - M, z1 + M, y1 + M)
    for a, c, dd, col in ((0.0, 0.2, 0.45, PAL['frame'] * 0.85), (0.2, 0.46, 0.62, PAL['frame'] * 1.1),
                          (0.46, 0.7, 0.4, PAL['frame'] * 0.75), (0.7, M, 0.55, PAL['frame'])):
        ring = outer.buffer(-a, join_style=2).difference(outer.buffer(-c, join_style=2))
        extrude_poly(b, plane, ring, 0, dd, col, METAL)
    # beads along the torus
    r_in = 0.33
    path = [(z0 - M + r_in, y0 - M + r_in), (z1 + M - r_in, y0 - M + r_in), (z1 + M - r_in, y1 + M - r_in), (z0 - M + r_in, y1 + M - r_in)]
    for (ua, ya), (ub, yb) in zip(path, path[1:] + path[:1]):
        n = int(np.hypot(ub - ua, yb - ya) / 0.42)
        for k in range(n):
            t = (k + 0.5) / n
            c = to_world(plane, [(ua + (ub - ua) * t, ya + (yb - ya) * t, 0.6)])[0]
            b.add_mesh(sphere(c, 0.1, 0), PAL['frame'] * 1.2, kind=METAL)
    # rosettes at the corners
    for (u, y) in path:
        c = to_world(plane, [(u, y, 0.75)])[0]
        b.add_mesh(sphere(c, 0.3, 1), PAL['frame'] * 1.15, kind=METAL)
        for k in range(6):
            t = k * np.pi / 3
            cc = to_world(plane, [(u + 0.34 * np.cos(t), y + 0.34 * np.sin(t), 0.68)])[0]
            b.add_mesh(sphere(cc, 0.15, 0), PAL['frame'], kind=METAL)
    # a shell on the top rail, a small acanthus under the bottom one
    um = (z0 + z1) / 2
    for k in range(7):
        t = np.pi * (k + 0.5) / 7
        tip = (um + 0.95 * np.cos(t), y1 + M + 0.15 + 0.75 * np.sin(t))
        pts = to_world(plane, [(um, y1 + M - 0.15, 0.5), (um, y1 + M - 0.15, 0.85), (tip[0], tip[1], 0.45), (tip[0], tip[1], 0.7),
                               (um + 0.3 * np.cos(t - 0.2), y1 + M + 0.1, 0.8), (um + 0.3 * np.cos(t + 0.2), y1 + M + 0.1, 0.8)])
        b.add_mesh(hull(pts), PAL['frame'] * (1.0 + 0.12 * (k % 2)), kind=METAL)
    for dx in (-0.45, 0.0, 0.45):
        c = to_world(plane, [(um + dx, y0 - M - 0.15, 0.55)])[0]
        b.add_mesh(sphere(c, 0.22 if dx else 0.3, 1, (1, 1.3, 1)), PAL['frame'], kind=METAL)

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
    ornate_frame(b, dend)
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

def sweep(b, pts, w, h, color, kind=WOOD):
    """a bar of w x h section along a polyline (each segment a hull of its two end sections)"""
    pts = [np.asarray(p, float) for p in pts]
    for p, q in zip(pts[:-1], pts[1:]):
        a = q - p; a /= np.linalg.norm(a)
        u = np.cross(a, [0, 0, 1] if abs(a[2]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(a, u)
        sec = [s1 * w / 2 * u + s2 * h / 2 * v for s1 in (-1, 1) for s2 in (-1, 1)]
        b.add_mesh(hull([p + o for o in sec] + [q + o for o in sec]), color, kind=kind)

def bez(p0, p1, p2, n=6):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * np.asarray(p0, float) + 2 * (1 - t) * t * np.asarray(p1, float) + t ** 2 * np.asarray(p2, float)

def back_extrude(b, outline, zfun, d0, d1, color, kind):
    """a flat outline (x, y) given thickness along a leaning back (z = zfun(y))"""
    poly = Polygon(outline).buffer(0)
    V2, T = tri_poly(poly)
    for dd in (d0, d1): b.add(np.c_[V2[:, 0], V2[:, 1], zfun(V2[:, 1]) + dd], T, color, kind=kind)
    ring = np.asarray(poly.exterior.coords)
    for i in range(len(ring) - 1):
        (xa, ya), (xc, yc) = ring[i], ring[i + 1]
        b.add([(xa, ya, zfun(ya) + d0), (xc, yc, zfun(yc) + d0), (xc, yc, zfun(yc) + d1), (xa, ya, zfun(ya) + d1)], [[0, 1, 2], [0, 2, 3]], color, kind=kind)

def build_side_chair():
    """local frame: x across, y up, z toward the table; origin on the floor under the seat"""
    b = Builder()
    lean = lambda y: -0.145 * (np.asarray(y) - 4.5)                 # the back leans 0.9 over its 6.2 height
    zb = -2.45                                                      # back edge of the seat
    for sx in (-1, 1):
        # posts: bowing out a little and sweeping back toward the top
        path = [(sx * x, y, zb + lean(y) - 0.12 * ((y - 4.4) / 6.0) ** 2) for x, y in bez((2.35, 4.4), (2.42, 8.2), (2.95, 10.45), 7)]
        sweep(b, path, 0.5, 0.46, PAL['chair'])
        b.add_mesh(cbox(sx * 2.35 - 0.23, sx * 2.35 + 0.23, 0, 4.4, zb - 0.23, zb + 0.23, 0.06), PAL['chair'], kind=WOOD)      # back leg
        for m in cabriole(sx * 2.3, 1.95, 4.0, 0.22, 0.48): b.add_mesh(m, PAL['chair'], kind=WOOD)
    b.add_mesh(cbox(-2.6, 2.6, 3.95, 4.4, -2.55, 2.45, 0.1), PAL['chair'], kind=WOOD)
    V, F = slab_with_holes(rounded_rect(-2.45, 2.45, -2.4, 2.35, 0.35), [], 4.4, 4.64, 0.08)
    b.add(V, F, PAL['back'], group='velvet', kind=CARPET)      # the same crushed velvet as the armchairs
    # the crest rail: one carved piece, swept up into ears at the posts, a bat with
    # scalloped wings spread across the middle
    bottom = [(0, 9.12), (0.22, 9.36), (0.45, 9.52), (0.6, 9.64), (0.85, 9.5), (1.05, 9.64), (1.3, 9.48), (1.5, 9.62), (1.75, 9.44),
              (2.1, 9.36), (2.5, 9.3), (2.9, 9.28)]
    top = [(2.95, 10.5), (2.7, 10.42), (2.4, 10.26), (2.1, 10.12), (1.85, 10.08), (1.7, 10.3), (1.45, 10.12), (1.2, 10.2), (0.95, 10.3),
           (0.7, 10.34), (0.45, 10.42), (0.3, 10.66), (0.16, 10.5), (0, 10.48)]
    right = bottom + top
    outline = right + [(-x, y) for x, y in reversed(right)][1:-1]
    back_extrude(b, outline, lambda y: zb + lean(y), -0.22, 0.22, PAL['chair'], WOOD)
    # the spiderweb, in the lower part of the back: spokes from the middle, three rings, held
    # to the posts and the seat; it stops well short of the crest rail
    cx, cy, rx, ry = 0.0, 6.3, 2.15, 1.6
    W = lambda x, y: (x, y, zb + lean(y))
    ang = [k * np.pi / 4 for k in range(8)]
    outer = [(cx + rx * np.cos(t), cy + ry * np.sin(t)) for t in ang]
    for (ex, ey) in outer: b.add_mesh(bar(W(cx, cy), W(ex, ey), 0.04), PAL['web'], kind=METAL)
    for k in (0.38, 0.68, 1.0):
        pts = [W(cx + (ex - cx) * k, cy + (ey - cy) * k) for ex, ey in outer]
        for i in range(len(pts)): b.add_mesh(bar(pts[i], pts[(i + 1) % len(pts)], 0.035), PAL['web'], kind=METAL)
    # strands from the web to the wood: each continues its spoke's own line outward until it
    # meets a post, the crest rail or the seat
    post_x = lambda y: np.interp(y, [4.4, 6.0, 8.0, 10.45], [2.35, 2.37, 2.5, 2.95]) - 0.25   # inner edge of a post
    for (ex, ey) in outer:
        dx, dy = ex - cx, ey - cy
        for s_ in np.linspace(1.0, 3.0, 400):
            x, y = cx + dx * s_, cy + dy * s_
            if abs(x) >= post_x(y) or y >= 9.2 or y <= 4.64: break
        y = min(max(y, 4.64), 9.2)
        if np.hypot(x - ex, y - ey) > 0.05:      # where the web already touches the wood, no strand
            b.add_mesh(bar(W(ex, ey), W(x, y), 0.035), PAL['web'], kind=METAL)
    for sx in (-1, 1):
        add_parts(b, skull((sx * 2.95, 10.5 + 0.42 * 1.25 - 0.06, zb + float(lean(10.45)) - 0.12)), METAL)   # sitting on the post, above all the wood
    return b.meshes()

def build_armchair():
    """the carvers at the table's ends (measured from cameras 2, 8 and 9): a solid wooden
    back leaning well back, a shield-shaped panel of crushed red velvet set into it, a small
    crown carved on top, skulls on the posts, level arms on curved front supports, a velvet
    seat, cabriole legs with claw-and-ball feet. Returns the wood and the velvet separately
    (the velvet gets a sheen in the viewer)."""
    b = Builder()
    lean = lambda y: -0.2 * (np.asarray(y) - 4.5)                   # 1.25 back over the back's height
    zb = -2.3
    # the back tapers in toward the seat: the posts curve out as they rise
    px = lambda y: 2.05 + 1.35 * np.clip((np.asarray(y) - 4.3) / 6.4, 0, 1) ** 1.4
    for sx in (-1, 1):
        sweep(b, [(sx * float(px(y)), y, zb + float(lean(y))) for y in np.linspace(4.3, 10.7, 9)], 0.52, 0.5, PAL['chair'])
        b.add_mesh(cbox(sx * 2.95 - 0.26, sx * 2.95 + 0.26, 0, 4.3, zb - 0.26, zb + 0.26, 0.06), PAL['chair'], kind=WOOD)
        for m in cabriole(sx * 2.95, 2.25, 3.95, 0.25, 0.55): b.add_mesh(m, PAL['chair'], kind=WOOD)
        b.add_mesh(sphere((sx * 2.95, 0.3, 2.45), 0.36, 1), PAL['claw'], kind=PLAIN)
        # level arm from the post, angling out to the front, a little scroll where it ends
        za = zb + float(lean(6.1))
        sweep(b, [(sx * float(px(6.1)), 6.1, za), (sx * 3.2, 6.1, za + 1.6), (sx * 3.2, 6.1, 2.42)], 0.4, 0.3, PAL['chair'])
        b.add_mesh(sphere((sx * 3.2, 6.0, 2.42), 0.24, 1, (0.85, 1, 1.1)), PAL['chair'], kind=WOOD)
        # front support: up from the seat's corner, bowing forward
        sweep(b, [(sx * 3.2, y, z) for y, z in bez((4.35, 2.1), (5.2, 2.75), (6.0, 2.3), 5)], 0.32, 0.32, PAL['chair'])
        add_parts(b, skull((sx * px(10.7), 10.7 + 0.48 * 1.25 - 0.06, zb + float(lean(10.7))), 0.48), METAL)   # sitting on the post, above all the wood
    # seat frame (front bowed a little) and its velvet cushion
    front = [(x, 2.45 + 0.15 * np.cos(np.pi * x / 6.6)) for x in np.linspace(3.3, -3.3, 9)]
    seat_out = [(3.3, -2.45)] + front + [(-3.3, -2.45)]
    V2, T = tri_poly(Polygon(seat_out))
    for y in (3.9, 4.32):
        b.add(np.c_[V2[:, 0], np.full(len(V2), y), V2[:, 1]], T, PAL['chair'], kind=WOOD)
    ring = seat_out + seat_out[:1]
    for (xa, za_), (xc, zc) in zip(ring[:-1], ring[1:]):
        b.add([(xa, 3.9, za_), (xc, 3.9, zc), (xc, 4.32, zc), (xa, 4.32, za_)], [[0, 1, 2], [0, 2, 3]], PAL['chair'], kind=WOOD)
    cush = Polygon([(x * 0.93, z * 0.95 - 0.05) for x, z in seat_out])
    V, F = slab_with_holes(np.asarray(cush.exterior.coords)[:-1], [], 4.32, 4.56, 0.1)
    b.add(V, F, PAL['back'], group='velvet', kind=CARPET)
    # the back: a solid board between the posts, flat-topped with a small crown in the middle
    top = [(px(10.25) - 0.25, 10.25), (1.05, 10.25), (0.8, 10.5), (0.6, 10.38), (0.35, 10.62), (0.18, 10.5), (0.0, 10.88)]
    right = [(float(px(y)) - 0.25, y) for y in np.linspace(4.6, 10.0, 7)] + top
    board = right + [(-x, y) for x, y in reversed(right)][1:]     # drop only the shared middle point
    back_extrude(b, board, lambda y: zb + lean(y), -0.18, 0.14, PAL['chair'], WOOD)
    # the velvet shield: wide at the top, narrowing down to a rounded point
    shield = [(2.35, 10.02), (2.2, 8.3), (1.8, 6.7), (1.35, 5.85)] + [(1.35 * np.cos(t), 5.85 - 0.65 * np.sin(t)) for t in np.linspace(0.3, np.pi - 0.3, 7)] + \
             [(-1.35, 5.85), (-1.8, 6.7), (-2.2, 8.3), (-2.35, 10.02)]
    shield = np.asarray(Polygon(shield).buffer(0.12, join_style=1).buffer(-0.12, join_style=1).exterior.coords)[:-1]
    bv = Builder()
    back_extrude(bv, shield, lambda y: zb + lean(y), 0.14, 0.36, PAL['back'], CARPET)
    # a gilt bead round the panel
    ring_ = np.r_[shield, shield[:1]]
    for p, q in zip(ring_[:-1], ring_[1:]):
        b.add_mesh(bar((p[0], p[1], zb + float(lean(p[1])) + 0.3), (q[0], q[1], zb + float(lean(q[1])) + 0.3), 0.06, 4), PAL['gold'], kind=METAL)
    out = b.meshes()
    vel = bv.meshes()['lit']
    out['velvet'] = trimesh.util.concatenate([out['velvet'], vel])
    return out

def build_table():
    """the long table: a thick top; at each end two shaped legs that flare at the foot and
    scroll out under the top, joined by a cross-rail (nothing runs along its length).
    Built in world coordinates, then returned in a local frame with its length along z
    (so the wood grain runs the table's length) and the transform that puts it back."""
    b = Builder(); t = TABLE
    zc, cx = (t['z0'] + t['z1']) / 2, (t['x0'] + t['x1']) / 2
    b.add_mesh(cbox(t['x0'], t['x1'], t['top'] - t['thick'], t['top'], t['z0'], t['z1'], 0.14), PAL['table'], kind=WOOD)
    under = t['top'] - t['thick']
    # one leg's outline in (o, y): o is outward from the leg's center, toward the table's side
    leg = Polygon([(-0.75, 0.0), (0.95, 0.0), (0.95, 0.22), (0.55, 0.5), (0.5, 0.9), (0.47, 4.1), (0.68, 4.7), (1.05, 5.3), (1.4, 5.8),
                   (1.6, 6.15), (1.62, under), (-0.55, under), (-0.55, 6.0), (-0.45, 5.5), (-0.47, 0.9), (-0.55, 0.5), (-0.75, 0.22)])
    V2, T = tri_poly(leg)
    ring = np.asarray(leg.exterior.coords)
    for x in t['legs']:
        for side in (-1, 1):
            z_leg = zc + side * t['leg_off']
            Z = lambda o: z_leg + side * o
            for dx in (-0.5, 0.5):
                b.add(np.c_[np.full(len(V2), x + dx), V2[:, 1], Z(V2[:, 0])], T, PAL['table'] * 0.9, kind=WOOD)
            for i in range(len(ring) - 1):
                (oa, ya), (ob, yb) = ring[i], ring[i + 1]
                b.add([(x - 0.5, ya, Z(oa)), (x + 0.5, ya, Z(oa)), (x + 0.5, yb, Z(ob)), (x - 0.5, yb, Z(ob))], [[0, 1, 2], [0, 2, 3]], PAL['table'] * 0.9, kind=WOOD)
        b.add_mesh(cbox(x - 0.35, x + 0.35, 1.5, 2.3, zc - t['leg_off'] + 0.4, zc + t['leg_off'] - 0.4, 0.08), PAL['table'] * 0.85, kind=WOOD)   # cross-rail
        b.add_mesh(cbox(x - 0.7, x + 0.7, under - 0.5, under, zc - t['leg_off'] - 1.2, zc + t['leg_off'] + 1.2, 0.1), PAL['table'] * 0.85, kind=WOOD)   # cleat
    m = b.meshes()['lit']
    to_local = np.linalg.inv(place(cx, zc, np.pi / 2))
    m.apply_transform(to_local)
    return m, place(cx, zc, np.pi / 2)

def build_sideboard():
    b = Builder(); s = SIDEBOARD
    b.add_mesh(cbox(s['x0'], s['x1'], s['top'] - 0.45, s['top'], s['z0'], s['z1'], 0.1), PAL['sideboard'], kind=WOOD)
    b.add_mesh(cbox(s['x0'], s['x1'] - 0.4, s['top'] - 1.35, s['top'] - 0.45, s['z0'] + 0.4, s['z1'] - 0.4, 0.08), PAL['sideboard'] * 0.85, kind=WOOD)
    for x, z in ((s['x0'] + 0.6, s['z0'] + 0.7), (s['x1'] - 0.8, s['z0'] + 0.7), (s['x0'] + 0.6, s['z1'] - 0.7), (s['x1'] - 0.8, s['z1'] - 0.7)):
        for m in cabriole(x, z, s['top'] - 0.45, 0.3 * np.sign(z - (s['z0'] + s['z1']) / 2), 0.6): b.add_mesh(m, PAL['sideboard'], kind=WOOD)
    # a candle on a brass dish where 1995 has a small pale something (camera 2 sees it)
    cx, cz, y = 140.6, -122.8, s['top']
    b.add_mesh(prism(cx, cz, 0.62, y, y + 0.12, 14), PAL['gilt'], kind=METAL)
    b.add_mesh(prism(cx, cz, 0.18, y + 0.12, y + 0.4, 10), PAL['gilt'] * 0.85, kind=METAL)
    b.add_mesh(prism(cx, cz, 0.3, y + 0.4, y + 1.45, 10), PAL['candle'])
    b.add_mesh(sphere((cx + 0.22, y + 1.15, cz + 0.1), 0.09, 0, (1, 2.0, 1)), PAL['candle'])    # a drip
    b.add_mesh(sphere((cx, y + 1.72, cz), 0.11, 1, (1, 2.2, 1)), PAL['flame'], group='glow')
    return b.meshes()

def build_chandelier():
    """wrought iron: a canopy and a chain from the ceiling, a crown of spikes, a turned
    column, five S-scroll arms with curls beneath, spiked candle cups, drip candles, and
    a pointed finial at the bottom"""
    b = Builder(); c = CHANDELIER; x, z = c['x'], c['z']
    iron, accent = PAL['iron'], PAL['gold'] * 0.8
    ring = lambda y, r, n=10: [(x + r * np.cos(t), y, z + r * np.sin(t)) for t in np.linspace(0, 2 * np.pi, n, endpoint=False)]
    b.add_mesh(hull(ring(CEIL, 1.3) + ring(CEIL - 0.45, 0.9) + ring(CEIL - 0.7, 0.3)), iron, kind=METAL)       # canopy
    # chain: links turned alternately
    y = CEIL - 0.7; k = 0
    while y > 24.6:
        rot = k % 2
        pts = [(x + (0.16 * np.cos(t) if rot else 0), y - 0.22 + 0.24 * np.sin(t), z + (0 if rot else 0.16 * np.cos(t))) for t in np.linspace(0, 2 * np.pi, 7)]
        for p, q in zip(pts[:-1], pts[1:]): b.add_mesh(bar(p, q, 0.035, 4), iron, kind=METAL)
        y -= 0.4; k += 1
    # crown: a hoop of upward spikes, hung from the chain by four rods
    for p, q in zip(ring(23.4, 1.5, 16), ring(23.4, 1.5, 16)[1:] + ring(23.4, 1.5, 16)[:1]): b.add_mesh(bar(p, q, 0.06, 4), iron, kind=METAL)
    for t in np.linspace(0, 2 * np.pi, 10, endpoint=False):
        px, pz = x + 1.5 * np.cos(t), z + 1.5 * np.sin(t)
        b.add_mesh(hull([(px + 0.1 * np.cos(a), 23.4, pz + 0.1 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 4, endpoint=False)] + [(px, 24.2, pz)]), iron, kind=METAL)
        b.add_mesh(sphere((px, 24.25, pz), 0.07, 0), accent, kind=METAL)
    for t in np.linspace(0, 2 * np.pi, 4, endpoint=False):
        b.add_mesh(bar((x + 1.5 * np.cos(t), 23.4, z + 1.5 * np.sin(t)), (x, y, z), 0.04, 4), iron, kind=METAL)
    # turned column: knop, collar, vase, bowl, finial
    b.add_mesh(bar((x, y, z), (x, 22.4, z), 0.1, 6), iron, kind=METAL)
    b.add_mesh(sphere((x, 22.0, z), 0.42, 1), iron, kind=METAL)
    b.add_mesh(hull(ring(21.45, 0.75) + ring(21.25, 0.75)), iron, kind=METAL)
    b.add_mesh(hull(ring(21.25, 0.35) + ring(20.5, 0.6) + ring(19.8, 0.4)), iron, kind=METAL)
    b.add_mesh(hull(ring(19.6, 0.95) + ring(19.3, 0.9) + ring(18.4, 0.45) + ring(c['bottom'], 0.22)), iron, kind=METAL)
    b.add_mesh(sphere((x, c['bottom'] - 0.25, z), 0.28, 1), accent, kind=METAL)
    b.add_mesh(hull(ring(c['bottom'] - 0.4, 0.16, 6) + [(x, c['bottom'] - 1.35, z)]), iron, kind=METAL)
    glow = []
    for i in range(c['n']):
        t = np.pi / 2 + i * 2 * np.pi / c['n']
        u = np.array([np.cos(t), 0, np.sin(t)]); o = np.array([x, 0, z])
        P = lambda r_, y_: o + u * r_ + np.array([0, y_, 0])
        # the S-scroll arm: out and down, then up to the cup
        arm = [P(0.6, 19.4), P(1.3, 18.9), P(2.0, 18.8), P(2.6, 19.2), P(3.05, 19.9), P(c['r'], 20.9), P(c['r'], c['arms_y'] - 0.15)]
        for p, q in zip(arm[:-1], arm[1:]): b.add_mesh(bar(p, q, 0.1, 4), iron, kind=METAL)
        # a curl hanging under the arm, and a small spike on its elbow
        curl = [P(1.7 + 0.45 * np.sin(a) * (1 - a / 7.5), 18.85 - 0.5 * (1 - np.cos(a)) * (1 - a / 7.5)) for a in np.linspace(0, 6.0, 10)]
        for p, q in zip(curl[:-1], curl[1:]): b.add_mesh(bar(p, q, 0.05, 4), iron, kind=METAL)
        e = P(2.6, 19.2)
        b.add_mesh(hull([e + np.array([0.08 * np.cos(a), 0, 0.08 * np.sin(a)]) for a in np.linspace(0, 2 * np.pi, 4, endpoint=False)] + [e + np.array([0, 0.55, 0])]), iron, kind=METAL)
        tip = P(c['r'], c['arms_y'])
        # spiked bobeche, candle with a drip, flame
        b.add_mesh(prism(tip[0], tip[2], 0.42, tip[1] - 0.15, tip[1] + 0.1, 8), iron, kind=METAL)
        for a in np.linspace(0, 2 * np.pi, 6, endpoint=False):
            r0 = tip + np.array([0.42 * np.cos(a), 0.1, 0.42 * np.sin(a)])
            b.add_mesh(hull([r0 + np.array([0.06 * np.cos(q), 0, 0.06 * np.sin(q)]) for q in (0, 2.1, 4.2)] + [r0 + np.array([0.12 * np.cos(a), 0.3, 0.12 * np.sin(a)])]), iron, kind=METAL)
        b.add_mesh(prism(tip[0], tip[2], 0.17, tip[1] + 0.1, tip[1] + 1.25, 8), PAL['candle'])
        b.add_mesh(sphere((tip[0] + 0.15 * np.cos(t + 1), tip[1] + 0.8, tip[2] + 0.15 * np.sin(t + 1)), 0.09, 0, (1, 1.8, 1)), PAL['candle'])
        glow.append(hull([(tip[0] + 0.1 * np.cos(a), tip[1] + 1.3, tip[2] + 0.1 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)] + [(tip[0], tip[1] + 1.75, tip[2])]))
    for g in glow: b.add_mesh(g, PAL['flame'], group='glow')
    return b.meshes()

def build_outside():
    """what the windows look out on, by moonlight: rough ground, rolling hills on the
    horizon and a few dead trees (camera 9 sees one through the first bay)"""
    b = Builder()
    cx, cz = (X0 + X1) / 2, (Z0 + Z1) / 2
    yg = -1.2
    n = 48
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    # ground: a big disc under everything (the room's floor covers it inside)
    V = [(cx, yg, cz)] + [(cx + 230 * np.cos(t), yg, cz + 230 * np.sin(t)) for t in ang]
    b.add(V, [[0, 1 + i, 1 + (i + 1) % n] for i in range(n)], half('#3a4636', (24, 30, 26)), kind=CARPET)
    # hills: a ring that rises to an uneven crest
    h = lambda t: 10 + 7 * np.sin(3 * t + 1.0) + 4 * np.sin(7 * t + 2.0) + 2.5 * np.sin(13 * t)
    for i in range(n):
        t0, t1 = ang[i], ang[(i + 1) % n]
        q = [(cx + 120 * np.cos(t0), yg, cz + 120 * np.sin(t0)), (cx + 120 * np.cos(t1), yg, cz + 120 * np.sin(t1)),
             (cx + 210 * np.cos(t1), yg + h(t1), cz + 210 * np.sin(t1)), (cx + 210 * np.cos(t0), yg + h(t0), cz + 210 * np.sin(t0))]
        b.add(q, [[0, 1, 2], [0, 2, 3]], half('#2e3a44', (18, 22, 30)), kind=CARPET)
    # dead trees: a crooked trunk, branching three times
    rng = np.random.default_rng(13)
    def branch(p, d, length, r, depth):
        q = p + d * length
        b.add_mesh(bar(p, q, r, 5), half('#2a221e', (20, 16, 14)), kind=WOOD)
        if depth == 0: return
        for k in range(2 + (depth > 1)):
            nd = d + rng.normal(0, 0.55, 3); nd[1] = abs(nd[1]) * 0.8 + 0.25; nd /= np.linalg.norm(nd)
            branch(q, nd, length * rng.uniform(0.55, 0.75), r * 0.6, depth - 1)
    for (tx, tz, s) in ((150, -183, 1.0), (186, -204, 1.2), (122, -205, 0.9), (234, -158, 1.1), (252, -104, 0.9), (210, -176, 0.8), (165, -240, 1.3)):
        d = np.array([rng.normal(0, 0.15), 1, rng.normal(0, 0.15)]); d /= np.linalg.norm(d)
        branch(np.array([tx, yg, tz]), d, 9 * s, 0.7 * s, 3)
    return b.meshes()['lit']

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
    V = np.array([(X0 + 0.3, y0, z1), (X0 + 0.3, y0, z0), (X0 + 0.3, y1, z0), (X0 + 0.3, y1, z1)])
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
    table, at = build_table()
    scene.add_geometry(table, geom_name='table', node_name='table', transform=at)
    scene.add_geometry(rug_mesh(), geom_name='rug_textured', node_name='rug_textured')
    scene.add_geometry(build_outside(), geom_name='outside', node_name='outside')
    for k, m in build_sideboard().items():
        name = 'sideboard' if k == 'lit' else 'sideboard_' + k
        scene.add_geometry(m, geom_name=name, node_name=name)
    scene.add_geometry(build_iron_rack(), geom_name='iron_rack', node_name='iron_rack')
    for k, m in build_chandelier().items():
        scene.add_geometry(m, geom_name='chandelier_' + k, node_name='chandelier_' + k)
    chair = build_side_chair(); arm = build_armchair()
    print('side chair triangles', sum(len(m.faces) for m in chair.values()), '/ armchair', len(arm['lit'].faces) + len(arm['velvet'].faces))
    for i, (x, z, deg) in enumerate(CHAIRS):
        for part, m in chair.items():
            name = 'chair' if part == 'lit' else 'chair_' + part
            scene.add_geometry(m, geom_name=name, node_name='%s_%02d' % (name, i), transform=place(x, z, np.radians(deg)))
    for k, ((x, z), facing) in enumerate(ARMCHAIRS):
        for part, m in arm.items():
            scene.add_geometry(m, geom_name='armchair_' + part, node_name='armchair_%s_%d' % (part, k), transform=place(x, z, np.pi / 2 * facing))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    scene.export(out)
    ntri = sum(len(scene.geometry[g].faces) for g in [scene.graph[n][1] for n in scene.graph.nodes_geometry])
    print('wrote', out, '%.2f MB' % (os.path.getsize(out) / 1e6), 'triangles placed', ntri)

if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'out', 'toon.glb'))
