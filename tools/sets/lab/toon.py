"""The cartoon mad scientist's lab (HH-Lab Background, number 9) for VR.

    python textures.py                        -> data/plaster.png, data/rock.png
    python toon.py [out.glb]                  -> out/toon.glb

A five-sided stone room under the mansion: a square end with the arched double
door, and a pointed end where the apparatus stands (a riveted column and a
domed boiler, joined by a coil and pipes, under a round window). A tilting
operating table with red straps, a lab table of glassware under a hanging lamp,
a wardrobe, a tall orange wall cabinet, a small red one by the door, a wall
shelf of bottles, a ladder-back chair, a little round table by a candle sconce,
and a trapdoor marked with a red X.

Everything is in 3DMM's own world units (the scene player's coordinates), measured
from the eight original views (lib/cloud.py; the numbers say where they came from).
The palette and the surface textures are the dining room's (dining/toon.py: oak,
gilt, iron, candle, the flagstone floor); the plaster and the rock are this room's
own pictures (textures.py)."""
import sys, os, importlib.util
import numpy as np
import trimesh
from shapely.geometry import Polygon, box, Point, LineString
from shapely.ops import unary_union
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
from toonkit import *

# the dining room's helpers and palette
_spec = importlib.util.spec_from_file_location('dining_toon', os.path.join(HERE, '..', 'dining', 'toon.py'))
D = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(D)
bar, sphere, place, xform, sweep, bez, arch, add_parts = D.bar, D.sphere, D.place, D.xform, D.sweep, D.bez, D.arch, D.add_parts

# ----------------------------------------------------------------- measurements (cloud, cameras 0-7)
XL, XR, ZB = -29.6, 29.6, 26.05          # side walls; the door wall (normals of the wall points)
CL, APEX, CR = (-29.6, -19.22), (0.0, -44.2), (29.6, -18.55)   # the pointed end: two walls meeting at the apex
WALL_H, VAULT = 30.0, 4.0                # walls; the ceiling rises 4 more toward the middle (down-facing points)
BASE = (1.1, 0.35)                       # baseboard height, depth
DOOR = dict(xc=0.64, hw=5.65, spring=13.7, recess=0.65, stone=2.4, stone_out=0.8)   # leaves x -5.0..6.3, jambs to 9.2 / -8.3
PORT = dict(c=(-11.2, 19.7, -34.6), r=3.9)        # round window over the boiler (rays through the wall, cams 0, 2, 4)
BENCH = dict(x0=-28.74, x1=-7.58, z0=-3.0, z1=10.3, top=6.93, tilt=0.216, slab_x0=-26.65, slab_x1=-8.63, slab_z0=-1.76, slab_z1=8.96)
LABT = dict(x0=-7.0, x1=7.0, z0=-22.6, z1=-14.8, top=8.23, shelf=2.72)
COLUMN = dict(x=-21.7, z=-22.2)          # the riveted column (circle fits by height)
BOILER = dict(x=-14.3, z=-27.9, r=4.6, wall=11.5, dome=16.4)
ARMOIRE = dict(x0=22.5, z0=-6.9, z1=6.8, top=21.2)
REDCAB = dict(x0=14.9, x1=19.9, y0=5.2, y1=16.0, front=23.46)
ORANGECAB = dict(u0=-11.1, u1=-1.5, y0=7.2, y1=20.2, depth=3.36)   # on the right-hand slanted wall (u along it)
SHELF = dict(z0=13.3, z1=21.2, y0=12.2, y1=21.1, depth=2.75)       # open shelf on the left wall
CHAIR = dict(x=-14.6, z=23.4)            # against the door wall, facing into the room
SIDETABLE = dict(x=26.9, z=16.4, top=9.4, r=2.3)
SCONCE = dict(z=15.1, y=15.6)
LAMP = dict(x=1.0, z=2.5, y=21.2, r=2.3)
TRAP = dict(x0=-4.3, x1=4.7, z0=-0.6, z1=8.6)     # flush in the floor; the X is centred on (0.2, 4.0)
FUSE = dict(c=(-26.7, 20.5, -19.6))

# ----------------------------------------------------------------- colors: the dining room's, plus the lab's own
PAL = dict(D.PAL)
PAL.update(
    floor=half('#55524f', (66, 60, 54)),                 # the dining room's flagstone, a little warmer (lit 67,53,35)
    stone=half('#6a5848', (72, 54, 42)),                 # the door's rough stone blocks (lit 86,48,31)
    plaster=half('#b0a898', (128, 120, 108)),            # where plaster shows without the picture (window reveal)
    machine=half('#d8ccb0', (120, 104, 82)),             # the apparatus's pale enamel (lit 120,83,49)
    copper=half('#b06438', (92, 52, 30)),
    oak=PAL['table'], oak_lt=PAL['chair'],               # the operating table and lab table are the dining room's oak
    dark_wood=half('#4a3220', (60, 40, 22)),
    wardrobe=half('#7a6038', (96, 78, 48)),              # the wardrobe's olive-brown (camera 3, lit)
    orange_wood=half('#e88a28', (176, 92, 22)),          # the tall wall cabinet (lit 156,69,7)
    red_wood=half('#a8402a', (122, 50, 30)),             # the small cabinet by the door (lit 146,70,47)
    strap=half('#c02818', (118, 34, 20)),                # the operating table's straps
    red_x=half('#d83020', (200, 50, 36)),
    pink=half('#ff5aa8', (176, 62, 112)), yellow=half('#e8b030', (190, 129, 47)), green=half('#50c040', (63, 110, 42)),
    glass=hexc('#c8dce8'), book=half('#8a1c10', (90, 20, 8)), shade=half('#3c4440', (58, 60, 58)),
    bulb=hexc('#fff0c0'), lamp_red=hexc('#ff3020'), lamp_green=hexc('#30e050'), slot=hexc('#ffc840'),
    window_glass=half('#1c2230', (30, 32, 40)), steel=half('#b8b8b0', (120, 112, 100)))

# ----------------------------------------------------------------- shapes
def lathe(b, cx, cz, prof, color, kind=PLAIN, n=18, y0=0.0, group='lit', cap=True):
    """a surface of revolution about the vertical through (cx, cz): prof = [(r, y), ...] bottom to top"""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = []; F = []
    for (r, y) in prof:
        V += [(cx + r * np.cos(t), y0 + y, cz + r * np.sin(t)) for t in a]
    for i in range(len(prof) - 1):
        for j in range(n):
            p, q = i * n + j, i * n + (j + 1) % n
            F += [(p, q + n, q), (p, p + n, q + n)]
    if cap:
        for i, s in ((0, 1), (len(prof) - 1, -1)):
            if prof[i][0] > 1e-3:
                c = len(V); V.append((cx, y0 + prof[i][1], cz))
                for j in range(n):
                    p, q = i * n + j, i * n + (j + 1) % n
                    F.append((c, q, p) if s > 0 else (c, p, q))
    b.add(np.array(V), np.array(F), color, group=group, kind=kind)

def tube(b, pts, r, color, kind=PLAIN, n=8, group='lit'):
    """a round pipe along a polyline"""
    pts = [np.asarray(p, float) for p in pts]
    V = []; F = []
    prev_u = None
    for k, p in enumerate(pts):
        t = (pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]); t /= np.linalg.norm(t)
        u = np.cross(t, [0, 1, 0] if abs(t[1]) < 0.9 else [1, 0, 0]) if prev_u is None else prev_u - t * (prev_u @ t)
        u /= np.linalg.norm(u); prev_u = u; v = np.cross(t, u)
        V += [p + r * (np.cos(a) * u + np.sin(a) * v) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]
    for i in range(len(pts) - 1):
        for j in range(n):
            p, q = i * n + j, i * n + (j + 1) % n
            F += [(p, q, q + n), (p, q + n, p + n)]
    b.add(np.array(V), np.array(F), color, group=group, kind=kind)

