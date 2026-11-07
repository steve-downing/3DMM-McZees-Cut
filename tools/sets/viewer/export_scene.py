"""One scene of a movie, for the 3D scene player (scene.html).

    python export_scene.py <poses.txt|.zip> <scene> <out dir> [--video movie.mp4] [--name NAME]

<poses> comes from 3dmm-render --poses (or render-folder.ps1 -Poses); <scene> is
the scene's number as 3DMM counts it, from 1. Writes into <out dir>:

  scene.json      the frames: time (ms from the scene's start), the movie's camera,
                  and which actors are on stage; actor names; material texture
                  transforms
  scene.glb.txt   every model the scene shows (m0, m1, ... in model space, with
                  3DMM's smoothing) and a placeholder per material (mat0, ...)
                  carrying its color or texture, base64
  scene.bin.txt   per frame, per actor on stage, per body part: model and material
                  (int16 pairs), then all the world matrices (float32, BRender
                  4 rows of 3), base64
  scene.mp3.txt   the scene's soundtrack, cut from --video, base64

Everything is read from what 3DMM itself drew, so stock actors, add-on actors
and 3D text all come out the same way. Materials are looked up by chunk number
in the game's content files.
"""
import sys, os, io, json, base64, struct, subprocess, tempfile, zipfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
from actor import Template, smooth_by_groups, part_mesh  # noqa: E402
from bkgd import Bkgd, base_palette  # noqa: E402
from paths import ROOT  # noqa: E402


def read_poses(path):
    if path.endswith('.zip'):
        z = zipfile.ZipFile(path); text = z.read(z.namelist()[0]).decode('latin1')
    else:
        text = open(path, encoding='latin1').read()
    lines = text.splitlines(); i = 0
    models, mats, frames = {}, {}, {}
    cur = None
    while i < len(lines):
        p = lines[i].split(); i += 1
        if not p: continue
        k = p[0]
        if k == 'M':
            mid, nv, nf = int(p[1]), int(p[2]), int(p[3])
            V = np.array([[float(x) for x in lines[i + j].split()] for j in range(nv)]).reshape(-1, 5); i += nv
            Fa = np.array([[int(x) for x in lines[i + j].split()] for j in range(nf)], int).reshape(-1, 4); i += nf
            models[mid] = (V[:, :3], V[:, 3:5], Fa[:, :3], Fa[:, 3])
        elif k == 'T':
            mats[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]))
        elif k == 'F':
            cur = dict(ifrm=int(p[1]), dts=int(p[2]), scene=int(p[3]), bkgd=int(p[4]), cam=int(p[5]), actors=[])
            frames[cur['ifrm']] = cur          # a frame written again replaces the earlier one
        elif k == 'A':
            cur['actors'].append(dict(arid=int(p[1]), sid=int(p[2]), cno=int(p[3]), parts=[]))
        elif k == 'P':
            cur['actors'][-1]['parts'].append((int(p[2]), int(p[3]), [float(x) for x in p[4:16]]))
    return models, mats, [frames[k] for k in sorted(frames)]


class Content(Template):
    """material lookups in one content file (Template's, without a template)"""
    def __init__(s, path):
        s.B = Bkgd(path); s.pal = base_palette()
        s.cnos = {k[1] for k in s.B.c.chunks if k[0] == 'MTRL'}


