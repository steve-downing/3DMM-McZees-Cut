"""The painting's canvas (HH-Dining, end wall by the door), as a texture.

    python painting.py            -> data/painting.png

The canvas is projected into the original pictures: camera 2 sees most of it,
large but cut off at the top; camera 4 sees all of it, small. The two are
matched in brightness and blended, then brightened (see below)."""
import sys, os, numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates, distance_transform_edt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
from bkgd import Bkgd
from fuse import focal

CANVAS_Z, CANVAS_Y, WALL_X = (-127.2, -114.0), (14.6, 23.0), 136.35   # measured (frame inner edge)

def main(out=os.path.join(HERE, 'data', 'painting.png')):
    vs = Bkgd().views(8)
    res = 0.03
    zs = np.arange(*CANVAS_Z, res); ys = np.arange(CANVAS_Y[1], CANVAS_Y[0], -res)
    G = np.stack(np.meshgrid(zs, ys), -1)
    Pw = np.stack([np.full(G.shape[:2], WALL_X), G[..., 1], G[..., 0]], -1)
    def sample(k):
        v = vs[k]; R, T = v['mat'][:3], v['mat'][3]
        Pc = (Pw - T) @ R.T; h, w = v['z'].shape; f = focal(v)
        px = Pc[..., 0] * f / (-Pc[..., 2]) + w / 2 - 0.5; py = -Pc[..., 1] * f / (-Pc[..., 2]) + h / 2 - 0.5
        img = np.stack([map_coordinates(v['rgb'][..., c].astype(float), [py, px], order=1) for c in range(3)], -1)
        return img, (px >= 1) & (px < w - 2) & (py >= 1) & (py < h - 2)
    a, oka = sample(1); b, okb = sample(3)
    both = oka & okb
    b = b * np.median(a[both], 0) / np.maximum(np.median(b[both], 0), 1)
    wa = np.clip(distance_transform_edt(oka) / 15, 0, 1)[..., None]
    # the pictures already carry 1995's lighting, and the player lights the canvas again:
    # store it brighter so it reads as it did
    img = (a * wa + b * (1 - wa)) * 1.9
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)
    print('painting', img.shape[1], 'x', img.shape[0], '->', out)

if __name__ == '__main__':
    main(*sys.argv[1:2])
