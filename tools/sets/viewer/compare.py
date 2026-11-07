"""Our model next to the original, from every original 3DMM camera: the review
step to run before showing anyone a new version (see ../STYLE.md).

    python compare.py <model.glb> <views dir> <out.png>

<views dir> holds cams.json and cam<k>.jpg from export_views.py. Writes one
image: a row per camera, ours on the left, the 1995 render on the right."""
import sys, os, json, subprocess, tempfile
from PIL import Image, ImageDraw

def main(model, views, out):
    cams = json.load(open(os.path.join(views, 'cams.json')))
    tmp = tempfile.mkdtemp()
    jobs = [{'js': 'setView(%d)' % k, 'out': os.path.join(tmp, 'c%d.png' % k)} for k in range(len(cams))]
    subprocess.run(['node', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shoot.js'),
                    os.path.abspath(model), os.path.join(views, 'cams.json'), json.dumps(jobs)], check=True)
    W, H = 544, 306
    sheet = Image.new('RGB', (2 * W + 8, len(cams) * (H + 8)), (20, 20, 24))
    dr = ImageDraw.Draw(sheet)
    for k, j in enumerate(jobs):
        y = k * (H + 8)
        sheet.paste(Image.open(j['out']).convert('RGB').resize((W, H)), (0, y))
        sheet.paste(Image.open(os.path.join(views, 'cam%d.jpg' % k)).convert('RGB').resize((W, H)), (W + 8, y))
        dr.text((6, y + 4), 'camera %d' % (k + 1), fill=(255, 255, 0))
    sheet.save(out)
    print('wrote', out)

if __name__ == '__main__':
    main(*sys.argv[1:4])
