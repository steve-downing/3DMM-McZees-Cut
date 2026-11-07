"""Assemble the rebuilt cabin: swept shell, end walls with the door recess,
one seat instanced 13 times, one side table instanced (and mirrored) twice."""
import sys, os, json
import numpy as np
import trimesh
import mapbox_earcut as earcut
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from layout import INST, R, SMALL, TABLES

def tex_mesh(V, F, uv, img, name):
    mat = trimesh.visual.material.SimpleMaterial(image=img, diffuse=[255, 255, 255, 255])
    m = trimesh.Trimesh(np.asarray(V, float), np.asarray(F), process=False,
                        visual=trimesh.visual.TextureVisuals(uv=np.asarray(uv, float), image=img, material=mat))
    m.metadata['name'] = name
    return m

def color_mesh(m, rgb):
    c = np.array(rgb, float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)   # glTF colors are linear
    m.visual = trimesh.visual.ColorVisuals(m, vertex_colors=np.tile(np.r_[np.round(c * 255), 255].astype(np.uint8), (len(m.vertices), 1)))
    return m

def arch_outline(A, n=24):
    xc, hw, sp = A['xc'], A['hw'], A['spring']
    pts = [(xc + hw, 0.0), (xc + hw, sp)]
    pts += [(xc + hw * np.cos(t), sp + hw * np.sin(t)) for t in np.linspace(0, np.pi, n)[1:-1]]
    pts += [(xc - hw, sp), (xc - hw, 0.0)]
    return np.array(pts)

def polygon(outer, holes, z):
    rings = [outer] + holes
    verts = np.vstack(rings)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tri = earcut.triangulate_float64(verts, ends).reshape(-1, 3)
    V = np.c_[verts, np.full(len(verts), z)]
    return V, tri

