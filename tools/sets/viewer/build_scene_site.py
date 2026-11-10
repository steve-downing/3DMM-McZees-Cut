"""Gather the 3D scene player into one folder, ready to publish or serve.

    python build_scene_site.py <scene dir> <site dir> [<set dir> | --blank]

<scene dir> is export_scene.py's output. The set comes from the scene's own
background: a rebuilt set from SETS below (its out/toon.glb, built with its
toon.py, and its viewer.json), or an empty stage for 3DMM's black background
and for sets that haven't been rebuilt yet. Pass a set dir to choose one, or
--blank for the empty stage. scene.html is the page; serve the folder over
http to try it locally.

A set's viewer.json (all optional):
  where   how the page says where it's staged ("in the rebuilt cartoon cabin")
  near    {camera number: near clip}, for cameras that sit just outside a wall
  vr      {"pos": [x, y, z] meters, "yaw": radians}: where VR starts
  sky     true (or "night"): show the sky outside (windows)
  shadows false: no cast shadows (a set lit from everywhere, like the cabin)
  floor   [x0, z0, x1, z1]: where you may teleport to in VR (3DMM units)
  lights  {"hemi": [sky color, ground color, intensity],
           "sun": {"pos", "target", "color", "intensity", "extent"},
           "lamps": [{"pos", "color", "intensity", "distance"}]}
"""
import sys, os, shutil, base64, json, html

HERE = os.path.dirname(os.path.abspath(__file__))
# background number -> rebuilt set (a folder next to this one)
SETS = {10: 'airplane', 8: 'dining'}
BLACK = 11


def main(scene_dir, site, setdir=None):
    meta = json.load(open(os.path.join(scene_dir, 'scene.json')))
    os.makedirs(site, exist_ok=True)
    for f in os.listdir(site):   # a set from an earlier build mustn't linger
        if f.startswith('set.'): os.remove(os.path.join(site, f))
    shutil.copy(os.path.join(HERE, 'surface.js'), site)
    # the page's title names the movie (it's what the tab and a shared link show)
    page = open(os.path.join(HERE, 'scene.html'), encoding='utf-8').read()
    page = page.replace('<title>A Scene in 3D</title>', '<title>%s in 3D</title>' % html.escape(meta['name']), 1)
    open(os.path.join(site, 'scene.html'), 'w', encoding='utf-8').write(page)
    for f in os.listdir(scene_dir):
        if f.startswith('scene.'): shutil.copy(os.path.join(scene_dir, f), site)

    if setdir is None and meta['bkgd'] in SETS:
        setdir = os.path.join(HERE, '..', SETS[meta['bkgd']])
    if setdir in (None, '--blank'):
        if meta['bkgd'] != BLACK:
            print('note: %s has no 3D set yet; the scene plays on an empty stage' % meta.get('bkgd_name', meta['bkgd']))
        cfg = dict(where='on an empty stage' if meta['bkgd'] == BLACK else 'on an empty stage (this set isn\'t rebuilt in 3D yet)')
    else:
        glb = os.path.join(setdir, 'out', 'toon.glb')
        if not os.path.exists(glb): raise SystemExit('build the set first: python %s' % os.path.join(setdir, 'toon.py'))
        open(os.path.join(site, 'set.glb.txt'), 'w').write(base64.b64encode(open(glb, 'rb').read()).decode())
        vj = os.path.join(setdir, 'viewer.json')
        cfg = json.load(open(vj)) if os.path.exists(vj) else {}
        cfg.setdefault('where', 'in the rebuilt set')
        cfg['model'] = 'set.glb.txt'
    json.dump(cfg, open(os.path.join(site, 'set.json'), 'w'))
    print('site ->', site, '(%s)' % cfg['where'])


if __name__ == '__main__':
    main(*sys.argv[1:4])