def helix(p0, p1, radius, turns, n_per=10):
    """points along a coil from p0 to p1"""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    ax = p1 - p0; L = np.linalg.norm(ax); ax /= L
    u = np.cross(ax, [0, 1, 0] if abs(ax[1]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(ax, u)
    N = int(turns * n_per) + 1
    return [p0 + ax * L * k / (N - 1) + radius * (np.cos(2 * np.pi * turns * k / (N - 1)) * u + np.sin(2 * np.pi * turns * k / (N - 1)) * v) for k in range(N)]

def box_on(b, c, size, color, kind=PLAIN, yaw=0.0, r=0.06, group='lit'):
    """a chamfered box centered on c (x, y, z) of size (w, h, d), turned yaw about y"""
    w, h, d = size
    m = cbox(-w / 2, w / 2, -h / 2, h / 2, -d / 2, d / 2, min(r, w / 3, h / 3, d / 3))
    M = place(c[0], c[2], yaw); M[1, 3] = c[1]
    b.add_mesh(xform(m, M), color, group=group, kind=kind)

def flame(b, x, y, z, h=0.45):
    b.add_mesh(hull([(x + 0.09 * np.cos(a), y, z + 0.09 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)] + [(x, y + h, z)]), PAL['flame'], group='glow')

def candle(b, x, y, z, h=1.0, r=0.17, lit=True):
    b.add_mesh(prism(x, z, r, y, y + h, 10), PAL['candle'])
    if lit: flame(b, x, y + h + 0.05, z)

# ----------------------------------------------------------------- the room
def floor_poly():
    return Polygon([(XL, ZB), (XR, ZB), CR, APEX, CL])

WALLS = [((XR, ZB), (XL, ZB)), ((XL, ZB), CL), (CL, APEX), (APEX, CR), (CR, (XR, ZB))]   # each seen from inside, left to right

def wall_frame(p0, p1):
    p0, p1 = np.array([p0[0], 0, p0[1]], float), np.array([p1[0], 0, p1[1]], float)
    t = p1 - p0; L = np.linalg.norm(t); t /= L
    n = np.array([-t[2], 0, t[0]])                       # inward (the room is on the left going p0 -> p1)
    if n @ (np.array([0, 0, 0.0]) - p0) < 0: n = -n
    return p0, t, n, L

def on_wall(i, u, y, d=0.0):
    p0, t, n, L = wall_frame(*WALLS[i])
    return p0 + t * u + np.array([0, 1, 0]) * y + n * d

def wall_u(i, p):
    p0, t, n, L = wall_frame(*WALLS[i])
    q = np.asarray(p, float) - p0
    return q @ t, q @ n

def door_hole():
    u, _ = wall_u(0, (DOOR['xc'], 0, ZB))
    return arch(u - DOOR['hw'], u + DOOR['hw'], -1, DOOR['spring'], 18)

def port_hole():
    u, _ = wall_u(2, PORT['c'])
    return Point(u, PORT['c'][1]).buffer(PORT['r'], 10)

def walls_textured():
    """the plaster walls, with the door and the round window cut out (textured: plaster.png)"""
    V = []; F = []; UV = []; u_acc = 0.0
    holes = {0: [door_hole()], 2: [port_hole()]}
    for i, (a, c) in enumerate(WALLS):
        p0, t, n, L = wall_frame(a, c)
        poly = box(0, 0, L, WALL_H)
        for h in holes.get(i, []): poly = poly.difference(h)
        # cut into vertical strips so the texture's columns stay straight (and it shades evenly)
        for s in np.arange(0, L, 4.0):
            piece = poly.intersection(box(s, 0, min(s + 4.0, L), WALL_H))
            for g in getattr(piece, 'geoms', [piece]):
                if g.is_empty or g.area < 1e-6: continue
                V2, T = tri_poly(g)
                base = len(V)
                for uu, yy in V2:
                    V.append(p0 + t * uu + np.array([0, yy, 0])); UV.append(((u_acc + uu) / 16.0, yy / 32.0))
                for tr in T:
                    a_, b_, c_ = (base + k for k in tr)
                    # face the room
                    nn = np.cross(np.asarray(V[b_]) - V[a_], np.asarray(V[c_]) - V[a_])
                    F.append((a_, b_, c_) if nn @ n > 0 else (a_, c_, b_))
        u_acc += L
    img = Image.open(os.path.join(HERE, 'data', 'plaster.png'))
    mat = trimesh.visual.material.PBRMaterial(baseColorTexture=img, roughnessFactor=0.95, metallicFactor=0.0)
    return trimesh.Trimesh(np.array(V), np.array(F), visual=trimesh.visual.TextureVisuals(uv=np.array(UV), material=mat), process=False)

def ceiling_textured():
    """the rock ceiling: flat where it meets the walls, rising VAULT toward the middle"""
    fp = floor_poly(); ring = fp.exterior
    def height(x, z):
        d = ring.distance(Point(x, z))
        s = np.clip(d / 11.0, 0, 1); return WALL_H + VAULT * (s * s * (3 - 2 * s))
    idx = {}; V = []; UV = []; F = []
    def vid(x, z):
        k = (round(x, 4), round(z, 4))
        if k not in idx:
            idx[k] = len(V); V.append((x, height(x, z), z)); UV.append((x / 12.0, z / 12.0))
        return idx[k]
    step = 2.0
    for x in np.arange(XL, XR, step):
        for z in np.arange(APEX[1], ZB, step):
            cell = box(x, z, x + step, z + step).intersection(fp)
            for g in getattr(cell, 'geoms', [cell]):
                if g.is_empty or g.area < 1e-6 or g.geom_type != 'Polygon': continue
                V2, T = tri_poly(g)
                ids = [vid(px, pz) for px, pz in V2]
                for tr in T:
                    a_, b_, c_ = (ids[k] for k in tr)
                    pa, pb, pc = (np.array(V[k]) for k in (a_, b_, c_))
                    F.append((a_, b_, c_) if np.cross(pb - pa, pc - pa)[1] < 0 else (a_, c_, b_))   # facing down
    img = Image.open(os.path.join(HERE, 'data', 'rock.png'))
    mat = trimesh.visual.material.PBRMaterial(baseColorTexture=img, roughnessFactor=1.0, metallicFactor=0.0)
    return trimesh.Trimesh(np.array(V), np.array(F), visual=trimesh.visual.TextureVisuals(uv=np.array(UV), material=mat), process=False)

def build_room():
    b = Builder()
    # floor: the dining room's flagstones, with the trapdoor's hole left for its planks
    fl = floor_poly().difference(box(TRAP['x0'], TRAP['z0'], TRAP['x1'], TRAP['z1']))
    for g in getattr(fl, 'geoms', [fl]):
        V2, T = tri_poly(g)
        V3 = np.c_[V2[:, 0], np.zeros(len(V2)), V2[:, 1]]
        if np.cross(V3[T[0, 1]] - V3[T[0, 0]], V3[T[0, 2]] - V3[T[0, 0]])[1] < 0: T = T[:, ::-1]   # facing up
        b.add(V3, T, PAL['floor'], kind=STONE)
    # baseboards, broken at the door
    for i, (a, c) in enumerate(WALLS):
        p0, t, n, L = wall_frame(a, c)
        spans = [(0, L)]
        if i == 0:
            u, _ = wall_u(0, (DOOR['xc'], 0, ZB)); w = DOOR['hw'] + DOOR['stone']
            spans = [(0, u - w), (u + w, L)]
        for s0, s1 in spans:
            P = [p0 + t * s0, p0 + t * s1, p0 + t * s1 + n * BASE[1], p0 + t * s0 + n * BASE[1]]
            hullpts = [p + np.array([0, y, 0]) for p in P for y in (0, BASE[0])]
            b.add_mesh(hull(hullpts), PAL['trim'], kind=WOOD)
    trapdoor(b)
    door(b)
    porthole(b)
    return b

def trapdoor(b):
    """planks flush with the floor, running along z, a red X painted across them"""
    t = TRAP; n = 6; w = (t['x1'] - t['x0']) / n
    for k in range(n):
        shade = PAL['oak'] * (0.94 + 0.12 * ((k * 37) % 5) / 4)
        b.add_mesh(cbox(t['x0'] + k * w + 0.04, t['x0'] + (k + 1) * w - 0.04, -0.3, 0.04, t['z0'], t['z1'], 0.05), shade, kind=WOOD)
    b.add_mesh(cbox(t['x0'] - 0.05, t['x1'] + 0.05, -0.32, -0.02, t['z0'] - 0.05, t['z1'] + 0.05, 0.02), PAL['oak'] * 0.4)
    cx, cz, hl, hw = 0.2, 4.0, 3.6, 0.42                   # the X: two painted strokes
    for ang in (np.radians(43), np.radians(-43)):
        c, s = np.cos(ang), np.sin(ang)
        pts = [(cx + c * a - s * bb, cz + s * a + c * bb) for a, bb in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))]
        V = np.array([(x, 0.06, z) for x, z in pts])
        b.add(V, [[0, 2, 1], [0, 3, 2]], PAL['red_x'], kind=PLAIN)

