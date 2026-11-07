"""Blender (.blend) -> a 3D Movie Maker add-on actor (.3cn content + .3th browser entry).

    python export_actor.py <in.blend> <out folder> [--armature NAME] [--cno 0x...]

Reads the conventions in README.md (the same ones import_actor.py writes):
an armature whose bones are body parts, rigid meshes parented to bones,
one Blender action per 3DMM action at 6 fps, materials as costumes. Writes
<name>.3cn and <name>.3th; put both in 3DMM's content folder
("3D Movie Maker" next to 3dmovie.exe) and the actor shows up in the browser.

Chunk numbers: every content file in that folder shares one pool, so each
actor takes its own block of 4096 numbers, picked from its name unless you
pass --cno. Keep it the same between versions of an actor: saved movies
point at it.
"""
import sys, os, json, struct, zlib, math
import numpy as np
import bpy
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'sets', 'lib'))
import chunky  # noqa: E402
from bkgd import base_palette  # noqa: E402

SCALE = 0.1
C = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
CI = np.linalg.inv(C)
S = np.diag([SCALE, SCALE, SCALE, 1.0]); SI = np.linalg.inv(S)
PAL = base_palette().astype(float)
RAMPS = [(15 + 8 * k, 7) for k in range(17)]          # the solid color ramps stock actors use
FSTATIC = 8


def to_brender(M_col):
    """inverse of import_actor.to_blender: Blender column matrix (meters) -> BRender row matrix"""
    return (CI @ SI @ np.asarray(M_col) @ S @ C).T


def default_cno(name):
    return 0x40000000 + (zlib.crc32(name.encode('utf-8')) & 0x3FFF) * 0x1000


def quantize(rgb):
    """nearest base palette entry for each pixel"""
    flat = rgb.reshape(-1, 3).astype(float)
    out = np.empty(len(flat), np.uint8)
    for i in range(0, len(flat), 65536):
        d = ((flat[i:i + 65536, None, :] - PAL[None]) ** 2).sum(-1)
        out[i:i + 65536] = d.argmin(1)
    return out.reshape(rgb.shape[:2])


def material_image(mat):
    if not mat or not mat.use_nodes: return None
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image: return n.image
    return None


def base_color(mat):
    if mat and mat.use_nodes:
        b = mat.node_tree.nodes.get('Principled BSDF')
        if b: return np.array(b.inputs['Base Color'].default_value[:3])
    if mat: return np.array(mat.diffuse_color[:3])
    return np.array([0.6, 0.6, 0.6])


