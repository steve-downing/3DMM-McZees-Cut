"""Turnaround sheet of an actor .blend: front, three-quarter, side, back, and a head close-up.

    python preview.py <actor.blend> <out.png> [--action NAME --frame N]
"""
import sys, os, math
import numpy as np
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
src, out = args[0], args[1]
bpy.ops.wm.open_mainfile(filepath=os.path.abspath(src))
scene = bpy.context.scene
arm = [o for o in scene.objects if o.type == 'ARMATURE'][0]
if '--action' in args:
    arm.animation_data.action = bpy.data.actions[args[args.index('--action') + 1]]
scene.frame_set(int(args[args.index('--frame') + 1]) if '--frame' in args else 0)
for o in [o for o in scene.objects if o.type in ('CAMERA', 'LIGHT')]: bpy.data.objects.remove(o)
deps = bpy.context.evaluated_depsgraph_get()
pts = []
for o in scene.objects:
    if o.type == 'MESH' and not o.evaluated_get(deps).hide_render:
        oe = o.evaluated_get(deps); pts += [oe.matrix_world @ Vector(c) for c in oe.bound_box]
lo = Vector([min(p[k] for p in pts) for k in range(3)]); hi = Vector([max(p[k] for p in pts) for k in range(3)])
mid = (lo + hi) / 2; H = hi.z - lo.z
sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN')); scene.collection.objects.link(sun)
sun.data.energy = 3.2
fill = bpy.data.objects.new('Fill', bpy.data.lights.new('Fill', 'SUN')); scene.collection.objects.link(fill)
fill.data.energy = 1.0; fill.rotation_euler = (math.radians(70), 0, math.radians(120))
scene.world = scene.world or bpy.data.worlds.new('W'); scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.75, 0.75, 0.78, 1)
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = 'ORTHO'
scene.render.resolution_x, scene.render.resolution_y = 300, 520
from PIL import Image
panels = []
views = [('front', 180), ('three-quarter', 215), ('side', 270), ('back', 0)]
for name, az in views:
    a = math.radians(az)
    d = Vector((math.cos(a), math.sin(a), 0.08)).normalized()
    cam.location = mid + d * 6; cam.rotation_euler = (mid - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.ortho_scale = H * 1.1
    sun.rotation_euler = (math.radians(50), 0, a + math.radians(-30))
    path = out + '.%s.png' % name; scene.render.filepath = path
    bpy.ops.render.render(write_still=True); panels.append(Image.open(path).convert('RGB')); os.remove(path)
# head close-up, three-quarter
a = math.radians(205); d = Vector((math.cos(a), math.sin(a), 0.15)).normalized()
hc = Vector((mid.x - 0.05, mid.y, hi.z - H * 0.15))
cam.location = hc + d * 6; cam.rotation_euler = (hc - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.ortho_scale = H * 0.42; sun.rotation_euler = (math.radians(50), 0, a - math.radians(30))
scene.render.resolution_x = 520
path = out + '.head.png'; scene.render.filepath = path
bpy.ops.render.render(write_still=True); panels.append(Image.open(path).convert('RGB')); os.remove(path)
W = sum(p.width for p in panels); sheet = Image.new('RGB', (W, 520), (255, 255, 255)); x = 0
for p in panels: sheet.paste(p, (x, 0)); x += p.width
sheet.save(out)