def door(b):
    """the arched double door, set back in the wall, in a surround of rough stone blocks:
    solid oak leaves, a small barred window in each, two strap hinges a side, push plates"""
    xc, hw, sp, rc = DOOR['xc'], DOOR['hw'], DOOR['spring'], DOOR['recess']
    zf = ZB + rc                                              # the leaves' face (z 26.7)
    opening = arch(xc - hw, xc + hw, 0, sp, 20)
    # the leaves (seen from the room: x falls to the right), vertical grain
    zm = xc
    for k, (a_, b_) in enumerate(((xc - hw, zm - 0.05), (zm + 0.05, xc + hw))):
        leaf = opening.intersection(box(a_, 0, b_, sp + hw + 1))
        V2, T = tri_poly(leaf)
        Vf = np.c_[V2[:, 0], V2[:, 1], np.full(len(V2), zf)]
        b.add(Vf, T, PAL['door'] * (1.0 if k else 0.94), kind=WOOD + TURNED)
        # window: a dark pane with a grid of bars in a pale frame
        wx = xc + (2.3 if k else -2.3); y0, y1, ww = 10.8, 15.1, 1.8
        b.add_mesh(cbox(wx - ww / 2 - 0.22, wx + ww / 2 + 0.22, y0 - 0.22, y1 + 0.22, zf - 0.14, zf + 0.01, 0.04), PAL['steel'] * 0.8, kind=METAL)
        b.add_mesh(cbox(wx - ww / 2, wx + ww / 2, y0, y1, zf - 0.16, zf - 0.13, 0.01), PAL['window_glass'])
        for gx in (wx - ww / 6, wx + ww / 6):
            b.add_mesh(cbox(gx - 0.06, gx + 0.06, y0, y1, zf - 0.2, zf - 0.14, 0.01), PAL['steel'] * 0.8, kind=METAL)
        for gy in np.linspace(y0, y1, 5)[1:-1]:
            b.add_mesh(cbox(wx - ww / 2, wx + ww / 2, gy - 0.06, gy + 0.06, zf - 0.2, zf - 0.14, 0.01), PAL['steel'] * 0.8, kind=METAL)
        # push plate
        px = xc + (1.45 if k else -1.45)
        b.add_mesh(cbox(px - 0.7, px + 0.7, 6.4, 9.2, zf - 0.08, zf + 0.01, 0.03), PAL['steel'], kind=METAL)
        # strap hinges at the outer edge, with a fleur end
        ex = xc + (hw if k else -hw); sgn = -1 if k else 1
        for hy in (4.4, 11.7):
            b.add_mesh(cbox(min(ex, ex + sgn * 3.0), max(ex, ex + sgn * 3.0), hy - 0.28, hy + 0.28, zf - 0.08, zf + 0.01, 0.03), PAL['steel'] * 0.9, kind=METAL)
            b.add_mesh(sphere((ex + sgn * 3.0, hy, zf - 0.05), 0.42, 1, (1, 0.9, 0.25)), PAL['steel'] * 0.9, kind=METAL)
    b.add_mesh(cbox(xc - 0.05, xc + 0.05, 0, sp + hw, zf - 0.02, zf + 0.02, 0.01), PAL['door'] * 0.3)   # the gap between the leaves
    # the reveal round the opening, from the wall face back to the leaves
    ring = np.asarray(opening.exterior.coords)
    for i in range(len(ring) - 1):
        (ua, ya), (ub, yb) = ring[i], ring[i + 1]
        if ya < 0.01 and yb < 0.01: continue
        b.add([(ua, ya, ZB), (ub, yb, ZB), (ub, yb, zf), (ua, ya, zf)], [[0, 1, 2], [0, 2, 3]], PAL['stone'] * 0.7, kind=HAMMERED)
    # the stone surround: jamb blocks up each side, then wedge-shaped blocks round the arch
    rng = np.random.default_rng(3)
    out_z = ZB - DOOR['stone_out']; st = DOOR['stone']
    for side in (-1, 1):
        x_in = xc + side * hw; x_out = x_in + side * st
        ys = [0.0, 2.6, 5.0, 7.7, 10.1, 12.0, sp]
        for k in range(len(ys) - 1):
            j = 0.25 * side * (k % 2)                       # alternating long and short blocks
            xa, xb = sorted((x_in, x_out + j))
            m = cbox(xa, xb, ys[k] + 0.08, ys[k + 1] - 0.08, out_z, ZB + 0.1, 0.18)
            b.add_mesh(m, PAL['stone'] * rng.uniform(0.85, 1.12), kind=HAMMERED)
    nv = 11
    for k in range(nv):
        a0, a1 = np.pi * k / nv + 0.012, np.pi * (k + 1) / nv - 0.012
        r0, r1 = hw, hw + st + 0.2 * (k % 2)
        pts = [(xc + r * np.cos(a), sp + r * np.sin(a), z) for a in (a0, a1) for r in (r0, r1) for z in (out_z, ZB + 0.1)]
        b.add_mesh(hull(pts), PAL['stone'] * rng.uniform(0.85, 1.12), kind=HAMMERED)

def porthole(b):
    """the round window: a plastered reveal through the wall, a dark wooden ring and a cross"""
    p0, t, n, L = wall_frame(*WALLS[2])
    u, _ = wall_u(2, PORT['c']); yc = PORT['c'][1]; r = PORT['r']; depth = 1.2
    a = np.linspace(0, 2 * np.pi, 21)
    for i in range(20):
        q = []
        for aa in (a[i], a[i + 1]):
            q.append(p0 + t * (u + r * np.cos(aa)) + np.array([0, yc + r * np.sin(aa), 0]))
        b.add([q[0], q[1], q[1] - n * depth, q[0] - n * depth], [[0, 2, 1], [0, 3, 2]], PAL['plaster'], kind=HAMMERED)
    # the frame ring, set into the reveal near the outside, and the cross of wooden bars
    for i in range(20):
        pts = []
        for aa in (a[i], a[i + 1]):
            for rr in (r - 0.55, r + 0.02):
                for dd in (-depth + 0.15, -depth + 0.65):
                    pts.append(p0 + t * (u + rr * np.cos(aa)) + np.array([0, yc + rr * np.sin(aa), 0]) + n * dd)
        b.add_mesh(hull(pts), PAL['dark_wood'], kind=WOOD)
    c = p0 + t * u + np.array([0, yc, 0]) - n * (depth - 0.4)
    for dvec, ln in ((t, r), (np.array([0, 1.0, 0]), r)):
        q0, q1 = c - dvec * ln, c + dvec * ln
        b.add_mesh(bar(q0, q1, 0.32, 4), PAL['dark_wood'], kind=WOOD)

