"""Build McZee, 3D Movie Maker's host, as a 3DMM actor.

    python build_mczee.py <out folder> [--preview]

Starts from Gustave (tools/actors/import_actor.py): McZee borrows his
skeleton and all 33 of his actions, so he can do everything a stock actor
does. Each body part gets McZee's own model, built here from simple shapes
at Gustave's joints; the poses Gustave swaps models for (bent knees, pointed
toes, shrugs) are carried over onto McZee's models.

Colors come from one small swatch texture: each face picks a swatch, so a
part can have several colors with 3DMM's one material per part. Outfits are
the same layout with other colors (and other hats).

Writes mczee.blend (open it in Blender to keep working on him) and the
add-on, mczee.3cn + mczee.3th.
"""
import sys, os, json, math
import numpy as np
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, '..', '..', 'tools', 'actors')
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, '..', 'sets', 'lib'))
import import_actor  # noqa: E402
from import_actor import hide_driver  # noqa: E402
from bkgd import base_palette  # noqa: E402

PAL = base_palette().astype(float)

# ---- colors ------------------------------------------------------------------
# Each swatch is snapped to the nearest color in 3DMM's palette, so what you
# see in Blender is what 3DMM draws.
SWATCHES = {
    'skin': (132, 112, 236), 'skin_dark': (92, 72, 180), 'eye': (246, 246, 246), 'pupil': (16, 16, 16),
    'mouth': (96, 16, 32), 'lip': (228, 72, 112), 'teeth': (246, 238, 200), 'hair': (112, 72, 40),
    'red': (206, 30, 36), 'red_dark': (150, 20, 28), 'gold': (238, 186, 40), 'glove': (250, 250, 250),
    'sole': (236, 236, 236), 'shoe': (214, 36, 52), 'stem': (40, 150, 50), 'black': (30, 30, 30),
}
OUTFITS = {   # swatch overrides per outfit; same layout
    'Bellhop': {},
}
NAMES = list(SWATCHES)
GRID = 4; CELL = 16


def snap(rgb):
    return PAL[((PAL - np.array(rgb, float)) ** 2).sum(1).argmin()]


