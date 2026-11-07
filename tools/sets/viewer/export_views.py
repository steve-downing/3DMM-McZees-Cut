"""Export a background's original camera views for the explorer and compare.py.

    python export_views.py <background number> <out dir>      (airplane = 10)

Writes cam<k>.jpg (the 1995 render, 544x306) and cams.json (per camera:
vertical fov in degrees, position, and rotation rows = camera axes, world units)."""
import sys, os, json
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from bkgd import Bkgd

def main(cno, out):
    os.makedirs(out, exist_ok=True)
    cams = []
    for k, v in enumerate(Bkgd().views(cno)):
        Image.fromarray(v['rgb']).save(os.path.join(out, 'cam%d.jpg' % k), quality=90)
        cams.append({'fov': round(float(np.degrees(v['fov'])), 3), 'pos': [round(float(a), 4) for a in v['mat'][3]],
                     'rot': [[round(float(a), 5) for a in row] for row in v['mat'][:3]]})
    json.dump(cams, open(os.path.join(out, 'cams.json'), 'w'))
    print(len(cams), 'views ->', out)

if __name__ == '__main__':
    main(int(sys.argv[1]), sys.argv[2])