def main(d, out):
    sh = json.load(open(os.path.join(d, 'shell.json')))
    loop = np.array(sh['loop']); s = np.array(sh['s']); S = s[-1]
    Z0, Z1, ZD, RES, A = sh['Z0'], sh['Z1'], sh['ZDOOR'], sh['RES'], sh['ARCH']
    scene = trimesh.Scene()

    # --- shell: the profile swept from the front wall to the rear wall
    V = []; F = []; UV = []
    for i in range(len(loop) - 1):
        a, b = loop[i], loop[i + 1]; k = len(V)
        V += [[a[0], a[1], Z0], [b[0], b[1], Z0], [b[0], b[1], Z1], [a[0], a[1], Z1]]
        UV += [[s[i] / S, 0], [s[i + 1] / S, 0], [s[i + 1] / S, 1], [s[i] / S, 1]]
        F += [[k, k + 1, k + 2], [k, k + 2, k + 3]]
    scene.add_geometry(tex_mesh(V, F, UV, Image.open(os.path.join(d, 'shell.jpg')), 'shell'), geom_name='shell', node_name='shell')

    # --- end walls (orthographic textures)
    def end_uv(P, e):
        return np.c_[(P[:, 0] - e['x0']) / (e['W'] * RES), P[:, 1] / (e['H'] * RES)]
    outer = loop[:-1][::-1].copy()          # earcut wants a simple ring; orientation is handled by earcut
    arch = arch_outline(A)
    fe = sh['ends']['front']; re_ = sh['ends']['rear']
    fimg = Image.open(os.path.join(d, 'front.jpg')); rimg = Image.open(os.path.join(d, 'rear.jpg'))
    V, T = polygon(outer, [arch], Z0)
    scene.add_geometry(tex_mesh(V, T, end_uv(V, fe), fimg, 'front_wall'), geom_name='front_wall', node_name='front_wall')
    V, T = polygon(arch, [], ZD)
    scene.add_geometry(tex_mesh(V, T, end_uv(V, fe), fimg, 'door'), geom_name='door', node_name='door')
    # door recess: the arch outline extruded from the wall to the door; textured with the frame color at the outline
    V = []; F = []; UV = []
    inner = arch - np.sign(arch - [A['xc'], A['spring']]) * [0.15, 0.0]   # sample just inside the frame
    for i in range(len(arch) - 1):
        a, b = arch[i], arch[i + 1]; ua, ub = inner[i], inner[i + 1]; k = len(V)
        V += [[a[0], a[1], Z0], [b[0], b[1], Z0], [b[0], b[1], ZD], [a[0], a[1], ZD]]
        uvp = end_uv(np.array([ua, ub, ub, ua]), fe); UV += uvp.tolist()
        F += [[k, k + 1, k + 2], [k, k + 2, k + 3]]
    # recess floor: continues the door texture's bottom row toward the wall
    x0r, x1r = A['xc'] - A['hw'], A['xc'] + A['hw']; k = len(V)
    V += [[x0r, 0, Z0], [x1r, 0, Z0], [x1r, 0, ZD], [x0r, 0, ZD]]
    UV += end_uv(np.array([[x0r + 0.15, 0.05], [x1r - 0.15, 0.05], [x1r - 0.15, 0.05], [x0r + 0.15, 0.05]]), fe).tolist()
    F += [[k, k + 1, k + 2], [k, k + 2, k + 3]]
    scene.add_geometry(tex_mesh(V, F, UV, fimg, 'door_recess'), geom_name='door_recess', node_name='door_recess')
    V, T = polygon(outer, [], Z1)
    scene.add_geometry(tex_mesh(V, T, end_uv(V, re_), rimg, 'rear_wall'), geom_name='rear_wall', node_name='rear_wall')

    # --- seats: one model, 13 placements
    st = np.load(os.path.join(d, 'photo', 'seat_tex.npz')); SV = st['V'].copy()
    low = SV[:, 1] < 0.3; SV[low, 1] = np.maximum(0.0, SV[low, 1] - 0.17)   # legs reach the floor
    seat = tex_mesh(SV, st['F'], st['uv'], Image.open(os.path.join(d, 'photo', 'seat_tex.png')), 'seat')
    placements = [(R(f), t) for t, f in INST]
    placements.append((R(SMALL['flip']) @ np.diag([0.66, 0.89, 0.9]), np.array([-0.6, 0.0, 27.0])))
    for i, (Aff, t) in enumerate(placements):
        M = np.eye(4); M[:3, :3] = Aff; M[:3, 3] = t
        scene.add_geometry(seat, geom_name='seat', node_name='seat_%02d' % i, transform=M)

    # --- side tables
    tt = np.load(os.path.join(d, 'photo', 'table_tex.npz')); parts = json.load(open(os.path.join(d, 'photo', 'table_parts.json')))
    top = tex_mesh(tt['V'], tt['F'], tt['uv'], Image.open(os.path.join(d, 'photo', 'table_tex.png')), 'table_top')
    ty = parts['top_y']
    legs = []
    for zl in (-2.08, 2.08):
        c = trimesh.creation.cylinder(radius=0.11, height=ty, sections=10)
        c.apply_translation([1.05, ty / 2, zl])
        c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0], [1.05, ty / 2, zl])) if False else None
        # trimesh cylinders run along z; stand them up
        legs.append(c)
    legs = [trimesh.creation.cylinder(radius=0.11, segment=[[1.05, 0, zl], [1.05, ty, zl]], sections=10) for zl in (-2.08, 2.08)]
    leg = color_mesh(trimesh.util.concatenate(legs), parts['leg'])
    bracket = color_mesh(trimesh.creation.box(extents=[0.25, ty - 0.2, 4.4], transform=trimesh.transformations.translation_matrix([-1.57, 0.1 + (ty - 0.2) / 2, 0])), parts['bracket'])
    for i, (Aff, t) in enumerate(TABLES):
        M = np.eye(4); M[:3, :3] = Aff; M[:3, 3] = t
        scene.add_geometry(top, geom_name='table_top', node_name='table_%d' % i, transform=M)
        scene.add_geometry(leg, geom_name='table_legs', node_name='table_legs_%d' % i, transform=M)
        scene.add_geometry(bracket, geom_name='table_bracket', node_name='table_bracket_%d' % i, transform=M)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    scene.export(out)
    print('wrote', out, '%.1f MB' % (os.path.getsize(out) / 1e6), 'triangles placed:',
          sum(len(scene.geometry[g].faces) for _, g in [(n, scene.graph[n][1]) for n in scene.graph.nodes_geometry]))

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'data'),
         sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, 'out', 'cabin.glb'))