def atlas(overrides):
    img = np.zeros((GRID * CELL, GRID * CELL, 3), np.uint8)
    for k, name in enumerate(NAMES):
        r, c = divmod(k, GRID)
        img[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = snap(overrides.get(name, SWATCHES[name]))
    return img


def swatch_uv(name):
    r, c = divmod(NAMES.index(name), GRID)
    return ((c + 0.5) / GRID, 1 - (r + 0.5) / GRID)


def atlas_material(name, img):
    mat = bpy.data.materials.new(name); mat.use_fake_user = True
    mat.use_nodes = True; nt = mat.node_tree; bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.8
    h, w = img.shape[:2]
    bimg = bpy.data.images.new(name, w, h, alpha=False)
    px = np.ones((h, w, 4), np.float32); px[..., :3] = img[::-1] / 255.0
    bimg.pixels.foreach_set(px.ravel()); bimg.pack()
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = bimg; tex.interpolation = 'Closest'
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    mat['palette_base'] = 39; mat['palette_range'] = 7
    return mat


# ---- shapes --------------------------------------------------------------------
# Everything is built in Blender's world space (meters, Z up, McZee facing -X)
# at Gustave's standing pose, then moved into each body part's own space.

class Shape:
    def __init__(s):
        s.V = []; s.F = []; s.sw = []; s.smooth = []

    def add(s, V, F, color, smooth=True):
        """color: a swatch name, or a function (face center, face normal) -> swatch name"""
        o = len(s.V); s.V += [np.asarray(v, float) for v in V]
        for f in F:
            f = [i + o for i in f]
            p = [s.V[i] for i in f]
            n = np.cross(p[1] - p[0], p[2] - p[0]); n /= (np.linalg.norm(n) + 1e-12)
            c = np.mean(p, 0)
            s.F.append(f); s.sw.append(color(c, n) if callable(color) else color); s.smooth.append(smooth)
        return s

    def tris(s):
        return sum(len(f) - 2 for f in s.F)

    def scale_about(s, o, k):
        o = np.asarray(o, float); s.V = [o + (v - o) * k for v in s.V]
        return s


def frames_along(path):
    """a parallel-transported frame (tangent, a, b) at each point of a path"""
    path = [np.asarray(p, float) for p in path]
    T = []
    for i in range(len(path)):
        d = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
        T.append(d / np.linalg.norm(d))
    up = np.array([0, 0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0, 0])
    a = np.cross(up, T[0]); a /= np.linalg.norm(a)
    out = []
    for t in T:
        a = a - t * np.dot(a, t); a /= np.linalg.norm(a)
        out.append((t, a, np.cross(t, a)))
    return path, out


def loft(rings, cap0=True, cap1=True):
    """rings of equal size, joined side to side; ends closed with a center point"""
    n = len(rings[0]); V = [p for r in rings for p in r]; F = []
    for k in range(len(rings) - 1):
        for j in range(n):
            a, b = k * n + j, k * n + (j + 1) % n
            F.append([a, b, b + n, a + n])
    if cap0:
        c = len(V); V.append(np.mean(rings[0], 0))
        F += [[c, (j + 1) % n, j] for j in range(n)]
    if cap1:
        c = len(V); V.append(np.mean(rings[-1], 0)); o = (len(rings) - 1) * n
        F += [[c, o + j, o + (j + 1) % n] for j in range(n)]
    return V, F


def tube(path, radii, seg=8, round_ends=(True, True), squash=1.0):
    """a tapered tube along path; radii per point (or (ra, rb) pairs); rounded ends"""
    path, fr = frames_along(path)
    radii = [r if isinstance(r, (tuple, list)) else (r, r * squash) for r in radii]
    rings = []
    def ring(p, f, ra, rb):
        t, a, b = f
        return [p + a * ra * math.cos(2 * math.pi * j / seg) + b * rb * math.sin(2 * math.pi * j / seg) for j in range(seg)]
    if round_ends[0]:
        t, a, b = fr[0]; ra, rb = radii[0]
        for ang in (55,):
            k = math.cos(math.radians(ang)); rings.append(ring(path[0] - t * min(ra, rb) * math.sin(math.radians(ang)) * 0.9, fr[0], ra * k, rb * k))
    for p, f, (ra, rb) in zip(path, fr, radii):
        rings.append(ring(p, f, ra, rb))
    if round_ends[1]:
        t, a, b = fr[-1]; ra, rb = radii[-1]
        for ang in (55,):
            k = math.cos(math.radians(ang)); rings.append(ring(path[-1] + t * min(ra, rb) * math.sin(math.radians(ang)) * 0.9, fr[-1], ra * k, rb * k))
    return loft(rings)


def ellipsoid(c, r, seg=10, rings=6, rot=None):
    c = np.asarray(c, float); R = np.eye(3) if rot is None else np.asarray(rot)
    V = [c + R @ (np.array([0, 0, -1.0]) * r)]
    for i in range(1, rings):
        th = math.pi * i / rings
        for j in range(seg):
            ph = 2 * math.pi * j / seg
            V.append(c + R @ (np.array([math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), -math.cos(th)]) * r))
    V.append(c + R @ (np.array([0, 0, 1.0]) * r))
    F = [[0, 1 + (j + 1) % seg, 1 + j] for j in range(seg)]
    for i in range(rings - 2):
        o = 1 + i * seg
        F += [[o + j, o + (j + 1) % seg, o + seg + (j + 1) % seg, o + seg + j] for j in range(seg)]
    top = len(V) - 1; o = 1 + (rings - 2) * seg
    F += [[top, o + j, o + (j + 1) % seg] for j in range(seg)]
    return V, F