# ----------------------------------------------------------------- the operating table
def build_bench():
    b = Builder(); t = BENCH
    x0, x1, z0, z1, top = t['x0'], t['x1'], t['z0'], t['z1'], t['top']
    # the fixed top: planks along x on an apron
    nz = 5; wz = (z1 - z0) / nz
    for k in range(nz):
        b.add_mesh(cbox(x0, x1, top - 0.55, top, z0 + k * wz + 0.03, z0 + (k + 1) * wz - 0.03, 0.08), PAL['oak'] * (0.95 + 0.1 * ((k * 3) % 4) / 3), kind=WOOD)
    for zz in (z0 + 0.4, z1 - 0.4):
        b.add_mesh(cbox(x0 + 0.5, x1 - 0.5, top - 1.6, top - 0.55, zz - 0.3, zz + 0.3, 0.06), PAL['oak'] * 0.85, kind=WOOD)
    for xx in (x0 + 0.6, x1 - 0.6):
        b.add_mesh(cbox(xx - 0.3, xx + 0.3, top - 1.6, top - 0.55, z0 + 0.4, z1 - 0.4, 0.06), PAL['oak'] * 0.85, kind=WOOD + TURNED)
    # legs, and stretchers low down along both sides and across the ends
    for xx in (x0 + 0.6, x1 - 0.6):
        for zz in (z0 + 0.6, z1 - 0.6):
            b.add_mesh(cbox(xx - 0.5, xx + 0.5, 0, top - 0.55, zz - 0.5, zz + 0.5, 0.08), PAL['oak'] * 0.9, kind=WOOD + TURNED)
    for zz in (z0 + 0.6, z1 - 0.6):
        b.add_mesh(cbox(x0 + 1.1, x1 - 1.1, 1.3, 2.1, zz - 0.32, zz + 0.32, 0.06), PAL['oak'] * 0.85, kind=WOOD)
    for xx in (x0 + 0.6, x1 - 0.6):
        b.add_mesh(cbox(xx - 0.32, xx + 0.32, 1.3, 2.1, z0 + 1.1, z1 - 1.1, 0.06), PAL['oak'] * 0.85, kind=WOOD + TURNED)
    # the tilting slab: hinged along its aisle edge, raised toward the wall (12 degrees)
    sx0, sx1, sz0, sz1 = t['slab_x0'], t['slab_x1'], t['slab_z0'], t['slab_z1']
    ang = np.arctan(t['tilt']); hinge_y = -t['tilt'] * sx1 + 6.04                  # top surface at the hinge (7.9)
    slab = Builder()
    L = sx1 - sx0; nzs = 4; wzs = (sz1 - sz0) / nzs
    for k in range(nzs):                                     # local: x from 0 (hinge) to -L, top at y 0
        slab.add_mesh(cbox(-L, 0, -0.8, 0, sz0 + k * wzs + 0.03, sz0 + (k + 1) * wzs - 0.03, 0.08), PAL['oak'] * (1.0 + 0.08 * (k % 2)), kind=WOOD)
    slab.add_mesh(cbox(-L + 0.3, -0.3, -1.4, -0.8, sz0 + 0.5, sz1 - 0.5, 0.06), PAL['oak'] * 0.8, kind=WOOD)
    # the straps: wrists near the raised end, ankles near the hinge, each a red band with a buckle
    for sx in (-L + 3.2, -3.0):
        for sz in (sz0 + 2.2, sz1 - 2.2):
            slab.add_mesh(cbox(sx - 0.9, sx + 0.9, 0.0, 0.45, sz - 0.75, sz + 0.75, 0.1), PAL['strap'], kind=FABRIC)
            slab.add_mesh(cbox(sx - 0.55, sx + 0.55, 0.45, 0.55, sz - 0.45, sz + 0.45, 0.04), PAL['steel'], kind=METAL)
    M = np.eye(4); c, s = np.cos(-ang), np.sin(-ang)
    M[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]; M[:3, 3] = [sx1, hinge_y, 0]
    # (the slab's parts keep their own colors and kinds: move their triangles over)
    for grp, (tris, cols, kinds) in slab.g.items():
        for T3, C3, K3 in zip(tris, cols, kinds):
            P = T3.reshape(-1, 3); P = P @ M[:3, :3].T + M[:3, 3]
            b.add(P, np.arange(len(P)).reshape(-1, 3), C3[0], kind=K3[0])
    # the vise on the corner by the wall
    vx, vz = x0 + 3.2, z0 - 0.2
    b.add_mesh(cbox(vx - 1.6, vx + 1.6, top - 1.6, top + 0.2, vz - 1.2, vz + 0.1, 0.1), PAL['iron'] * 1.4, kind=HAMMERED)
    b.add_mesh(cbox(vx - 1.3, vx + 1.3, top - 1.4, top + 0.1, vz - 2.2, vz - 1.4, 0.1), PAL['iron'] * 1.4, kind=HAMMERED)
    b.add_mesh(bar((vx, top - 0.7, vz - 3.4), (vx, top - 0.7, vz), 0.14, 6), PAL['steel'], kind=METAL)
    b.add_mesh(bar((vx - 1.2, top - 0.7, vz - 3.4), (vx + 1.2, top - 0.7, vz - 3.4), 0.1, 6), PAL['steel'], kind=METAL)
    return b

# ----------------------------------------------------------------- the lab table and its glassware
def round_flask(b, x, y, z, r, liquid, neck=0.8, fill=0.55):
    """a round-bottomed flask: glass shell, the liquid inside up to fill of the bulb"""
    prof = [(0.01, -r)] + [(r * np.sin(a), -r * np.cos(a)) for a in np.linspace(0.3, np.pi * 0.86, 8)] + [(0.28 * r, r * 0.96), (0.26 * r, r + neck)]
    lathe(b, x, z, prof, PAL['glass'], y0=y + r, group='glass', n=16)
    lv = -r + 2 * r * fill
    lp = [(0.01, -r * 0.94)] + [(r * 0.94 * np.sin(a), -r * 0.94 * np.cos(a)) for a in np.linspace(0.3, np.arccos(np.clip(-lv / (r * 0.94), -1, 1)), 6)]
    lathe(b, x, z, lp, liquid, y0=y + r, n=16)

def erlenmeyer(b, x, y, z, r, h, liquid, fill=0.45):
    prof = [(r, 0), (r * 0.98, 0.1), (r * 0.3, h * 0.72), (r * 0.26, h)]
    lathe(b, x, z, prof, PAL['glass'], y0=y, group='glass', n=16)
    lathe(b, x, z, [(r * 0.94, 0.02), (r * 0.94 - (r * 0.64) * fill, h * 0.72 * fill)], liquid, y0=y, n=16)

def bottle(b, x, y, z, r, h, color, glass=False):
    prof = [(r, 0), (r, h * 0.62), (r * 0.42, h * 0.8), (r * 0.36, h)]
    lathe(b, x, z, prof, PAL['glass'] if glass else color, y0=y, group='glass' if glass else 'lit', n=12)
    if glass: lathe(b, x, z, [(r * 0.9, 0.02), (r * 0.9, h * 0.45)], color, y0=y, n=12)
    b.add_mesh(prism(x, z, r * 0.4, y + h, y + h + 0.25, 8), PAL['dark_wood'] * 1.4)   # cork

