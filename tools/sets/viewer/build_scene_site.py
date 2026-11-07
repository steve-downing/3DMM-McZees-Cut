"""Gather the 3D scene player into one folder, ready to publish or serve.

    python build_scene_site.py <scene dir> <site dir> [<cabin set dir>]

<scene dir> is export_scene.py's output. Takes the cartoon cabin from
<cabin set dir>/out/toon.glb (default: ../airplane; build it with toon.py).
scene.html is the page; serve the folder over http to try it locally."""
import sys, os, shutil, base64

def main(scene_dir, site, setdir=None):
    here = os.path.dirname(os.path.abspath(__file__))
    setdir = setdir or os.path.join(here, '..', 'airplane')
    os.makedirs(site, exist_ok=True)
    shutil.copy(os.path.join(here, 'surface.js'), site)
    # the page's title names the movie (it's what the tab and a shared link show)
    import json, html
    name = json.load(open(os.path.join(scene_dir, 'scene.json')))['name']
    page = open(os.path.join(here, 'scene.html'), encoding='utf-8').read()
    page = page.replace('<title>Cabin Scene in 3D</title>', '<title>%s in 3D</title>' % html.escape(name), 1)
    open(os.path.join(site, 'scene.html'), 'w', encoding='utf-8').write(page)
    for f in os.listdir(scene_dir):
        if f.startswith('scene.'): shutil.copy(os.path.join(scene_dir, f), site)
    glb = os.path.join(setdir, 'out', 'toon.glb')
    if not os.path.exists(glb): raise SystemExit('build the cabin first: python %s' % os.path.join(setdir, 'toon.py'))
    open(os.path.join(site, 'toon.glb.txt'), 'w').write(base64.b64encode(open(glb, 'rb').read()).decode())
    print('site ->', site)

if __name__ == '__main__':
    main(*sys.argv[1:4])