def rot_y(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# ---- McZee ---------------------------------------------------------------------
# Gustave's body parts: 0 neck, 1 head, 2 nose, 5 hair, 6/8 ears, 10 glasses,
# 11/12 torso front/back, 13/16 forearms, 14/17 hands, 15/18 upper arms,
# 19 collar, 20 hips, 21/23 shins, 22/24 thighs, 25/26 shoes. Side +1 is +Y.

HEAD_PIVOT = (-0.03, 0, 1.53)
HEAD_SCALE = 1.25


def body():
    P = {}
    def part(i): return P.setdefault(i, Shape())

    # neck: long and thin
    part(0).add(*tube([(-0.005, 0, 1.22), (-0.012, 0, 1.38), (-0.03, 0, 1.54)], [0.024, 0.023, 0.03], seg=8), 'skin')

    # head: a round skull, a muzzle with the big grin, googly eyes on top
    part(1).add(*ellipsoid((0.015, 0, 1.665), (0.112, 0.108, 0.118), seg=10, rings=6), 'skin')
    part(1).add(*ellipsoid((-0.06, 0, 1.548), (0.092, 0.098, 0.074), seg=8, rings=5), 'skin')
    part(1).add(*ellipsoid((-0.128, 0, 1.52), (0.034, 0.084, 0.034), seg=8, rings=4), 'mouth')
    part(1).add(*ellipsoid((-0.122, 0, 1.484), (0.044, 0.088, 0.024), seg=8, rings=3), 'lip')
    for y in (-0.05, -0.019, 0.019, 0.05):            # gappy teeth
        part(1).add(*ellipsoid((-0.153, y, 1.536), (0.009, 0.015, 0.02), seg=4, rings=2), 'teeth')
    for side in (-1, 1):
        c = np.array([-0.03, 0.056 * side, 1.8])
        look = np.array([-0.95, -0.12 * side, 0.12]); look /= np.linalg.norm(look)
        def eye_color(fc, n, c=c, look=look):
            if np.dot(n, look) > 0.9: return 'pupil'
            if n[2] > 0.45: return 'skin'                # heavy upper lids
            return 'eye'
        part(1).add(*ellipsoid(c, (0.056, 0.05, 0.064), seg=10, rings=7), eye_color)

    # snout: long, out in front, drooping at the end into a bulb
    part(2).add(*tube([(-0.07, 0, 1.64), (-0.16, 0, 1.646), (-0.24, 0, 1.625), (-0.29, 0, 1.585), (-0.31, 0, 1.53)],
                      [(0.05, 0.046), (0.045, 0.043), (0.042, 0.04), (0.045, 0.043), (0.055, 0.052)], seg=9), 'skin')

    # ears
    for i, side in ((6, 1), (8, -1)):
        part(i).add(*ellipsoid((0.02, 0.118 * side, 1.635), (0.028, 0.014, 0.042), seg=8, rings=5), 'skin')

    for i in (1, 2, 6, 8):                              # McZee's head is a fifth of him
        part(i).scale_about(HEAD_PIVOT, HEAD_SCALE)

    # bellhop jacket: front and back halves, gold buttons and hem
    def torso_ring(z, ry, rx, front):
        angs = np.linspace(math.pi / 2, 3 * math.pi / 2, 9) if front else np.linspace(-math.pi / 2, math.pi / 2, 9)
        return [np.array([rx * math.cos(a), ry * math.sin(a), z]) for a in angs]
    prof = [(0.79, 0.14, 0.095), (0.825, 0.139, 0.096), (0.9, 0.138, 0.098), (1.04, 0.15, 0.102), (1.16, 0.165, 0.098), (1.24, 0.155, 0.085), (1.29, 0.09, 0.06)]
    hem = lambda fc, n: 'gold' if fc[2] < 0.82 else 'red'
    for i, front in ((11, True), (12, False)):
        part(i).add(*loft([torso_ring(z, ry, rx, front) for z, ry, rx in prof]), hem)
    for z in (0.95, 1.1):
        for y in (-0.042, 0.042):
            part(11).add(*ellipsoid((-0.099, y, z), (0.008, 0.013, 0.013), seg=4, rings=2), 'gold')

    # collar: a tall stand-up collar, gold rim
    part(19).add(*tube([(-0.005, 0, 1.2), (-0.005, 0, 1.25), (-0.008, 0, 1.31)], [0.075, 0.068, 0.058], seg=10, round_ends=(False, False)),
                 lambda fc, n: 'gold' if fc[2] > 1.29 or n[2] > 0.7 else 'red')

    # arms: red sleeves, gold epaulettes and cuffs, white four-fingered gloves
    for side, up, fore, hand in ((1, 15, 13, 14), (-1, 18, 16, 17)):
        y = lambda v: v * side
        part(up).add(*tube([(0.005, y(0.165), 1.215), (0.02, y(0.2), 1.09), (0.04, y(0.228), 0.965)], [0.044, 0.041, 0.039], seg=7), 'red')
        part(up).add(*ellipsoid((0.005, y(0.175), 1.24), (0.055, 0.05, 0.018), seg=6, rings=3), 'gold')
        wrist = np.array([-0.035, y(0.224), 0.745])
        part(fore).add(*tube([(0.045, y(0.232), 0.975), (0.01, y(0.23), 0.86), tuple(wrist)], [0.039, 0.036, 0.034], seg=7),
                       lambda fc, n, w=wrist: 'gold' if np.linalg.norm(fc - w) < 0.045 else 'red')
        # glove: cuff, palm, three fingers and a thumb, curled a little
        part(hand).add(*tube([(-0.037, y(0.223), 0.735), (-0.045, y(0.222), 0.69)], [0.042, 0.036], seg=6, round_ends=(False, True)), 'glove')
        part(hand).add(*ellipsoid((-0.06, y(0.222), 0.64), (0.046, 0.024, 0.056), seg=6, rings=4), 'glove')
        for k, x0 in enumerate((-0.088, -0.064, -0.04)):
            part(hand).add(*tube([(x0, y(0.222), 0.6), (x0 - 0.026, y(0.221), 0.525)], [0.0145, 0.0125], seg=4), 'glove')
        part(hand).add(*tube([(-0.09, y(0.208), 0.66), (-0.128, y(0.198), 0.605)], [0.015, 0.0125], seg=4), 'glove')

    # hips and legs: red trousers with a gold stripe down the outside
    hips = [(0.66, 0.13, 0.09), (0.74, 0.138, 0.094), (0.8, 0.128, 0.086)]   # tucked inside the jacket
    part(20).add(*loft([[np.array([rx * math.cos(a), ry * math.sin(a), z]) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)] for z, ry, rx in hips]), 'red')
    for side, thigh, shin in ((-1, 22, 21), (1, 24, 23)):
        out = np.array([0, side, 0.0])
        stripe = lambda fc, n, out=out: 'gold' if np.dot(n, out) > 0.8 else 'red'
        part(thigh).add(*tube([(0.01, 0.088 * side, 0.79), (0.008, 0.08 * side, 0.6), (0.004, 0.072 * side, 0.43)], [0.058, 0.054, 0.046], seg=7), stripe)
        part(shin).add(*tube([(0.004, 0.07 * side, 0.45), (0.002, 0.066 * side, 0.27), (0.0, 0.062 * side, 0.1)], [0.046, 0.042, 0.036], seg=7), stripe)

    # sneakers: big and red, white toe caps, soles and laces
    for i, side in ((25, -1), (26, 1)):
        ankle = np.array([0.02, 0.066 * side, 0.0])
        d = np.array([-1.0, 0.28 * side, 0]); d /= np.linalg.norm(d)
        lat = np.cross([0, 0, 1.0], d)
        rings = []
        for t, w, h in ((-0.08, 0.045, 0.08), (-0.045, 0.06, 0.115), (0.02, 0.068, 0.105), (0.11, 0.074, 0.085), (0.2, 0.076, 0.076), (0.27, 0.066, 0.066), (0.31, 0.036, 0.048)):
            c = ankle + d * t
            rings.append([c + lat * w * math.cos(a) + np.array([0, 0, h * math.sin(a)]) for a in np.linspace(0, math.pi, 7)] +
                         [c])
        def shoe_color(fc, n, ankle=ankle, d=d):
            t = np.dot(fc - ankle, d)
            if n[2] < -0.5 or fc[2] < 0.018: return 'sole'
            if t > 0.19: return 'sole'                  # toe cap
            if 0.0 < t < 0.15 and n[2] > 0.75: return 'eye'   # laces
            return 'shoe'
        part(i).add(*loft(rings), shoe_color)
    return P