def build_labtable():
    b = Builder(); t = LABT
    x0, x1, z0, z1, top, sh = t['x0'], t['x1'], t['z0'], t['z1'], t['top'], t['shelf']
    b.add_mesh(cbox(x0, x1, top - 0.5, top, z0, z1, 0.1), PAL['oak'], kind=WOOD + TURNED)
    for xx in (x0 + 0.7, x1 - 0.7):
        for zz in (z0 + 0.7, z1 - 0.7):
            b.add_mesh(cbox(xx - 0.42, xx + 0.42, 0, top - 0.5, zz - 0.42, zz + 0.42, 0.06), PAL['oak'] * 0.9, kind=WOOD + TURNED)
    b.add_mesh(cbox(x0 + 0.3, x1 - 0.3, top - 1.3, top - 0.5, z1 - 0.9, z1 - 0.5, 0.05), PAL['oak'] * 0.85, kind=WOOD)
    b.add_mesh(cbox(x0 + 0.3, x1 - 0.3, sh - 0.3, sh, z0 + 0.4, z1 - 0.4, 0.06), PAL['oak'] * 0.88, kind=WOOD + TURNED)
    # on the shelf: a row of flasks and bottles (amber, clear, a little color)
    shelf_items = [(-5.4, 'b', 0.65, 2.2, PAL['yellow'] * 0.7), (-3.6, 'f', 0.85, 0, PAL['green'] * 0.8), (-1.6, 'b', 0.55, 2.6, PAL['glass']),
                   (0.3, 'f', 1.0, 0, PAL['yellow']), (2.4, 'b', 0.6, 1.9, PAL['pink'] * 0.8), (4.3, 'f', 0.8, 0, PAL['glass']), (5.8, 'b', 0.5, 2.3, PAL['yellow'] * 0.6)]
    for k, (x, kind, r, h, col) in enumerate(shelf_items):
        z = (z0 + z1) / 2 + (0.9 if k % 2 else -0.8)
        if kind == 'b': bottle(b, x, sh, z, r, h, col, glass=True)
        else: round_flask(b, x, sh, z, r, col, neck=0.7, fill=0.75)
    # on top: the pink flask on a tripod over a candle, joined by a glass coil to the green tube
    fx, fz = -1.8, -18.1
    for a in np.radians([90, 210, 330]):
        b.add_mesh(bar((fx + 1.15 * np.cos(a), top, fz + 1.15 * np.sin(a)), (fx + 0.85 * np.cos(a), top + 1.45, fz + 0.85 * np.sin(a)), 0.07, 4), PAL['iron'] * 1.3, kind=METAL)
    tube(b, [(fx + 0.85 * np.cos(a), top + 1.45, fz + 0.85 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 13)], 0.07, PAL['iron'] * 1.3, kind=METAL)
    candle(b, fx, top, fz, 0.7, 0.2)
    b.add_mesh(prism(fx, fz, 0.42, top, top + 0.08, 10), PAL['gilt'], kind=METAL)
    round_flask(b, fx, top + 1.45, fz, 1.05, PAL['pink'], neck=1.1, fill=0.82)
    b.add_mesh(prism(fx, fz, 0.32, top + 1.45 + 1.9 + 1.0, top + 1.45 + 1.9 + 1.4, 8), PAL['dark_wood'] * 1.4)   # stopper
    neck_top = np.array([fx, top + 1.45 + 1.9 + 1.4, fz])
    # the tall stand with the green tube at its top
    sx, sz = 2.6, -14.9
    b.add_mesh(cbox(sx - 1.0, sx + 1.0, top, top + 0.25, sz - 0.7, sz + 0.7, 0.08), PAL['iron'] * 1.2, kind=METAL)
    b.add_mesh(bar((sx, top, sz), (sx, 17.6, sz), 0.12, 6), PAL['iron'] * 1.2, kind=METAL)
    gx, gz = 1.9, -15.2
    b.add_mesh(bar((sx, 15.4, sz), (gx, 15.4, gz), 0.08, 4), PAL['steel'], kind=METAL)
    lathe(b, gx, gz, [(0.42, 0), (0.42, 2.2)], PAL['glass'], y0=14.4, group='glass', n=12)
    lathe(b, gx, gz, [(0.36, 0.05), (0.36, 1.9)], PAL['green'], y0=14.4, n=12)
    tube(b, [neck_top + (0, 0.1, 0)] + list(helix(neck_top + np.array([0.6, 0.6, 0.6]), np.array([gx, 14.2, gz]) + np.array([-0.6, -0.2, -0.4]), 0.55, 3.2)) + [np.array([gx, 14.4, gz])], 0.09, PAL['glass'], group='glass', n=6)
    # the ring stand with a test tube in its clamp
    rx, rz = -1.15, -20.9
    b.add_mesh(cbox(rx - 0.9, rx + 0.9, top, top + 0.22, rz - 0.6, rz + 0.6, 0.08), PAL['iron'] * 1.2, kind=METAL)
    b.add_mesh(bar((rx, top, rz), (rx, 13.6, rz), 0.1, 6), PAL['iron'] * 1.2, kind=METAL)
    b.add_mesh(bar((rx, 12.0, rz), (-2.25, 12.0, -21.4), 0.07, 4), PAL['steel'], kind=METAL)
    lathe(b, -2.25, -21.4, [(0.01, 0), (0.28, 0.25), (0.3, 4.2)], PAL['glass'], y0=9.3, group='glass', n=10)
    lathe(b, -2.25, -21.4, [(0.01, 0.03), (0.24, 0.25), (0.25, 1.6)], PAL['steel'] * 0.9, y0=9.3, n=10)
    # the yellow conical flask, and a red book
    erlenmeyer(b, 1.65, top, -20.6, 1.0, 2.4, PAL['yellow'], fill=0.7)
    box_on(b, (-4.7, top + 0.22, -20.4), (3.4, 0.44, 2.5), PAL['book'], kind=FABRIC, yaw=0.15, r=0.08)
    box_on(b, (-4.75, top + 0.22, -20.4), (3.2, 0.36, 2.42), PAL['candle'] * 0.9, yaw=0.15, r=0.02)
    return b

