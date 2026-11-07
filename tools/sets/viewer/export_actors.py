"""Export every 3DMM actor for the explorer's character picker.

    python export_actors.py <out dir>          -> <out dir>/actors/...

Writes actors/index.json (id and name per actor, in the game's own order) and,
per actor, <id>.glb (every model any action uses, in model space, with its
costume) and <id>.json (the body tree and each action's cels; see actor.rig)."""
import sys, os, json, re, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from bkgd import Bkgd
from actor import Template, rig
from paths import ROOT

def actor_names():
    """the 45 actors, from the actor browser's thumbnails (actor.3th), in browser order"""
    th = Bkgd(os.path.join(ROOT, 'content-files', 'actor.3th'))
    tm = Bkgd(os.path.join(ROOT, 'content-files', 'tmpls.3cn'))
    names = {k[1]: tm.c.name(*k) for k in tm.c.chunks if k[0] == 'TMPL'}
    return [names[struct.unpack('<I', th.get(*k)[8:12])[0]] for k in sorted(k for k in th.c.chunks if k[0] == 'TMTH')]

def main(out):
    d = os.path.join(out, 'actors'); os.makedirs(d, exist_ok=True)
    index = []
    for name in actor_names():
        aid = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        scene, meta = rig(Template(name))
        meta['name'] = name
        scene.export(os.path.join(d, aid + '.glb'))
        json.dump(meta, open(os.path.join(d, aid + '.json'), 'w'), separators=(',', ':'))
        index.append(dict(id=aid, name=name))
        print('%-16s %3d meshes %2d actions' % (name, meta['meshes'], len(meta['actions'])))
    json.dump(index, open(os.path.join(d, 'index.json'), 'w'), indent=0)

if __name__ == '__main__':
    main(sys.argv[1])
