import sys, os, numpy as np, trimesh
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from seatfuse import INST, R, views
from bake import bake
s = trimesh.load(sys.argv[1], force='mesh')
V = np.asarray(s.vertices); F = np.asarray(s.faces)
vs = views()
vmap, Fn, uv, tex = bake(V, F, [(R(f), t) for t, f in INST], vs, size=1024)
Image.fromarray(np.clip(tex, 0, 255).astype(np.uint8)[::-1]).save(sys.argv[2] + '.png')
np.savez(sys.argv[2] + '.npz', V=V[vmap], F=Fn, uv=uv)