# ----------------------------------------------------------------- the apparatus
def build_apparatus():
    b = Builder(); cx, cz = COLUMN['x'], COLUMN['z']
    col = PAL['machine']
    # the column: a foot, a tapering stem, a collar, a riveted drum, a cap and a little dome
    lathe(b, cx, cz, [(3.4, 0), (3.4, 0.6), (2.9, 0.9), (2.4, 4.6), (2.7, 7.6), (3.2, 8.6)], col, kind=HAMMERED, n=24)
    lathe(b, cx, cz, [(3.7, 8.4), (3.7, 9.5)], PAL['copper'] * 0.8, kind=METAL, n=24)
    lathe(b, cx, cz, [(3.9, 9.5), (4.05, 10.0), (4.05, 17.2), (3.7, 17.8)], col, kind=HAMMERED, n=24)
    lathe(b, cx, cz, [(3.3, 17.8), (3.1, 20.4), (2.2, 21.0), (1.6, 21.6)], col, kind=HAMMERED, n=24)
    lathe(b, cx, cz, [(1.6, 21.6), (1.5, 22.6), (1.1, 23.5), (0.3, 24.0)], col * 0.9, kind=HAMMERED, n=16)
    lathe(b, cx, cz, [(1.75, 22.0), (1.75, 22.5)], PAL['copper'] * 0.8, kind=METAL, n=16)
    for ry in (10.4, 16.6):                                   # rivet rows
        for a in np.linspace(0, 2 * np.pi, 28, endpoint=False):
            b.add_mesh(sphere((cx + 4.08 * np.cos(a), ry, cz + 4.08 * np.sin(a)), 0.13, 0), col * 0.8)
    # the lights, red over green, on the side facing the room
    a = np.arctan2(0 - cz, 0 - cx) + 0.25
    for y, c in ((14.3, PAL['lamp_red']), (13.1, PAL['lamp_green'])):
        b.add_mesh(sphere((cx + 4.1 * np.cos(a), y, cz + 4.1 * np.sin(a)), 0.32, 1), c, group='glow')
    # two heavy hoses looping off the drum's left side
    side = np.arctan2(0 - cz, 0 - cx) - 1.1
    sv = np.array([np.cos(side), 0, np.sin(side)]); up = np.array([0, 1, 0]); cc = np.array([cx, 0, cz])
    for k, off in enumerate((-0.6, 0.6)):
        q0 = cc + sv * 4.0 + up * 17.0 + np.array([0, 0, off])
        q1 = cc + sv * 4.0 + up * 12.0 + np.array([0, 0, off])
        tube(b, list(bez(q0, q0 + sv * 3.0 + up * 0.5, q1 + sv * 2.6, 9)) , 0.42, PAL['copper'] * 0.75, kind=METAL, n=10)
    # pipes coiling from the column's foot round to the boiler
    bx, bz = BOILER['x'], BOILER['z']
    for y in (1.3, 2.6):
        pts = [np.array([cx + 2.9 * np.cos(a), y, cz + 2.9 * np.sin(a)]) for a in np.linspace(np.pi * 0.2, np.pi * 1.6, 10)]
        pts += [np.array([(cx + bx) / 2 + 1.0, y, (cz + bz) / 2 + 1.5]), np.array([bx + 4.4 * np.cos(2.4), y, bz + 4.4 * np.sin(2.4)])]
        tube(b, pts, 0.38, col * 0.95, kind=METAL, n=10)
    # the boiler: a drum, a dome, a finial; a control panel and a glowing slot facing the room
    R = BOILER['r']
    lathe(b, bx, bz, [(R, 0), (R, BOILER['wall'])] + [(R * np.cos(a), BOILER['wall'] + (BOILER['dome'] - BOILER['wall']) * np.sin(a)) for a in np.linspace(0.15, np.pi / 2 - 0.05, 7)], col, kind=HAMMERED, n=28)
    lathe(b, bx, bz, [(R + 0.15, 0), (R + 0.15, 0.7)], col * 0.8, kind=HAMMERED, n=28)
    lathe(b, bx, bz, [(0.9, 16.2), (0.6, 17.4), (0.3, 18.2), (0.32, 21.0), (0.55, 21.4), (0.3, 22.1)], PAL['copper'], kind=METAL, n=12)
    b.add_mesh(sphere((bx, 19.4, bz), 0.6, 1), PAL['copper'], kind=METAL)
    face = np.arctan2(-4.0 - bz, 0 - bx)
    fv = np.array([np.cos(face), 0, np.sin(face)]); rv = np.array([-fv[2], 0, fv[0]])
    # panel: a slab hugging the front, knobs and dials on it, the slot above
    pc = np.array([bx, 0, bz]) + fv * (R + 0.05)
    def on_front(du, y, dd): return pc + rv * du + up * y + fv * dd
    P = [on_front(du, y, dd) for du in (-2.2, 2.2) for y in (3.2, 8.4) for dd in (0.0, 0.35)]
    b.add_mesh(hull(P), col * 0.88, kind=HAMMERED)
    rng = np.random.default_rng(5)
    for du in np.linspace(-1.6, 1.6, 5):
        for y in (4.2, 5.4, 6.6):
            b.add_mesh(sphere(on_front(du, y, 0.42), 0.2, 0, (1, 1, 0.6)), PAL['iron'] * 1.2 if rng.random() < 0.7 else PAL['copper'])
    for du, y in ((-1.3, 7.6), (1.3, 7.6)):
        b.add_mesh(sphere(on_front(du, y, 0.4), 0.38, 1, (1, 1, 0.3)), PAL['steel'], kind=METAL)
    S = [on_front(du, y, 0.12) for du in (-0.32, 0.32) for y in (8.9, 11.6)]
    b.add_mesh(hull(S + [s - fv * 0.3 for s in S]), PAL['slot'], group='glow')
    side_pc = np.array([bx, 0, bz]) + (fv * np.cos(-0.9) + rv * np.sin(-0.9)) * (R + 0.05)
    b.add_mesh(sphere(side_pc + up * 7.9, 0.22, 1), PAL['lamp_red'], group='glow')
    b.add_mesh(sphere(side_pc + up * 7.9 + rv * 0.6, 0.22, 1), PAL['lamp_green'], group='glow')
    # the coil of insulators arching from the column's top to the boiler's finial
    p0 = np.array([cx + 0.6, 24.2, cz - 0.2]); p1 = np.array([bx, 21.5, bz])
    for k, s in enumerate(np.linspace(0, 1, 9)):
        p = p0 * (1 - s) + p1 * s + np.array([0, 3.2 * np.sin(np.pi * s), 0]) + np.array([1.2, 0, 1.2]) * np.sin(np.pi * s)
        b.add_mesh(sphere(p, 0.42, 1, (1, 0.8, 1)), PAL['copper'] * (0.9 if k % 2 else 0.7), kind=METAL)
    tube(b, [p0 * (1 - s) + p1 * s + np.array([0, 3.2 * np.sin(np.pi * s), 0]) + np.array([1.2, 0, 1.2]) * np.sin(np.pi * s) for s in np.linspace(0, 1, 17)], 0.12, PAL['iron'] * 1.2, kind=METAL)
    # the fuse box on the wall, with cables down to the column and up into the ceiling
    fc = np.array(FUSE['c']); p0w, tw, nw, Lw = wall_frame(*WALLS[2])
    fb = [fc + tw * du + up * dy + nw * dd for du in (-1.5, 1.5) for dy in (-2.6, 2.6) for dd in (-0.1, 0.9)]
    b.add_mesh(hull(fb), PAL['dark_wood'] * 1.3, kind=WOOD)
    b.add_mesh(hull([fc + tw * du + up * dy + nw * 0.95 for du in (-1.2, 1.2) for dy in (-2.2, 2.2)] + [fc + tw * du + up * dy + nw * 1.0 for du in (-1.2, 1.2) for dy in (-2.2, 2.2)]), PAL['copper'] * 0.6)
    for du in (-0.7, 0.7):
        tube(b, [fc + tw * du + up * 2.6 + nw * 0.4, fc + tw * du + up * 9.0 + nw * 0.4], 0.12, PAL['iron'], n=6)
    tube(b, list(bez(fc - up * 2.6 + nw * 0.4, fc - up * 8 + nw * 1.0, np.array([cx, 15.0, cz]) + (fc - np.array([cx, 0, cz])) * 0.0 + np.array([-3.2, 0, 1.6]), 8)), 0.14, PAL['iron'], n=6)
    return b

# ----------------------------------------------------------------- furniture
def build_wardrobe():
    """the tall wardrobe against the right wall: two panelled doors over three drawers, a
    cornice, books on top. Built facing +z at the origin, then turned to face the room (-x)."""
    b = Builder(); a = ARMOIRE
    W = a['z1'] - a['z0']; Dp = XR - a['x0']; top = a['top']; wood = PAL['wardrobe']
    b.add_mesh(cbox(-W / 2 - 0.2, W / 2 + 0.2, 0, 1.0, -Dp, 0.2, 0.08), wood * 0.8, kind=WOOD)
    b.add_mesh(cbox(-W / 2, W / 2, 1.0, top - 1.2, -Dp, 0, 0.06), wood, kind=WOOD + TURNED)
    for y0, y1, o in ((top - 1.2, top - 0.8, 0.2), (top - 0.8, top - 0.25, 0.42), (top - 0.25, top, 0.3)):
        b.add_mesh(cbox(-W / 2 - o, W / 2 + o, y0, y1, -Dp, o, 0.06), wood * 1.05, kind=WOOD)
    for k, (u0, u1) in enumerate(((-W / 2 + 0.3, -0.04), (0.04, W / 2 - 0.3))):
        b.add_mesh(cbox(u0, u1, 10.2, top - 1.5, -0.05, 0.12, 0.03), wood * (1.06 if k else 1.0), kind=WOOD + TURNED)
        for py0, py1 in ((10.8, 14.6), (15.2, top - 2.1)):
            b.add_mesh(cbox(u0 + 0.45, u1 - 0.45, py0, py1, 0.12, 0.26, 0.08), wood * 1.12, kind=WOOD + TURNED)
        b.add_mesh(sphere(((0.35 if k else -0.35), 12.6, 0.3), 0.2, 1), PAL['gilt'], kind=METAL)
    for k, (y0, y1) in enumerate(((1.3, 3.9), (4.1, 6.8), (7.0, 9.8))):
        b.add_mesh(cbox(-W / 2 + 0.3, W / 2 - 0.3, y0, y1, -0.05, 0.14, 0.04), wood * (1.02 + 0.04 * (k % 2)), kind=WOOD)
        for sx in (-W / 4, W / 4):
            b.add_mesh(sphere((sx, (y0 + y1) / 2, 0.3), 0.2, 1), PAL['gilt'], kind=METAL)
    for k, (bz, h, col) in enumerate(((-2.0, 2.1, PAL['book']), (-1.3, 2.5, PAL['dark_wood'] * 0.6), (-0.65, 1.9, PAL['book'] * 1.2))):
        b.add_mesh(cbox(bz - 0.3, bz + 0.3, top, top + h, -Dp + 1.2, -Dp + 3.2, 0.04), col, kind=FABRIC)
    return b, place(a['x0'], (a['z0'] + a['z1']) / 2, -np.pi / 2)