def hats():
    """accessories: the bellhop's fez (on the glasses slot) and McZee's own tuft of hair"""
    fez = Shape()
    base, top = np.array([0.045, 0, 1.765]), np.array([0.075, 0, 1.9])
    fez.add(*tube([tuple(base), tuple(base + (top - base) * 0.25), tuple(top)], [0.074, 0.07, 0.062], seg=10, round_ends=(False, False)),
            lambda fc, n: 'gold' if fc[2] < 1.79 else 'red')
    fez.add(*tube([tuple(top), tuple(top + [0.004, 0, 0.04])], [0.006, 0.005], seg=5), 'stem')
    fez.add(*ellipsoid(top + [0.006, 0, 0.05], (0.018, 0.018, 0.014), seg=6, rings=3), 'red')
    tuft = Shape()
    tuft.add(*tube([(0.04, 0, 1.76), (0.065, 0, 1.85), (0.045, 0, 1.92), (0.005, 0, 1.94), (-0.02, 0, 1.92)],
                   [0.03, 0.024, 0.017, 0.01, 0.005], seg=7, round_ends=(False, True)), 'hair')
    fez.scale_about(HEAD_PIVOT, HEAD_SCALE); tuft.scale_about(HEAD_PIVOT, HEAD_SCALE)
    return {'fez': (10, fez), 'tuft': (5, tuft)}


