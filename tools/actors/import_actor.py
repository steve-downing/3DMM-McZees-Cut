"""3D Movie Maker actor -> Blender (.blend).

    python import_actor.py <actor name> <out.blend> [--preview out.png] [--glb out.glb]

Runs with Blender's Python module (pip install bpy). Reads the actor from
content-files/tmpls.3cn (see tools/sets/lib/actor.py) and builds the
conventions in README.md, which the exporter reads back:

- An armature named after the actor. Each body part is a bone ("Head.03"),
  parented the way the parts are. Parts whose cels ever shear (squash and
  stretch) get a hidden child bone "<part>.twist" carrying the extra
  rotation, so the import is exact; new actors don't need them.
- Each model a part can show is a mesh parented to its bone, with a "model"
  property (its number in the template). A bone's keyed "model" property says
  which mesh shows; drivers hide the others. -1 means the costume's
  accessory, if it has one.
- Each 3DMM action is a Blender action at 6 fps, one key per cel, constant
  interpolation. Its "steps" property holds the distance the actor moves at
  each cel when walking a path.
- Costumes: Blender materials, plus the armature's "costumes" property
  (JSON): body part sets, and for each costume option the material and
  accessory per part. Option 0 is applied.
- Units: 3DMM units / 10, Blender's Z up. Gustave is about 1.8 m tall.
"""
import sys, os, json, struct, math
import numpy as np
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'sets', 'lib'))
from actor import Template, gl, gg, mat34, model, smooth_by_groups, FX  # noqa: E402

SCALE = 0.1
# BRender (Y up) -> Blender (Z up): x -> x, y -> z, z -> -y
C = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
CI = np.linalg.inv(C)


def to_blender(M_row):
    """a BRender row-vector matrix (v' = v M) as a Blender column matrix, scaled to meters"""
    S = np.diag([SCALE, SCALE, SCALE, 1.0]); SI = np.diag([1 / SCALE] * 3 + [1.0])
    return S @ C @ M_row.T @ CI @ SI


def point(v):
    return (C[:3, :3] @ np.asarray(v)) * SCALE


def is_trs(L3, tol=1e-4):
    """column-form 3x3 that is rotate-after-scale (columns orthogonal)?"""
    G = L3.T @ L3
    off = np.abs(G - np.diag(np.diag(G))).max()
    return off <= tol * max(np.abs(G).max(), 1e-12)


def split_twist(L):
    """L (4x4 column form) = A @ B, A = translate*rotate*scale, B = pure rotation"""
    U, S, Vt = np.linalg.svd(L[:3, :3])
    if np.linalg.det(U) < 0: U[:, 2] *= -1; S[2] *= -1
    if np.linalg.det(Vt) < 0: Vt[2, :] *= -1; S[2] *= -1
    A = np.eye(4); A[:3, :3] = U @ np.diag(S); A[:3, 3] = L[:3, 3]
    B = np.eye(4); B[:3, :3] = Vt
    return A, B


def rigid(M):
    """nearest rotation + translation"""
    U, _, Vt = np.linalg.svd(M[:3, :3])
    R = U @ Vt
    if np.linalg.det(R) < 0: U[:, 2] *= -1; R = U @ Vt
    out = np.eye(4); out[:3, :3] = R; out[:3, 3] = M[:3, 3]
    return out


def M(a):
    return Matrix([list(r) for r in a])


def set_labels(t):
    """Head / Top / Bottom / Feet by where each body part set sits in the rest pose"""
    rest, _ = t.cel(min(t.actions), 0)
    world = {}
    def W(i):
        if i not in world: world[i] = rest[i][1] @ W(t.parent[i]) if t.parent[i] >= 0 else rest[i][1]
        return world[i]
    ys = [W(i)[3, 1] for i in range(len(t.parent))]; top = max(ys) or 1
    labels, seen = [], {}
    for ibset in range(len(t.costumes)):
        parts = [i for i, b in enumerate(t.bset) if b == ibset]
        h = np.mean([ys[p] for p in parts]) / top if parts else 0
        lab = 'Head' if h > 0.8 else 'Top' if h > 0.5 else 'Bottom' if h > 0.2 else 'Feet'
        seen[lab] = seen.get(lab, 0) + 1
        labels.append(lab if seen[lab] == 1 else '%s%d' % (lab, seen[lab]))
    return labels