def glazed_cabinet(b, W, H, Dp, wood, panes=(2, 2), crown=True, foot=True):
    """a wall cabinet facing +z, back on z = -Dp, from y 0 to H: glazed doors on a carcase"""
    b.add_mesh(cbox(-W / 2, W / 2, 0, H, -Dp, 0, 0.06), wood, kind=WOOD + TURNED)
    b.add_mesh(cbox(-W / 2 + 0.35, W / 2 - 0.35, 0.5, H - 0.5, -Dp + 0.2, 0.0, 0.02), wood * 0.55, kind=WOOD + TURNED)   # the inside
    b.add_mesh(cbox(-W / 2 + 0.35, W / 2 - 0.35, 0.5, H - 0.5, -0.02, 0.02, 0.01), PAL['glass'], group='glass')
    b.add_mesh(cbox(-W / 2 + 0.4, W / 2 - 0.4, H / 2 - 0.12, H / 2 + 0.12, -Dp + 0.2, -0.1, 0.02), wood, kind=WOOD)   # a shelf
    cols, rows = panes
    for k in range(cols + 1):
        x = -W / 2 + 0.35 + k * (W - 0.7) / cols
        b.add_mesh(cbox(x - 0.18, x + 0.18, 0.4, H - 0.4, -0.05, 0.12, 0.03), wood * 1.1, kind=WOOD + TURNED)
    for k in range(rows + 1):
        y = 0.5 + k * (H - 1.0) / rows
        b.add_mesh(cbox(-W / 2 + 0.3, W / 2 - 0.3, y - 0.16, y + 0.16, -0.05, 0.12, 0.03), wood * 1.1, kind=WOOD)
    if crown:
        b.add_mesh(cbox(-W / 2 - 0.35, W / 2 + 0.35, H, H + 0.55, -Dp, 0.35, 0.08), wood * 1.08, kind=WOOD)
    if foot:
        b.add_mesh(cbox(-W / 2 - 0.25, W / 2 + 0.25, -0.5, 0, -Dp, 0.25, 0.08), wood * 0.9, kind=WOOD)
        b.add_mesh(hull([(sx * W / 2 * 0.8, y, z) for sx in (-1, 1) for y, z in ((-0.5, -Dp), (-0.5, 0.0), (-2.0, -Dp))]), wood * 0.85, kind=WOOD)

def build_orange_cabinet():
    """the tall orange cabinet on the right-hand slanted wall: a pair of doors with raised
    panels, a cornice, a ledge beneath on a shaped bracket, small bottles on top"""
    b = Builder(); c = ORANGECAB
    W = c['u1'] - c['u0']; H = c['y1'] - c['y0'] - 0.6; Dp = c['depth']; wood = PAL['orange_wood']
    b.add_mesh(cbox(-W / 2, W / 2, 0, H, -Dp, 0, 0.06), wood * 0.92, kind=WOOD + TURNED)
    for k, (u0, u1) in enumerate(((-W / 2 + 0.3, -0.05), (0.05, W / 2 - 0.3))):
        b.add_mesh(cbox(u0, u1, 0.35, H - 0.35, -0.05, 0.14, 0.04), wood * (1.04 if k else 1.0), kind=WOOD + TURNED)
        for py0, py1 in ((0.9, H * 0.42), (H * 0.42 + 0.6, H - 0.9)):
            b.add_mesh(cbox(u0 + 0.6, u1 - 0.6, py0, py1, 0.14, 0.34, 0.12), wood * 1.1, kind=WOOD + TURNED)
        b.add_mesh(sphere(((0.35 if k else -0.35), H * 0.45, 0.32), 0.17, 1), PAL['gilt'], kind=METAL)
    b.add_mesh(cbox(-W / 2 - 0.35, W / 2 + 0.35, H, H + 0.55, -Dp, 0.35, 0.08), wood * 1.08, kind=WOOD)
    b.add_mesh(cbox(-W / 2 - 0.6, W / 2 + 0.6, -0.5, 0, -Dp, 0.6, 0.08), wood * 0.95, kind=WOOD)
    b.add_mesh(hull([(sx * W / 2 * 0.85, y, z) for sx in (-1, 1) for y, z in ((-0.5, -Dp), (-0.5, 0.2), (-2.2, -Dp))]), wood * 0.85, kind=WOOD)
    for k, x in enumerate((-W / 2 + 0.9, -W / 2 + 1.7, W / 2 - 1.2)):           # and three small bottles on top
        bottle(b, x, H + 0.55, -Dp / 2, 0.3, 1.0, PAL['yellow'] * 0.8, glass=True)
    # place: centered on the measured span of the slanted right wall (wall 3: apex -> right corner;
    # the cloud's u along that wall put the apex at -29.46)
    p0, t, n, L = wall_frame(*WALLS[3])
    ucen = (c['u0'] + c['u1']) / 2 + 29.46
    pos = p0 + t * ucen + n * Dp
    yaw = np.arctan2(n[0], n[2])
    M = place(pos[0], pos[2], yaw); M[1, 3] = c['y0'] + 0.5
    return b, M

def build_red_cabinet():
    b = Builder(); c = REDCAB
    W = c['x1'] - c['x0']; H = c['y1'] - c['y0'] - 0.6; Dp = ZB - c['front']
    glazed_cabinet(b, W, H, Dp, PAL['red_wood'], panes=(2, 2), foot=False)
    b.add_mesh(cbox(-W / 2 - 0.3, W / 2 + 0.3, -0.6, 0, -Dp, 0.3, 0.06), PAL['red_wood'] * 0.85, kind=WOOD)
    for k, x in enumerate((-1.2, 0.3, 1.4)):
        bottle(b, x, 0.6 + (H / 2) * (k % 2), -Dp / 2, 0.35, 1.5, (PAL['green'], PAL['pink'], PAL['yellow'])[k], glass=True)
    bottle(b, -0.8, H + 0.55, -Dp / 2, 0.45, 1.8, PAL['dark_wood'] * 0.8)
    M = place((c['x0'] + c['x1']) / 2, c['front'], np.pi); M[1, 3] = c['y0'] + 0.6
    return b, M

