"""Gather the explorer page into one folder, ready to publish or serve.

    python build_site.py <set dir> <views dir> <site dir> [actors dir]

Takes <set dir>/out/toon.glb and, if present, out/cabin.glb (the photo version,
compressed with gltfpack), and <set dir>/viewer.json as set.json (the set's
lights, sky, names and where an actor stands). <views dir> is export_views.py's
output: the original pictures and cams.json. [actors dir] is export_actors.py's output folder; its
actors become the explorer's character picker. Models ship as base64 .glb.txt files
because some static hosts won't serve .glb. index.html loads three.js from a
CDN; for a local test, serve <site dir> over http (file:// won't load modules)."""
import sys, os, shutil, base64, subprocess, tempfile

def main(setdir, views, site, actors_dir=None):
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(site, 'views'), exist_ok=True)
    for f in ('index.html', 'surface.js'):
        shutil.copy(os.path.join(here, f), site)
    for f in os.listdir(views):
        if f.startswith('cam') and (f.endswith('.jpg') or f == 'cams.json'): shutil.copy(os.path.join(views, f), os.path.join(site, 'views'))
    # the set's settings (names, lights, sky, actor spot; see build_scene_site.py) and the page's title
    import json, html
    vj = os.path.join(setdir, 'viewer.json')
    cfg = json.load(open(vj)) if os.path.exists(vj) else {}
    json.dump(cfg, open(os.path.join(site, 'set.json'), 'w'))
    title = cfg.get('explorer', {}).get('title', 'A Set in 3D').replace(', in 3D', ' in 3D')
    page = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
    page = page.replace('<title>Airplane Set in 3D</title>', '<title>%s</title>' % html.escape(title), 1)
    open(os.path.join(site, 'index.html'), 'w', encoding='utf-8').write(page)
    def ship(glb, name, pack):
        if pack:
            packed = os.path.join(tempfile.mkdtemp(), name + '.glb')
            cmd = ['gltfpack'] if shutil.which('gltfpack') else ['npx', '--yes', 'gltfpack@0.22.0']
            subprocess.run(cmd + ['-i', glb, '-o', packed, '-cc'], check=True)
            glb = packed
        open(os.path.join(site, name + '.glb.txt'), 'w').write(base64.b64encode(open(glb, 'rb').read()).decode())
    ship(os.path.join(setdir, 'out', 'toon.glb'), 'toon', False)
    photo = os.path.join(setdir, 'out', 'cabin.glb')
    if os.path.exists(photo): ship(photo, 'cabin', True)
    if actors_dir:
        src = os.path.join(actors_dir, 'actors') if os.path.isdir(os.path.join(actors_dir, 'actors')) else actors_dir
        dst = os.path.join(site, 'actors'); os.makedirs(dst, exist_ok=True)
        for f in os.listdir(src):
            if f.endswith('.json'): shutil.copy(os.path.join(src, f), dst)
            elif f.endswith('.glb'):
                open(os.path.join(dst, f + '.txt'), 'w').write(base64.b64encode(open(os.path.join(src, f), 'rb').read()).decode())
    print('site ->', site)

if __name__ == '__main__':
    main(*sys.argv[1:5])