class Export:
    def __init__(s, arm, cno=None):
        s.arm = arm; s.name = arm.get('3dmm_actor', arm.name)
        s.cno = cno if cno is not None else default_cno(s.name); s.next = s.cno
        s.w = chunky.Chunky(); s.th = chunky.Chunky()
        s.tmaps = {}; s.models = {}

    def new(s, tag, data, name='', loner=False, w=None):
        key = (w or s.w).add(tag, s.next, data, name, loner); s.next += 1
        assert s.next < s.cno + 0x1000, 'actor too big for its chunk number block'
        return key

    # ---- structure ------------------------------------------------------
    def parts(s):
        bones = [b for b in s.arm.data.bones if not b.name.endswith('.twist')]
        pbs = s.arm.pose.bones
        if all('part' in pbs[b.name] for b in bones):
            bones.sort(key=lambda b: pbs[b.name]['part'])
        else:                                       # parents before children
            order = []
            def visit(b):
                order.append(b); [visit(c) for c in b.children if not c.name.endswith('.twist')]
                for c in b.children:
                    if c.name.endswith('.twist'): [visit(g) for g in c.children]
            [visit(b) for b in bones if b.parent is None]
            bones = order
        s.bone = [b.name for b in bones]
        idx = {n: i for i, n in enumerate(s.bone)}
        def main(b): return b.parent.name if b.name.endswith('.twist') else b.name
        s.parent = []
        for b in bones:
            p = b.parent
            if p is not None and p.name.endswith('.twist'): p = p.parent
            s.parent.append(idx[p.name] if p is not None else -1)
            assert s.parent[-1] < len(s.parent) - 1, 'body part %s comes before its parent' % b.name
        names = {b.name for b in s.arm.data.bones}
        s.holder = [n + '.twist' if n + '.twist' in names else n for n in s.bone]
        s.bset = [int(pbs[n].get('set', 0)) for n in s.bone]
        s.nsets = max(s.bset) + 1
        s.objs = [[] for _ in s.bone]; s.acc = []
        for o in bpy.data.objects:
            if o.type != 'MESH' or o.parent is not s.arm or o.parent_type != 'BONE': continue
            b = o.parent_bone[:-6] if o.parent_bone.endswith('.twist') else o.parent_bone
            if b not in idx: continue
            if o.get('model', 0) == -1: s.acc.append((idx[b], o))
            else: s.objs[idx[b]].append(o)

    def world(s):
        """posed holder matrices relative to the armature, at the current frame"""
        A = np.linalg.inv(np.array(s.arm.matrix_world))
        return [A @ np.array(s.arm.pose.bones[h].matrix) for h in s.holder]

    # ---- models -----------------------------------------------------------
    def model_of(s, o, i, W):
        """3DMM model data for mesh object o on part i (W: posed holder matrices)"""
        deps = bpy.context.evaluated_depsgraph_get()
        oe = o.evaluated_get(deps); me = oe.to_mesh()
        rel = np.linalg.inv(W[i]) @ np.linalg.inv(np.array(s.arm.matrix_world)) @ np.array(oe.matrix_world)
        to3 = CI @ SI @ rel                          # Blender local -> 3DMM model space
        uvl = me.uv_layers.active
        sg = me.attributes.get('smoothing_group')
        me.calc_loop_triangles()
        verts = {}; V = []; UV = []; F = []; SM = []
        for tri in me.loop_triangles:
            poly = me.polygons[tri.polygon_index]
            if sg is not None: grp = sg.data[tri.polygon_index].value
            else: grp = 1 if poly.use_smooth else 0
            f = []
            for li, vi in zip(tri.loops, tri.vertices):
                uv = tuple(uvl.data[li].uv) if uvl else (0.0, 0.0)
                # sharp edges: give each side its own vertex so BRender doesn't smooth across
                side = 0
                if sg is None and poly.use_smooth:
                    side = s._side(me, tri.polygon_index, vi)
                key = (vi, round(uv[0], 6), round(uv[1], 6), side)
                if key not in verts:
                    verts[key] = len(V)
                    p = to3 @ np.array([*me.vertices[vi].co, 1.0])
                    V.append(p[:3]); UV.append((uv[0], 1 - uv[1]))
                f.append(verts[key])
            F.append(f); SM.append(grp)
        oe.to_mesh_clear()
        return np.array(V), np.array(UV), np.array(F), np.array(SM)

    def _side(s, me, pi, vi):
        """which smooth fan around vertex vi (split by sharp edges) face pi is in"""
        key = id(me)
        if getattr(s, '_fans_key', None) != key:
            s._fans_key = key; s._fans = {}
            sharp = me.attributes.get('sharp_edge')
            sharp = {i for i, d in enumerate(sharp.data) if d.value} if sharp else set()
            ek = {tuple(sorted(e.vertices)): e.index for e in me.edges}
            by_v = {}
            for p in me.polygons:
                for v in p.vertices: by_v.setdefault(v, []).append(p.index)
            for v, faces in by_v.items():
                comp = {f: f for f in faces}
                def find(x):
                    while comp[x] != x: x = comp[x]
                    return x
                for a in faces:
                    ea = {tuple(sorted(e)) for e in me.polygons[a].edge_keys if v in e}
                    for b in faces:
                        if b <= a: continue
                        eb = {tuple(sorted(e)) for e in me.polygons[b].edge_keys if v in e}
                        shared = ea & eb
                        if shared and not any(ek[e] in sharp for e in shared):
                            comp[find(a)] = find(b)
                for f in faces: s._fans[(f, v)] = find(f)
        return s._fans[(pi, vi)]

    def bmdl(s, o, i, W):
        V, UV, F, SM = s.model_of(o, i, W)
        return chunky.bmdl(V, UV, F, SM)

    # ---- materials ----------------------------------------------------------
    def mtrl(s, mat):
        img = material_image(mat)
        if img is not None:
            base, rng = int(mat.get('palette_base', 55)), int(mat.get('palette_range', 7))
            key = s.new('MTRL', chunky.mtrl(base, rng, True))
            if img.name not in s.tmaps:
                w, h = img.size
                px = np.array(img.pixels[:], np.float32).reshape(h, w, -1)[::-1, :, :3]
                rgb = np.clip(np.round(s._srgb(img, px) * 255), 0, 255)
                if max(w, h) > 256:                 # 3DMM's own textures stay at 256 or under
                    from PIL import Image
                    k = 256 / max(w, h)
                    rgb = np.array(Image.fromarray(rgb.astype(np.uint8)).resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS), float)
                s.tmaps[img.name] = s.new('TMAP', chunky.tmap(quantize(rgb)))
            s.w.adopt(key, s.tmaps[img.name], 0)
            if 'uv_transform' in mat:
                xf = np.array(mat['uv_transform'], float).reshape(3, 2)
                s.w.adopt(key, s.new('TXXF', chunky.txxf(xf)), 0)
            return key
        if 'palette_base' in mat:
            base, rng = int(mat['palette_base']), int(mat['palette_range'])
        else:                                       # the ramp whose lit shade is closest
            want = np.clip(base_color(mat), 0, 1) ** (1 / 2.2) * 255
            base, rng = min(RAMPS, key=lambda r: ((PAL[r[0] + int(r[1] * 0.72)] - want) ** 2).sum())
        return s.new('MTRL', chunky.mtrl(base, rng, False))

    @staticmethod
    def _srgb(img, px):
        # Blender stores byte images' pixels as they are (sRGB); float images are linear
        if img.is_float: return np.where(px <= 0.0031308, px * 12.92, 1.055 * np.power(np.clip(px, 0, None), 1 / 2.4) - 0.055)
        return px

    # ---- the whole actor ------------------------------------------------------
    def run(s, out_dir):
        s.parts()
        arm = s.arm; n = len(s.bone)
        rest = [int(round(a * 65536 / 360.0)) for a in arm.get('rest_rotation', (0, 90, 0))]
        grf = int(arm.get('template_flags', 1))
        tmpl = s.w.add('TMPL', s.cno, struct.pack('<hhhhhhI', 1, chunky.OSK, *rest, 20, grf), s.name, True); s.next += 1
        s.w.adopt(tmpl, s.new('GLPI', chunky.gl([struct.pack('<h', p) for p in s.parent], 2)), 0)
        s.w.adopt(tmpl, s.new('GLBS', chunky.gl([struct.pack('<h', b) for b in s.bset], 2)), 0)

        # actions (and the models they show)
        actions = [a for a in bpy.data.actions if a.get('3dmm', 'steps' in a)]
        actions.sort(key=lambda a: a.get('anid', 1 << 20))
        if not actions: raise SystemExit('no actions: mark them with a "3dmm" property (see README.md)')
        arm.animation_data_create()
        keep = arm.animation_data.action
        model_chid = {}                             # (part, object name) -> chid
        for anid, act in enumerate(actions):
            arm.animation_data.action = act
            f0, f1 = (int(x) for x in act.frame_range)
            cels = []; xfs = []; xfi = {}
            steps = list(act.get('steps', []))
            for k, f in enumerate(range(f0, f1 + 1)):
                bpy.context.scene.frame_set(f)
                W = s.world()
                deps = bpy.context.evaluated_depsgraph_get()
                cps = []
                for i in range(n):
                    L = W[i] if s.parent[i] < 0 else np.linalg.inv(W[s.parent[i]]) @ W[i]
                    m = chunky.mat34(to_brender(L))
                    if m not in xfi: xfi[m] = len(xfs); xfs.append(m)
                    shown = [o for o in s.objs[i] if not o.evaluated_get(deps).hide_render]
                    if len(shown) > 1:
                        raise SystemExit('%s, frame %d: body part %s shows %d meshes; one at a time' % (act.name, f, s.bone[i], len(shown)))
                    if shown:
                        o = shown[0]; key = (i, o.name)
                        if key not in model_chid:
                            want = int(o['model']) if 'model' in o and o['model'] >= 0 else None
                            taken = set(model_chid.values())
                            if want is None or want in taken and s.models.get(want) != o.data.name:
                                want = max(taken | {-1}) + 1
                            model_chid[key] = want
                            if want not in s.models:
                                s.models[want] = o.data.name
                                s.w.adopt(tmpl, s.new('BMDL', s.bmdl(o, i, W)), want)
                        cps.append((model_chid[key], xfi[m]))
                    else:
                        cps.append((-1, xfi[m]))
                step = steps[k] if k < len(steps) else 0.0
                cels.append((struct.pack('<ii', -1, chunky.fixed(step / SCALE)),
                             b''.join(struct.pack('<hh', c, x) for c, x in cps)))
            flags = int(act.get('flags', 2 if any(steps) else 2 | FSTATIC))   # turn to follow paths
            ak = s.new('ACTN', struct.pack('<hhi', 1, chunky.OSK, flags), act.name)
            s.w.adopt(tmpl, ak, anid)
            s.w.adopt(ak, s.new('GGCL', chunky.gg(cels, 8)), 0)
            s.w.adopt(ak, s.new('GLXF', chunky.gl(xfs, 48)), 0)
        arm.animation_data.action = keep

        # costumes
        costumes = json.loads(arm['costumes']) if 'costumes' in arm else None
        if costumes is None:                        # one costume per set: what each part wears now
            costumes = []
            for b in range(s.nsets):
                parts = [s.bone[i] for i in range(n) if s.bset[i] == b]
                mats = [(s.objs[s.bone.index(p)][0].active_material.name
                         if s.objs[s.bone.index(p)] and s.objs[s.bone.index(p)][0].active_material else '') for p in parts]
                costumes.append(dict(set=b, parts=parts, options=[dict(name='', materials=mats, accessories=[''] * len(parts))]))
        ggcm = []; cmid = 0
        bpy.context.scene.frame_set(int(actions[0].frame_range[0]))
        arm.animation_data.action = actions[0]; bpy.context.scene.frame_set(int(actions[0].frame_range[0]))
        W = s.world()
        for cs in sorted(costumes, key=lambda c: c['set']):
            ids = []
            parts = [s.bone[i] for i in range(n) if s.bset[i] == cs['set']]
            for opt in cs['options']:
                ck = s.new('CMTL', struct.pack('<hhi', 1, chunky.OSK, cs['set']), opt.get('name', ''))
                s.w.adopt(tmpl, ck, cmid); ids.append(cmid); cmid += 1
                for k, p in enumerate(parts):
                    mname = opt['materials'][k] if k < len(opt['materials']) else ''
                    if mname: s.w.adopt(ck, s.mtrl(bpy.data.materials[mname]), k)
                    aname = opt['accessories'][k] if k < len(opt.get('accessories', [])) else ''
                    if aname == '-':                # an empty model: takes the accessory off
                        s.w.adopt(ck, s.new('BMDL', chunky.bmdl([], [], [], [])), k)
                    elif aname:
                        o = bpy.data.objects[aname]
                        s.w.adopt(ck, s.new('BMDL', s.bmdl(o, s.bone.index(p), W)), k)
            ggcm.append((struct.pack('<i', len(ids)), struct.pack('<%di' % len(ids), *ids)))
        s.w.adopt(tmpl, s.new('GGCM', chunky.gg(ggcm, 4)), 0)

        os.makedirs(out_dir, exist_ok=True)
        base = os.path.join(out_dir, s.name.lower().replace(' ', '-'))
        s.w.save(base + '.3cn')
        s.thumbnail(base + '.3th')
        return base

    def thumbnail(s, path):
        """the actor browser's 72x72 picture: thumbnail.png next to the .blend, else a quick render"""
        from PIL import Image
        src = bpy.path.abspath(s.arm.get('thumbnail', '//thumbnail.png'))
        if not os.path.exists(src):
            src = os.path.join(os.path.dirname(path), 'thumbnail.png')
            try:
                render_thumbnail(s.arm, src)
            except Exception as e:              # no way to render here: a plain card with the name
                print('thumbnail render failed (%s); using a plain one' % e)
                plain_thumbnail(s.name, src)
        im = Image.open(src).convert('RGBA').resize((72, 72), Image.LANCZOS)
        alpha = np.array(im)[..., 3] > 127
        pim = Image.new('P', (1, 1)); pim.putpalette(PAL.astype(np.uint8).ravel().tolist())
        idx = np.array(im.convert('RGB').quantize(palette=pim, dither=Image.Dither.FLOYDSTEINBERG))
        tmth = s.th.add('TMTH', s.cno, struct.pack('<hh4sI', 1, chunky.OSK, b'TMPL'[::-1], s.cno), '', True)
        gokd = s.th.add('GOKD', s.cno, bytes.fromhex(GOKD))
        s.th.add('MBMP', s.cno, chunky.mbmp(idx, alpha))
        s.th.adopt(tmth, gokd, 0); s.th.adopt(gokd, ('MBMP', s.cno), 0x10000)
        s.th.save(path)


