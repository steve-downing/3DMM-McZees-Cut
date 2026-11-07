"""Check an imported actor against 3DMM's own posing math.

    python check_actor.py <actor name> <actor.blend> [--all]

For every action (every cel with --all, else the first, middle and last),
poses the armature in Blender and compares each visible mesh's vertices with
Template.pose from tools/sets/lib/actor.py. Prints the worst error in
millimeters (3DMM units are 10 cm here) and exits 1 if anything is off by
more than 0.25 mm, or a part shows the wrong model.
"""
import sys, os
import numpy as np
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'sets', 'lib'))
from actor import Template  # noqa: E402
from import_actor import point  # noqa: E402


def check(name, path, every=False):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(path))
    scene = bpy.context.scene
    arm = bpy.data.objects[name]
    t = Template(name)
    parts = {}
    for o in scene.objects:
        if o.type == 'MESH' and o.parent is arm:
            parts.setdefault(arm.pose.bones[o.parent_bone.replace('.twist', '')]['part'], []).append(o)
    worst = 0.0; bad = 0; checked = 0
    for anid in sorted(t.actions):
        act = bpy.data.actions[t.actions[anid]]
        arm.animation_data.action = act
        n = len(act['steps'])
        cels = range(n) if every else sorted({0, n // 2, n - 1})
        for c in cels:
            scene.frame_set(c)
            deps = bpy.context.evaluated_depsgraph_get()
            want = {i: (V, F) for V, UV, F, sm, m, i in t.pose(anid, c)}
            for i, objs in parts.items():
                shown = [o for o in objs if not o.evaluated_get(deps).hide_render]
                if i not in want:
                    if shown: bad += 1; print('  %s cel %d part %d: shows %s, wants nothing' % (act.name, c, i, [o.name for o in shown]))
                    continue
                V, F = want[i]
                if len(shown) != 1 or len(shown[0].data.vertices) != len(V):
                    bad += 1; print('  %s cel %d part %d: shows %s' % (act.name, c, i, [o.name for o in shown])); continue
                o = shown[0].evaluated_get(deps)
                Mw = np.array(o.matrix_world)
                got = np.array([v.co for v in o.data.vertices]) @ Mw[:3, :3].T + Mw[:3, 3]
                ref = np.array([point(v) for v in V])
                err = np.abs(got - ref).max() * 1000
                worst = max(worst, err); checked += 1
                if err > 0.25: bad += 1; print('  %s cel %d part %d: off by %.3f mm' % (act.name, c, i, err))
    print('%s: %d actions, %d part poses checked, worst %.4f mm, %d problems' % (name, len(t.actions), checked, worst, bad))
    return bad == 0


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    ok = check(args[0], args[1], '--all' in args)
    sys.exit(0 if ok else 1)
