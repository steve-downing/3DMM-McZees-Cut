"""Original 3DMM actors standing in the cabin, to see how they sit in the rebuilt set.

    python actors.py [out.glb]              -> out/actors.glb

Each actor is posed in its first action ("At Rest"), first cel, in its default
costume, with the 1995 models and textures as they are. Actors face -x in
their own frame; a yaw of 90 degrees turns them toward the rear of the cabin."""
import sys, os
import numpy as np
import trimesh
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from actor import Template, to_meshes

# name: (x, z, yaw in degrees), on the floor of the aisle
CAST = {'Gustave': (-3.2, 9.0, 110), 'Bongo': (2.6, 6.0, 70)}

def place(x, z, yaw):
    a = np.radians(yaw); c, s = np.cos(a), np.sin(a)
    M = np.eye(4); M[:3, :3] = [[c, 0, s], [0, 1, 0], [-s, 0, c]]; M[:3, 3] = [x, 0, z]
    return M

def main(out):
    scene = trimesh.Scene()
    for name, (x, z, yaw) in CAST.items():
        for nm, m in to_meshes(Template(name).pose(0, 0), place(x, z, yaw), name):
            scene.add_geometry(m, geom_name=nm, node_name=nm)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    scene.export(out)
    print('wrote', out, '%.2f MB' % (os.path.getsize(out) / 1e6))

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'actors.glb'))