# ---- putting him on Gustave's skeleton -----------------------------------------

def to_mesh(name, shape, M_inv):
    """a Blender mesh in a bone's space: M_inv takes world points there"""
    me = bpy.data.meshes.new(name)
    V = [tuple((M_inv @ np.r_[v, 1.0])[:3]) for v in shape.V]
    me.from_pydata(V, [], shape.F)
    uvl = me.uv_layers.new(name='UVMap')
    for poly, sw, sm in zip(me.polygons, shape.sw, shape.smooth):
        u, v = swatch_uv(sw); poly.use_smooth = sm
        for li in poly.loop_indices: uvl.data[li].uv = (u, v)
    me.materials.append(None)
    me['swatches'] = json.dumps(shape.sw)
    return me


def transfer(base_local, g_main, g_var, k=4):
    """move McZee's vertices the way Gustave's main model moves into a variant:
    each vertex follows the nearest few of Gustave's vertices"""
    disp = g_var - g_main
    d = np.linalg.norm(base_local[:, None, :] - g_main[None, :, :], axis=2)
    idx = np.argsort(d, 1)[:, :k]
    w = 1 / (np.take_along_axis(d, idx, 1) + 1e-4); w /= w.sum(1, keepdims=True)
    return base_local + (disp[idx] * w[..., None]).sum(1)


