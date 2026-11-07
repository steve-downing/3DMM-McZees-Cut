"""Gather the explorer page into one folder, ready to publish or serve.

    python build_site.py <set dir> <views dir> <site dir>

Takes <set dir>/out/toon.glb and, if present, out/cabin.glb (the photo
version, compressed with gltfpack). Models ship as base64 .glb.txt files
because some static hosts won't serve .glb. index.html loads three.js from a
CDN; for a local test, serve <site dir> over http (file:// won't load modules)."""
import sys, os, shutil, base64, subprocess, tempfile

def main(setdir, views, site):
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(site, 'views'), exist_ok=True)
    for f in ('index.html', 'surface.js'):
        shutil.copy(os.path.join(here, f), site)
    for f in os.listdir(views):
        if f.startswith('cam') and f.endswith('.jpg'): shutil.copy(os.path.join(views, f), os.path.join(site, 'views'))
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
    print('site ->', site)

if __name__ == '__main__':
    main(*sys.argv[1:4])