def make_mesh(name, V, UV, F, sm):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(point(v)) for v in V], [], [tuple(int(i) for i in f) for f in F])
    me.validate(clean_customdata=False)
    uvl = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li, vi in zip(poly.loop_indices, poly.vertices):
            u, v = UV[vi]
            uvl.data[li].uv = (u, 1 - v)        # stored the usual Blender way; materials map back
    att = me.attributes.new('smoothing_group', 'INT', 'FACE')
    att.data.foreach_set('value', [int(s) for s in sm])
    for p in me.polygons: p.use_smooth = True
    N = smooth_by_groups(V, F, sm)               # BRender's smoothing, per corner
    normals = []
    for fi, poly in enumerate(me.polygons):
        f = [int(x) for x in F[fi]]
        for vi in poly.vertices:
            normals.append(tuple(C[:3, :3] @ N[fi, f.index(vi)]))
    me.normals_split_custom_set(normals)
    me.materials.append(None)                    # one slot; each object links its costume's material
    return me


def make_material(name, m):
    mat = bpy.data.materials.new(name)
    mat.use_fake_user = True                     # costumes nobody wears yet still get saved
    mat.use_nodes = True
    nt = mat.node_tree; bsdf = nt.nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = 0.85
    mat['palette_base'] = int(m['base']); mat['palette_range'] = int(m['range'])
    if 'image' in m:
        img = m['image']; h, w = img.shape[:2]
        bimg = bpy.data.images.new(name, w, h, alpha=False)
        px = np.ones((h, w, 4), np.float32); px[..., :3] = img[::-1] / 255.0
        bimg.pixels.foreach_set(px.ravel())
        bimg.pack()
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = bimg; tex.interpolation = 'Closest'
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        if 'uvxf' in m and not np.allclose(m['uvxf'], [[1, 0], [0, 1], [0, 0]]):
            # 3DMM: [u v 1] @ uvxf, v down from the top. The mesh holds (u, 1 - v).
            a, b = m['uvxf'][0]; c, d = m['uvxf'][1]; e, f = m['uvxf'][2]
            mat['uv_transform'] = [float(x) for x in m['uvxf'].ravel()]
            uvn = nt.nodes.new('ShaderNodeUVMap'); sep = nt.nodes.new('ShaderNodeSeparateXYZ')
            nt.links.new(uvn.outputs['UV'], sep.inputs[0])
            def lin(k1, k2, k3, x, y):          # k1*x + k2*y + k3
                n1 = nt.nodes.new('ShaderNodeMath'); n1.operation = 'MULTIPLY_ADD'
                nt.links.new(x, n1.inputs[0]); n1.inputs[1].default_value = k1
                n2 = nt.nodes.new('ShaderNodeMath'); n2.operation = 'MULTIPLY_ADD'
                nt.links.new(y, n2.inputs[0]); n2.inputs[1].default_value = k2; n2.inputs[2].default_value = k3
                n3 = nt.nodes.new('ShaderNodeMath'); n3.operation = 'ADD'
                nt.links.new(n1.outputs[0], n3.inputs[0]); nt.links.new(n2.outputs[0], n3.inputs[1])
                n1.inputs[2].default_value = 0
                return n3.outputs[0]
            v_down = nt.nodes.new('ShaderNodeMath'); v_down.operation = 'SUBTRACT'
            v_down.inputs[0].default_value = 1.0; nt.links.new(sep.outputs['Y'], v_down.inputs[1])
            s = lin(a, c, e, sep.outputs['X'], v_down.outputs[0])
            tdown = lin(b, d, f, sep.outputs['X'], v_down.outputs[0])
            tup = nt.nodes.new('ShaderNodeMath'); tup.operation = 'SUBTRACT'
            tup.inputs[0].default_value = 1.0; nt.links.new(tdown, tup.inputs[1])
            comb = nt.nodes.new('ShaderNodeCombineXYZ')
            nt.links.new(s, comb.inputs['X']); nt.links.new(tup.outputs[0], comb.inputs['Y'])
            nt.links.new(comb.outputs[0], tex.inputs['Vector'])
    else:
        ramp = m['ramp']; col = ramp[min(len(ramp) - 1, int(len(ramp) * 0.72))] / 255.0
        bsdf.inputs['Base Color'].default_value = (*[float(x) ** 2.2 for x in col], 1.0)
    return mat