# the stock thumbnail GOKD (a plain picture, no states)
GOKD = '01000303000000000000000000000000000000000a0000000000000000000000ffffffffffffffffffffffff61c30000ffffffff'


def plain_thumbnail(name, path):
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (72, 72), (70, 60, 110)); d = ImageDraw.Draw(im)
    d.text((36, 36), name[:10], fill=(255, 230, 120), anchor='mm')
    im.save(path)


def render_thumbnail(arm, path):
    scene = bpy.context.scene
    keep = (scene.render.resolution_x, scene.render.resolution_y, scene.camera)
    scene.render.resolution_x = scene.render.resolution_y = 144
    sys.path.insert(0, HERE)
    from import_actor import frame_camera
    cam = frame_camera(arm, head=True)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    scene.render.resolution_x, scene.render.resolution_y, scene.camera = keep


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    opts = {}
    for k in ('--armature', '--cno'):
        if k in args:
            j = args.index(k); opts[k[2:]] = args[j + 1]; del args[j:j + 2]
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args[0]))
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE' and (opts.get('armature') in (None, o.name))]
    if len(arms) != 1: raise SystemExit('which armature? %s' % [o.name for o in arms])
    e = Export(arms[0], int(opts['cno'], 0) if 'cno' in opts else None)
    print('wrote', e.run(args[1]) + '.3cn/.3th', 'chunks %#x..%#x' % (e.cno, e.next - 1))