def build(out_dir, preview=False):
    gblend = os.path.join(out_dir, 'gustave-base.blend')
    arm = import_actor.import_actor('Gustave', gblend)
    scene = bpy.context.scene
    arm.name = arm.data.name = 'McZee'
    arm['3dmm_actor'] = 'McZee'
    for k in [k for k in arm.keys() if k.startswith('costume')]: del arm[k]
    arm.animation_data.action = bpy.data.actions['At Rest']; scene.frame_set(0)
    bpy.context.view_layer.update()

    pb = {b['part']: b for b in arm.pose.bones if 'part' in b}
    holder = {i: (arm.pose.bones[b.name + '.twist'] if b.name + '.twist' in arm.pose.bones else b) for i, b in pb.items()}
    Aw = np.array(arm.matrix_world)
    world = {i: Aw @ np.array(h.matrix) for i, h in holder.items()}

    # Gustave's models per part (in the bone's space), and how often each shows
    gus = {}
    for o in list(bpy.data.objects):
        if o.type == 'MESH' and o.parent is arm and o.get('model', -1) >= 0:
            i = arm.pose.bones[o.parent_bone.replace('.twist', '')]['part']
            gus.setdefault(i, {})[int(o['model'])] = np.array([v.co for v in o.data.vertices])
    usage = {i: {} for i in pb}
    for act in bpy.data.actions:
        arm.animation_data.action = act
        f0, f1 = (int(x) for x in act.frame_range)
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            for i, b in pb.items():
                m = int(b['model']); usage[i][m] = usage[i].get(m, 0) + 1
    arm.animation_data.action = bpy.data.actions['At Rest']; scene.frame_set(0)

    # out with Gustave
    for o in [o for o in bpy.data.objects if o.type == 'MESH']: bpy.data.objects.remove(o)
    for m in list(bpy.data.meshes): bpy.data.meshes.remove(m)
    for m in list(bpy.data.materials): bpy.data.materials.remove(m)
    for im in list(bpy.data.images): bpy.data.images.remove(im)

    mats = {name: atlas_material('McZee ' + name, atlas(ov)) for name, ov in OUTFITS.items()}
    mat = mats['Bellhop']

    def place(obj, i):
        obj.parent = arm; obj.parent_type = 'BONE'; obj.parent_bone = holder[i].name
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = Matrix.Translation((0, -arm.data.bones[holder[i].name].length, 0))
        obj.material_slots[0].link = 'OBJECT'; obj.material_slots[0].material = mat

    P = body(); total = 0
    for i, shape in sorted(P.items()):
        Minv = np.linalg.inv(world[i]); total += shape.tris()
        chids = sorted(usage[i], key=lambda m: -usage[i][m]); chids = [m for m in chids if m >= 0]
        main = chids[0]
        base = to_mesh('McZee.%s.m%d' % (pb[i].name, main), shape, Minv)
        base_V = np.array([v.co for v in base.vertices])
        for ch in chids:
            if ch == main: me = base
            else:
                me = base.copy(); me.name = 'McZee.%s.m%d' % (pb[i].name, ch)
                gm, gv = gus.get(i, {}).get(main), gus.get(i, {}).get(ch)
                if gm is not None and gv is not None and gm.shape == gv.shape and np.abs(gv - gm).max() < 0.15:
                    me.vertices.foreach_set('co', transfer(base_V, gm, gv).ravel())
                    me.update()
            obj = bpy.data.objects.new(me.name, me); scene.collection.objects.link(obj)
            obj['model'] = ch; place(obj, i)
            hide_driver(obj, arm, pb[i].name, 'm != %d' % ch)

    # body part sets: hands go with the outfit, hair goes with the hat
    sets = {0: 'Head', 1: 'Hat', 2: 'Top', 3: 'Bottom', 4: 'Feet'}
    setof = {i: int(b['set']) for i, b in pb.items()}
    setof[14] = setof[17] = 2; setof[5] = 1
    for i, b in pb.items(): b['set'] = setof[i]
    # the hair and glasses slots show accessories (model -1) all the time
    for act in bpy.data.actions:
        for fc in _fcurves(act):
            if fc.data_path in ('pose.bones["%s"]["model"]' % pb[5].name, 'pose.bones["%s"]["model"]' % pb[10].name):
                for kp in fc.keyframe_points: kp.co[1] = -1
    pb[5]['model'] = -1

    acc = {}
    for name, (i, shape) in hats().items():
        me = to_mesh('McZee.%s' % name, shape, np.linalg.inv(world[i])); total += shape.tris()
        obj = bpy.data.objects.new(me.name, me); scene.collection.objects.link(obj)
        obj['model'] = -1; obj['costume_set'] = 1; place(obj, i); acc[name] = obj
    hats_opts = [('Bellhop fez', {5: '-', 10: 'fez'}), ('Hair', {5: 'tuft', 10: '-'})]
    for o, (nm, which) in enumerate(hats_opts):
        for i, a in which.items():
            if a != '-':
                acc[a]['costume_option'] = o
                hide_driver(acc[a], arm, pb[i].name, '(m != -1) + (c != %d)' % o, extra='["costume_1"]')

    costumes = []
    for s_, label in sets.items():
        parts = sorted(i for i in pb if setof[i] == s_)
        if s_ == 1:
            opts = [dict(name=nm, materials=[mat.name] * len(parts),
                         accessories=[(acc[which[i]].name if which.get(i, '-') != '-' else '-') for i in parts]) for nm, which in hats_opts]
        else:
            opts = [dict(name=o, materials=[m.name] * len(parts), accessories=[''] * len(parts)) for o, m in mats.items()]
        costumes.append(dict(set=s_, label=label, parts=[pb[i].name for i in parts], options=opts))
        arm['costume_%d' % s_] = 0
    arm['costumes'] = json.dumps(costumes)

    scene.frame_set(0)
    path = os.path.join(out_dir, 'mczee.blend')
    os.remove(gblend)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(path), compress=True)
    print('McZee: %d triangles (Gustave: 995)' % total)
    if preview:
        import_actor.render_preview(arm, os.path.join(out_dir, 'mczee-preview.png'))
    return arm


def _fcurves(act):
    """an action's F-curves (Blender 4.4+ keeps them in layers, strips and channelbags)"""
    if hasattr(act, 'fcurves') and len(act.fcurves): return list(act.fcurves)
    out = []
    for layer in getattr(act, 'layers', []):
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', []): out += list(bag.fcurves)
    return out


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    out = args[0]; os.makedirs(out, exist_ok=True)
    arm = build(out, '--preview' in args)
    if '--export' in args:
        import export_actor
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(os.path.join(out, 'mczee.blend')))
        e = export_actor.Export(bpy.data.objects['McZee'])
        print('wrote', e.run(out))