def hide_driver(obj, arm, bone, expr, extra=None):
    for path in ('hide_viewport', 'hide_render'):
        fc = obj.driver_add(path); drv = fc.driver
        drv.type = 'SCRIPTED'
        v = drv.variables.new(); v.name = 'm'; v.type = 'SINGLE_PROP'
        v.targets[0].id = arm; v.targets[0].data_path = 'pose.bones["%s"]["model"]' % bone
        if extra:
            v2 = drv.variables.new(); v2.name = 'c'; v2.type = 'SINGLE_PROP'
            v2.targets[0].id = arm; v2.targets[0].data_path = extra
        drv.expression = expr


def import_actor(name, out, preview=None, glb=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'
    scene = bpy.context.scene
    scene.render.fps = 6
    t = Template(name)
    nparts = len(t.parent)
    labels = set_labels(t)
    bone = ['%s.%02d' % (labels[t.bset[i]], i) for i in range(nparts)]
    anids = sorted(t.actions)

    # every action's local matrices, in Blender's form
    acts = []
    need_twist = [False] * nparts
    for anid in anids:
        a = t._kidref('ACTN', anid); ak = t.B.c.chunks[a]['kids']
        grf = struct.unpack('<hhi', t.B.get(*a)[:8])[2]
        xf = [mat34(e) for e in gl(t._kid('GLXF', 0, ak))]
        cels = []
        for fixed, var in gg(t._kid('GGCL', 0, ak)):
            snd, dwr = struct.unpack('<ii', fixed)
            cps = [struct.unpack('<hh', var[i * 4:i * 4 + 4]) for i in range(nparts)]   # 3DMM ignores extras
            loc = [to_blender(xf[im]) for _, im in cps]
            for i, L in enumerate(loc):
                if not is_trs(L[:3, :3]): need_twist[i] = True
            cels.append(dict(models=[ch for ch, _ in cps], local=loc, step=dwr * FX * SCALE))
        acts.append(dict(name=t.actions[anid], flags=grf, cels=cels))

    # rest pose: the first action's first cel, made rigid
    rest_local = acts[0]['cels'][0]['local']
    rest_world = [None] * nparts
    def RW(i):
        if rest_world[i] is None:
            L = rest_local[i]
            rest_world[i] = (RW(t.parent[i]) @ L) if t.parent[i] >= 0 else L
        return rest_world[i]
    bone_rest = [rigid(RW(i)) for i in range(nparts)]

    arm_data = bpy.data.armatures.new(name)
    arm_data.display_type = 'STICK'
    arm = bpy.data.objects.new(name, arm_data)
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm; arm.select_set(True)
    arm['3dmm_actor'] = name
    arm['rest_rotation'] = [x * 360.0 / 65536 for x in t.rest]      # degrees about x, y, z
    arm['template_flags'] = struct.unpack('<I', t.B.get(*t.key)[12:16])[0]
    bpy.ops.object.mode_set(mode='EDIT')
    eb = {}
    for i in range(nparts):
        b = arm_data.edit_bones.new(bone[i]); b.head = (0, 0, 0); b.tail = (0, 0.04, 0)
        b.matrix = M(bone_rest[i]); b.inherit_scale = 'FULL'; eb[i] = b
        if need_twist[i]:
            tw = arm_data.edit_bones.new(bone[i] + '.twist'); tw.head = (0, 0, 0); tw.tail = (0, 0.02, 0)
            tw.matrix = M(bone_rest[i]); tw.parent = b; tw.inherit_scale = 'FULL'
    for i in range(nparts):
        p = t.parent[i]
        if p >= 0:
            eb[i].parent = arm_data.edit_bones[bone[p] + '.twist'] if need_twist[p] else eb[p]
    bpy.ops.object.mode_set(mode='OBJECT')
    holder = lambda i: bone[i] + '.twist' if need_twist[i] else bone[i]
    for i in range(nparts):
        pb = arm.pose.bones[bone[i]]; pb.rotation_mode = 'QUATERNION'
        pb['model'] = -1; pb['set'] = int(t.bset[i]); pb['part'] = i
        if need_twist[i]: arm.pose.bones[bone[i] + '.twist'].rotation_mode = 'QUATERNION'
        if need_twist[i]: arm_data.bones[bone[i] + '.twist'].hide = True
    bpy.context.view_layer.update()

    # costumes: materials and accessories
    mats = {}
    def material(ref):
        if ref not in mats:
            m = t.material(ref)
            mats[ref] = make_material('%s.mtrl%d' % (name, ref[1]), m)
        return mats[ref]
    costumes = []; default_mat = [None] * nparts
    accessories = []
    for ibset, cmids in enumerate(t.costumes):
        parts = [i for i, b in enumerate(t.bset) if b == ibset]
        opts = []
        for o, cmid in enumerate(cmids):
            ref = t._kidref('CMTL', cmid); ckids = t.B.c.chunks[ref]['kids']
            mi, ai = [], []
            for k, p in enumerate(parts):
                mr = t._kidref('MTRL', k, ckids); ar = t._kidref('BMDL', k, ckids)
                mat = material(mr) if mr else None
                mi.append(mat.name if mat else '')
                if o == 0: default_mat[p] = mat
                if not ar: ai.append(''); continue
                if len(model(t.B.get(*ar))[2]) == 0: ai.append('-'); continue    # an empty one: takes the accessory off
                accessories.append((p, ibset, o, ar, mat)); ai.append('%s.%s.acc%d' % (name, bone[p], o))
            opts.append(dict(cmid=int(cmid), name=t.B.c.name(*ref) or ('Costume %d' % o), materials=mi, accessories=ai))
        costumes.append(dict(set=ibset, label=labels[ibset], parts=[bone[p] for p in parts], options=opts))
        arm['costume_%d' % ibset] = 0
    arm['costumes'] = json.dumps(costumes)

    # models: one mesh per (part, model) the cels use, parented to the part's bone
    meshes = {}
    def place(obj, i):
        obj.parent = arm; obj.parent_type = 'BONE'; obj.parent_bone = holder(i)
        # bone children hang from the bone's tail: step back to its head
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = Matrix.Translation((0, -arm_data.bones[holder(i)].length, 0))
    used = sorted({(i, ch) for a in acts for c in a['cels'] for i, ch in enumerate(c['models']) if ch != -1})
    for i, ch in used:
        ref = t._kidref('BMDL', ch)
        if not ref: continue
        V, UV, F, sm = model(t.B.get(*ref))
        if len(F) == 0: continue
        if ch not in meshes: meshes[ch] = make_mesh('%s.model%d' % (name, ch), V, UV, F, sm)
        obj = bpy.data.objects.new('%s.%s.m%d' % (name, bone[i], ch), meshes[ch])
        scene.collection.objects.link(obj)
        obj['model'] = int(ch)
        obj.material_slots[0].link = 'OBJECT'
        if default_mat[i]: obj.material_slots[0].material = default_mat[i]
        place(obj, i)
        hide_driver(obj, arm, bone[i], 'm != %d' % ch)
    for p, ibset, o, ar, mat in accessories:
        V, UV, F, sm = model(t.B.get(*ar))
        if len(F) == 0: continue
        me = make_mesh('%s.acc%d' % (name, ar[1]), V, UV, F, sm)
        obj = bpy.data.objects.new('%s.%s.acc%d' % (name, bone[p], o), me)
        scene.collection.objects.link(obj)
        obj['model'] = -1; obj['costume_set'] = ibset; obj['costume_option'] = o
        obj.material_slots[0].link = 'OBJECT'
        if mat: obj.material_slots[0].material = mat
        place(obj, p)
        hide_driver(obj, arm, bone[p], '(m != -1) + (c != %d)' % o, extra='["costume_%d"]' % ibset)

    # actions
    arm.animation_data_create()
    rest_parent = [np.linalg.inv(bone_rest[t.parent[i]]) @ bone_rest[i] if t.parent[i] >= 0 else bone_rest[i]
                   for i in range(nparts)]
    first = None
    for a in acts:
        act = bpy.data.actions.new(a['name'])
        act.use_fake_user = True
        act['steps'] = [c['step'] for c in a['cels']]
        act['flags'] = a['flags']; act['anid'] = len(bpy.data.actions) - 1; act['3dmm'] = True
        arm.animation_data.action = act
        if first is None: first = act
        quat_prev = {}
        for f, c in enumerate(a['cels']):
            for i in range(nparts):
                L = c['local'][i]
                if need_twist[i]:
                    A, B = split_twist(L)
                else:
                    A, B = L, None
                basis = np.linalg.inv(rest_parent[i]) @ A
                pb = arm.pose.bones[bone[i]]
                pb.matrix_basis = M(basis)
                q = pb.rotation_quaternion.copy()
                if bone[i] in quat_prev and q.dot(quat_prev[bone[i]]) < 0: pb.rotation_quaternion = -q
                quat_prev[bone[i]] = pb.rotation_quaternion.copy()
                for prop in ('location', 'rotation_quaternion', 'scale'):
                    pb.keyframe_insert(prop, frame=f)
                pb['model'] = int(c['models'][i]); pb.keyframe_insert('["model"]', frame=f)
                if B is not None:
                    tb = arm.pose.bones[bone[i] + '.twist']; tb.matrix_basis = M(B)
                    tb.keyframe_insert('rotation_quaternion', frame=f)
        act.frame_range = (0, max(0, len(a['cels']) - 1)); act.use_frame_range = True
    arm.animation_data.action = first
    scene.frame_start = 0; scene.frame_end = int(first.frame_range[1]); scene.frame_set(0)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out), compress=True)
    if glb:
        bpy.ops.export_scene.gltf(filepath=os.path.abspath(glb), export_animations=False)
    if preview:
        render_preview(arm, preview)
    return arm