def export(poses, scene_no, out, video=None, name=None):
    models, mats, frames = read_poses(poses)
    iscen = scene_no - 1
    sel = [f for f in frames if f['scene'] == iscen]
    if not sel: raise SystemExit('no frames in scene %d (the capture has scenes %s)' % (scene_no, sorted({f['scene'] for f in frames})))
    t0 = sel[0]['dts']
    after = [f for f in frames if f['dts'] > sel[-1]['dts'] and f['scene'] != iscen]
    t1 = after[0]['dts'] if after else sel[-1]['dts'] + 1000

    # actors and their names
    tm = Bkgd(os.path.join(ROOT, 'content-files', 'tmpls.3cn'))
    tnames = {k[1]: tm.c.name(*k) for k in tm.c.chunks if k[0] == 'TMPL'}
    actors, aindex = [], {}
    for f in sel:
        for a in f['actors']:
            if a['arid'] not in aindex:
                aindex[a['arid']] = len(actors)
                nm = '3-D text' if a['sid'] == 0 else tnames.get(a['cno'], 'Actor %d' % a['arid'])
                actors.append(dict(arid=a['arid'], name=nm, parts=len(a['parts'])))

    # models and materials the scene uses, renumbered from 0
    mused, tused = {}, {}
    for f in sel:
        for a in f['actors']:
            for m, t, _ in a['parts']:
                if m >= 0 and m not in mused: mused[m] = len(mused)
                if t >= 0 and t not in tused: tused[t] = len(tused)

    import trimesh
    sc = trimesh.Scene()
    plain = trimesh.visual.material.PBRMaterial(baseColorFactor=[1, 1, 1, 1], roughnessFactor=0.85, metallicFactor=0.0)
    for m, k in mused.items():
        V, UV, F, sm = models[m]
        F = np.array([f for f in F if len(set(f)) == 3], int).reshape(-1, 3)
        if len(F) == 0:
            V = np.zeros((3, 3)); UV = np.zeros((3, 2)); F = np.array([[0, 1, 2]]); sm = np.zeros(1, int)
        else:
            sm = np.array([g for f, g in zip(models[m][2], models[m][3]) if len(set(f)) == 3], int)
        N = smooth_by_groups(V, F, sm).reshape(-1, 3)
        P = V[F].reshape(-1, 3); uv = UV[F].reshape(-1, 2)
        vis = trimesh.visual.TextureVisuals(uv=np.c_[uv[:, 0], 1 - uv[:, 1]], material=plain)
        mesh = trimesh.Trimesh(P, np.arange(len(P)).reshape(-1, 3), vertex_normals=N, visual=vis, process=False)
        sc.add_geometry(mesh, geom_name='m%d' % k, node_name='m%d' % k)
    files = [Content(os.path.join(ROOT, 'content-files', f)) for f in ('tmpls.3cn', 'mtrls.3cn')]
    pal = base_palette(); cache = {}; matinfo = []
    for t, k in tused.items():
        cno, base, rng = mats[t]
        src = next((c for c in files if cno in c.cnos), None)
        md = src.material(('MTRL', cno)) if src else dict(ref=('PAL', base, rng), ramp=pal[base:base + max(rng, 1)])
        tri = np.array([[0, -50, 0], [0.01, -50, 0], [0, -49.99, 0]])
        stub = part_mesh(tri, np.zeros((3, 2)), np.array([[0, 1, 2]]), np.zeros(1, int), md, cache)
        sc.add_geometry(stub, geom_name='mat%d' % k, node_name='mat%d' % k)
        matinfo.append(dict(uvxf=[round(float(v), 6) for v in md['uvxf'].ravel()] if 'uvxf' in md else None))

    # the frames
    ids, xf, fmeta = [], [], []
    for f in sel:
        on = []
        for a in f['actors']:
            on.append(aindex[a['arid']])
            for m, t, M in a['parts']:
                ids += [mused.get(m, -1), tused.get(t, -1)]
                xf += M
        fmeta.append(dict(t=f['dts'] - t0, cam=f['cam'], actors=on))
    blob = np.array(ids, '<i2').tobytes()
    blob += b'\0' * (-len(blob) % 4) + np.array(xf, '<f4').tobytes()

    os.makedirs(out, exist_ok=True)
    meta = dict(name=name or 'Scene %d' % scene_no, scene=scene_no, duration=t1 - t0, bkgd=sel[0]['bkgd'],
                actors=actors, mats=matinfo, models=len(mused), frames=fmeta,
                ids_bytes=len(ids) * 2, xf_offset=len(blob) - len(xf) * 4)
    json.dump(meta, open(os.path.join(out, 'scene.json'), 'w'), separators=(',', ':'))
    glb = sc.export(file_type='glb')
    open(os.path.join(out, 'scene.glb.txt'), 'w').write(base64.b64encode(glb).decode())
    open(os.path.join(out, 'scene.bin.txt'), 'w').write(base64.b64encode(blob).decode())
    if video:
        mp3 = os.path.join(tempfile.mkdtemp(), 'scene.mp3')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', '%.3f' % (t0 / 1000), '-t', '%.3f' % ((t1 - t0) / 1000),
                        '-i', video, '-vn', '-ac', '2', '-c:a', 'libmp3lame', '-b:a', '128k', mp3], check=True)
        open(os.path.join(out, 'scene.mp3.txt'), 'w').write(base64.b64encode(open(mp3, 'rb').read()).decode())
    print('%s: %d frames, %.1f s, actors %s, %d models, %d materials -> %s' % (
        meta['name'], len(sel), (t1 - t0) / 1000, [a['name'] for a in actors], len(mused), len(tused), out))
    return meta


if __name__ == '__main__':
    a = sys.argv[1:]
    opts = {}
    for k in ('--video', '--name'):
        if k in a:
            j = a.index(k); opts[k[2:]] = a[j + 1]; del a[j:j + 2]
    export(a[0], int(a[1]), a[2], **opts)