def build_shelf():
    """the open shelf on the left wall: two shelves of bottles in a frame"""
    b = Builder(); s = SHELF
    W = s['z1'] - s['z0']; H = s['y1'] - s['y0']; Dp = s['depth']; wood = PAL['dark_wood'] * 1.2
    for sx in (-W / 2, W / 2):
        b.add_mesh(cbox(sx - 0.25, sx + 0.25, 0, H, -Dp, 0, 0.05), wood, kind=WOOD + TURNED)
    for y in (0.0, H / 2, H - 0.4):
        b.add_mesh(cbox(-W / 2, W / 2, y, y + 0.4, -Dp, 0, 0.05), wood, kind=WOOD)
    b.add_mesh(cbox(-W / 2, W / 2, 0, H, -Dp, -Dp + 0.15, 0.02), wood * 0.7, kind=WOOD + TURNED)
    rng = np.random.default_rng(9)
    for yb in (0.4, H / 2 + 0.4):
        for k, x in enumerate(np.linspace(-W / 2 + 0.9, W / 2 - 0.9, 5)):
            h = rng.uniform(1.3, 2.6)
            bottle(b, x, yb, -Dp / 2, rng.uniform(0.3, 0.5), h, (PAL['green'], PAL['yellow'], PAL['glass'], PAL['pink'], PAL['yellow'])[k] * rng.uniform(0.7, 1.0), glass=k % 3 != 1)
    M = place(XL + Dp, (s['z0'] + s['z1']) / 2, np.pi / 2); M[1, 3] = s['y0']
    return b, M

def build_chair():
    """the ladder-back chair: turned posts, three slats, a rush seat; facing +z at the origin"""
    b = Builder(); wood = PAL['oak'] * 0.85
    w, d, seat = 4.6, 4.2, 6.0
    for sx in (-1, 1):
        b.add_mesh(prism(sx * (w / 2 - 0.3), -d / 2 + 0.3, 0.28, 0, 13.0, 8), wood, kind=WOOD)          # back posts
        b.add_mesh(sphere((sx * (w / 2 - 0.3), 13.25, -d / 2 + 0.3), 0.36, 1), wood, kind=WOOD)
        b.add_mesh(prism(sx * (w / 2 - 0.3), d / 2 - 0.3, 0.28, 0, seat, 8), wood, kind=WOOD)            # front legs
    for y in (8.0, 9.9, 11.8):
        b.add_mesh(cbox(-w / 2 + 0.3, w / 2 - 0.3, y - 0.42, y + 0.42, -d / 2 + 0.15, -d / 2 + 0.45, 0.06), wood, kind=WOOD)
    for y in (1.5, 3.2):
        b.add_mesh(bar((-w / 2 + 0.3, y, d / 2 - 0.3), (w / 2 - 0.3, y, d / 2 - 0.3), 0.15, 6), wood, kind=WOOD)
        for sx in (-1, 1):
            b.add_mesh(bar((sx * (w / 2 - 0.3), y, -d / 2 + 0.3), (sx * (w / 2 - 0.3), y, d / 2 - 0.3), 0.15, 6), wood, kind=WOOD)
    b.add_mesh(cbox(-w / 2 + 0.05, w / 2 - 0.05, seat - 0.45, seat, -d / 2 + 0.1, d / 2 - 0.05, 0.12), PAL['oak_lt'] * 0.9, kind=FABRIC)
    return b, place(CHAIR['x'], CHAIR['z'], np.pi)

def build_sidetable():
    """the little round table by the sconce: a tripod pedestal, a green flask and a box on it;
    and the sconce: a bracket with a lit candle"""
    b = Builder(); t = SIDETABLE; x, z, top, r = t['x'], t['z'], t['top'], t['r']
    wood = PAL['red_wood'] * 0.7
    lathe(b, x, z, [(r, top - 0.35), (r, top)], wood, kind=WOOD, n=24)
    lathe(b, x, z, [(0.35, 1.4), (0.5, 3.0), (0.3, 5.5), (0.42, top - 1.2), (0.6, top - 0.35)], wood, kind=WOOD, n=10)
    for a in np.radians([30, 150, 270]):
        tube(b, [np.array([x, 1.8, z]), np.array([x + 1.0 * np.cos(a), 0.9, z + 1.0 * np.sin(a)]), np.array([x + 1.8 * np.cos(a), 0.25, z + 1.8 * np.sin(a)]), np.array([x + 2.0 * np.cos(a), 0.0, z + 2.0 * np.sin(a)])], 0.22, wood, kind=WOOD, n=6)
    round_flask(b, x - 0.4, top, z - 0.6, 0.75, PAL['green'], neck=0.6, fill=0.7)
    box_on(b, (x + 0.2, top + 0.4, z + 0.9), (1.2, 0.8, 1.0), PAL['red_wood'], kind=WOOD, yaw=0.3)
    # the sconce on the wall above
    sz, sy = SCONCE['z'], SCONCE['y']
    b.add_mesh(cbox(XR - 0.25, XR, sy - 1.2, sy + 1.2, sz - 0.6, sz + 0.6, 0.08), PAL['iron'] * 1.4, kind=HAMMERED)
    tube(b, [np.array([XR - 0.2, sy, sz]), np.array([XR - 1.0, sy + 0.2, sz]), np.array([XR - 1.4, sy + 1.0, sz])], 0.14, PAL['iron'] * 1.4, kind=METAL, n=6)
    lathe(b, XR - 1.45, sz, [(0.2, 0), (0.5, 0.35), (0.55, 0.45)], PAL['iron'] * 1.4, y0=sy + 1.0, kind=METAL, n=10)
    candle(b, XR - 1.45, sy + 1.45, sz, 1.0, 0.2)
    return b

def build_lamp():
    """the hanging lamp: a cord from the ceiling, a dark dome shade, a bare bulb"""
    b = Builder(); l = LAMP; x, z, y, r = l['x'], l['z'], l['y'], l['r']
    b.add_mesh(bar((x, y + 1.4, z), (x, WALL_H + VAULT, z), 0.06, 4), PAL['iron'])
    lathe(b, x, z, [(r, 0), (r * 0.95, 0.25), (r * 0.7, 0.8), (0.45, 1.2), (0.3, 1.45)], PAL['shade'], y0=y, kind=METAL, n=24, cap=False)
    lathe(b, x, z, [(r * 0.94, 0.02), (r * 0.66, 0.78), (0.42, 1.15)], PAL['shade'] * 0.5, y0=y, n=24, cap=False)
    b.add_mesh(sphere((x, y + 0.45, z), 0.45, 1, (1, 1.2, 1)), PAL['bulb'], group='glow')
    return b

# ----------------------------------------------------------------- assemble
def add_builder(scene, b, name, M=None):
    for k, m in b.meshes().items():
        nm = name if k == 'lit' else name + '_' + k
        scene.add_geometry(m, geom_name=nm, node_name=nm, transform=M if M is not None else np.eye(4))

def build(out):
    scene = trimesh.Scene()
    add_builder(scene, build_room(), 'room')
    scene.add_geometry(walls_textured(), geom_name='room_walls_textured', node_name='room_walls_textured')
    scene.add_geometry(ceiling_textured(), geom_name='room_ceiling_textured', node_name='room_ceiling_textured')
    add_builder(scene, build_bench(), 'bench')
    add_builder(scene, build_labtable(), 'labtable')
    add_builder(scene, build_apparatus(), 'apparatus')
    for fn, nm in ((build_wardrobe, 'wardrobe'), (build_orange_cabinet, 'orange_cabinet'), (build_red_cabinet, 'red_cabinet'),
                   (build_shelf, 'shelf'), (build_chair, 'chair')):
        b, M = fn(); add_builder(scene, b, nm, M)
    add_builder(scene, build_sidetable(), 'sidetable')
    add_builder(scene, build_lamp(), 'lamp')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    scene.export(out)
    ntri = sum(len(scene.geometry[g].faces) for g in [scene.graph[n][1] for n in scene.graph.nodes_geometry])
    print('wrote', out, '%.2f MB' % (os.path.getsize(out) / 1e6), 'triangles', ntri)

if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'out', 'toon.glb'))