def frame_camera(arm, square=False, head=False):
    """a camera looking at the actor's visible meshes from the front left, or a close-up of the head"""
    scene = bpy.context.scene
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in scene.objects:
        if o.type != 'MESH' or o.parent is not arm: continue
        oe = o.evaluated_get(deps)
        if oe.hide_render: continue
        pts += [oe.matrix_world @ Vector(c) for c in oe.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    mid = (lo + hi) / 2; size = max(hi - lo)
    cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera')); scene.collection.objects.link(cam)
    cam.data.lens = 50
    if not any(o.type == 'LIGHT' for o in scene.objects):
        sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN')); scene.collection.objects.link(sun)
        sun.rotation_euler = (math.radians(50), math.radians(-20), math.radians(-60)); sun.data.energy = 3.5
    if scene.world is None:
        scene.world = bpy.data.worlds.new('World'); scene.world.use_nodes = True
        scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.55, 0.55, 0.6, 1)
    # actors are modeled facing sideways; the template's rest rotation turns them to the camera (+z)
    xa, ya, za = [math.radians(-a) for a in arm.get('rest_rotation', (0, 90, 0))]
    def rot(axis, a):
        c, s_ = math.cos(a), math.sin(a)
        return {'x': np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]]), 'y': np.array([[c, 0, s_], [0, 1, 0], [-s_, 0, c]]),
                'z': np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])}[axis]
    f3 = rot('x', xa) @ rot('y', ya) @ rot('z', za) @ np.array([0, 0, 1.0])
    front = Vector(C[:3, :3] @ f3); front.z = 0; front.normalize()
    side = Vector((0, 0, 1)).cross(front)
    if head:                                     # the top of the actor, nearly face on
        top = [p for p in pts if p.z > hi.z - (hi.z - lo.z) * 0.22]
        hlo = Vector((min(p.x for p in top), min(p.y for p in top), hi.z - (hi.z - lo.z) * 0.22))
        mid = (hlo + hi) / 2; d = max(hi.x - hlo.x, hi.z - hlo.z) * 2.3
        cam.location = mid + d * (front * 0.95 + side * 0.3) + Vector((0, 0, d * 0.05))
        cam.rotation_euler = (mid - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.camera = cam
        return cam
    d = size * (1.9 if square else 2.2)
    cam.location = mid + d * (front * 0.9 + side * 0.45) + Vector((0, 0, d * 0.15))
    cam.rotation_euler = (mid - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    return cam


def render_preview(arm, path, frame=0):
    scene = bpy.context.scene
    scene.frame_set(frame)
    frame_camera(arm)
    scene.render.resolution_x = 480; scene.render.resolution_y = 600
    scene.render.filepath = os.path.abspath(path)
    bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    opts = {}
    for k in ('--preview', '--glb'):
        if k in args:
            j = args.index(k); opts[k[2:]] = args[j + 1]; del args[j:j + 2]
    import_actor(args[0], args[1], **opts)
