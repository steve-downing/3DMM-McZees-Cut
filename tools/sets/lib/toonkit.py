"""Toolkit for the cartoon set rebuilds: flat-colored, low-poly geometry with a
surface kind per face (read by viewer/surface.js), smooth normals across gentle
bends, and helpers for the shapes these sets keep needing. See ../STYLE.md."""
import colorsys
import numpy as np
import trimesh
import mapbox_earcut as earcut

CARTOON = 0.10   # how far colors lean toward the cartoon palette (0 = original, 1 = cartoon)

# surface kinds (vertex-color alpha) understood by viewer/surface.js
PLAIN, FABRIC, CARPET, WOOD, METAL, HAMMERED = range(6)
def toon(rgb):
    """brighter, more saturated version of an original color"""
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, s * 1.25 + 0.04); v = min(1.0, 0.5 + 0.62 * v)
    return np.array(colorsys.hsv_to_rgb(h, s, v)) * 255

def hexc(h): return np.array([int(h[i:i+2], 16) for i in (1, 3, 5)], float)

def tri_poly(poly):
    """earcut a shapely polygon (with holes); returns 2D vertices and triangles"""
    rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in poly.interiors]
    verts = np.vstack(rings); ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    return verts, earcut.triangulate_float64(verts, ends).reshape(-1, 3)

def rrect(s0, s1, zc_, zh, r, n=5):
    """rounded rectangle outline in (s, z)"""
    pts = []
    for cs, cz, a0 in ((s1 - r, zc_ + zh - r, 0), (s0 + r, zc_ + zh - r, 90), (s0 + r, zc_ - zh + r, 180), (s1 - r, zc_ - zh + r, 270)):
        pts += [(cs + r * np.cos(a), cz + r * np.sin(a)) for a in np.radians(np.linspace(a0, a0 + 90, n))]
    return pts

def smooth_normals(T, crease_deg=40.0):
    """per-corner normals: average the faces meeting at a point whose normals are within the
    crease angle, so rounded parts shade smoothly and real edges stay sharp"""
    fn = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); ar = np.linalg.norm(fn, axis=1)
    fu = fn / np.maximum(ar, 1e-12)[:, None]
    P = T.reshape(-1, 3); cf = np.repeat(np.arange(len(T)), 3)
    _, grp = np.unique(np.round(P / 1e-4).astype(np.int64), axis=0, return_inverse=True)
    grp = grp.ravel(); order = np.argsort(grp, kind='stable'); bounds = np.flatnonzero(np.diff(grp[order])) + 1
    out = np.repeat(fu, 3, axis=0).copy(); cosc = np.cos(np.radians(crease_deg))
    for idx in np.split(order, bounds):
        if len(idx) < 2: continue
        f = cf[idx]; U = fu[f]; Wt = fn[f]
        M = (U @ U.T) > cosc
        S = M.astype(float) @ Wt
        out[idx] = S / np.maximum(np.linalg.norm(S, axis=1), 1e-12)[:, None]
    return out

class Builder:
    """triangles with one flat color each, in groups (lit / glow)"""
    def __init__(self): self.g = {}
    def add(self, V, F, color, group='lit', kind=0):
        V = np.asarray(V, float); F = np.asarray(F, int)
        tri = V[F]
        e = self.g.setdefault(group, ([], [], []))
        e[0].append(tri); e[1].append(np.repeat(np.asarray(color, float)[None], len(F), 0)); e[2].append(np.full(len(F), kind))
    def add_mesh(self, m, color, group='lit', kind=0): self.add(m.vertices, m.faces, color, group, kind)
    def meshes(self):
        out = {}
        for k, (tris, cols, kinds) in self.g.items():
            T = np.concatenate(tris); C = np.concatenate(cols) / 255.0; Kd = np.concatenate(kinds)
            C = np.where(C <= 0.04045, C / 12.92, ((C + 0.055) / 1.055) ** 2.4)          # linear for glTF
            V = T.reshape(-1, 3); F = np.arange(len(V)).reshape(-1, 3)
            N = smooth_normals(T)
            # alpha carries the surface kind for the viewer's shader: 0 plain, 1 fabric, 2 carpet, 3 wood, 4 metal
            vc = np.repeat(np.c_[np.round(C * 255), 16 + 32 * Kd].astype(np.uint8), 3, axis=0)
            m = trimesh.Trimesh(V, F, vertex_normals=N, process=False); m.visual = trimesh.visual.ColorVisuals(m, vertex_colors=vc)
            out[k] = m
        return out

def hull(points):
    return trimesh.convex.convex_hull(np.asarray(points, float))

def cbox(x0, x1, y0, y1, z0, z1, r=0.12):
    """box with chamfered edges"""
    pts = []
    for x in (x0, x1):
        for y in (y0, y1):
            for z in (z0, z1):
                sx = 1 if x == x0 else -1; sy = 1 if y == y0 else -1; sz = 1 if z == z0 else -1
                pts += [(x + sx * r, y, z), (x, y + sy * r, z), (x, y, z + sz * r)]
    return hull(pts)

def prism(cx, cz, rad, y0, y1, n=6):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = [(cx + rad * np.cos(t), y, cz + rad * np.sin(t)) for y in (y0, y1) for t in a]
    return hull(pts)

def slab_with_holes(outline, holes, y0, y1, bevel=0.1):
    """horizontal slab from a 2-D outline (x, z) with through-holes; beveled top edge"""
    outline = np.asarray(outline, float); holes = [np.asarray(h, float) for h in holes]
    c = outline.mean(0)
    inset = c + (outline - c) * (1 - bevel / np.max(np.abs(outline - c), axis=0).mean())
    V = []; F = []
    def ring_faces(r0, ya, r1, yb):
        n = len(r0); base = len(V)
        for p in r0: V.append((p[0], ya, p[1]))
        for p in r1: V.append((p[0], yb, p[1]))
        for i in range(n):
            j = (i + 1) % n
            F.append((base + i, base + j, base + n + j)); F.append((base + i, base + n + j, base + n + i))
    def cap(ring, hs, y):
        verts = np.vstack([ring] + hs); ends = np.cumsum([len(ring)] + [len(h) for h in hs]).astype(np.uint32)
        T = earcut.triangulate_float64(verts, ends).reshape(-1, 3); base = len(V)
        for p in verts: V.append((p[0], y, p[1]))
        for t in T: F.append(tuple(base + t))
    ring_faces(outline, y0, outline, y1 - bevel)
    ring_faces(outline, y1 - bevel, inset, y1)
    cap(inset, holes, y1); cap(outline, holes, y0)
    for h in holes: ring_faces(h, y0, h, y1)
    return np.array(V), np.array(F)

def circle(cx, cz, r, n=12):
    return [(cx + r * np.cos(t), cz + r * np.sin(t)) for t in np.linspace(0, 2 * np.pi, n, endpoint=False)]

def rounded_rect(x0, x1, z0, z1, r, n=3):
    pts = []
    for (cx, cz, a0) in ((x1 - r, z1 - r, 0), (x0 + r, z1 - r, 90), (x0 + r, z0 + r, 180), (x1 - r, z0 + r, 270)):
        for a in np.radians(np.linspace(a0, a0 + 90, n + 1)):
            pts.append((cx + r * np.cos(a), cz + r * np.sin(a)))
    return pts

def disk(center, normal, rad, n=10, lift=0.02):
    normal = np.asarray(normal, float) / np.linalg.norm(normal)
    u = np.cross(normal, [0, 1, 0] if abs(normal[1]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(normal, u)
    c = np.asarray(center, float) + normal * lift
    ring = [c + rad * (np.cos(t) * u + np.sin(t) * v) for t in np.linspace(0, 2 * np.pi, n, endpoint=False)]
    V = np.vstack([c, ring]); F = [[0, 1 + i, 1 + (i + 1) % n] for i in range(n)]
    return V, F


def half(cartoon, original):
    c = hexc(cartoon) if isinstance(cartoon, str) else np.asarray(cartoon, float)
    return CARTOON * c + (1 - CARTOON) * np.array(original, float)

# cartoon color and original color (measured from the 1995 renders), averaged

def bezier(p0, p1, p2, n=6):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * np.array(p0) + 2 * (1 - t) * t * np.array(p1) + t ** 2 * np.array(p2)

def offset_polygon(P, d):
    """move each vertex inward by d along the averaged edge normals (CCW polygon)"""
    n = len(P); out = []
    for i in range(n):
        a, b_, c = P[i - 1], P[i], P[(i + 1) % n]
        e1 = b_ - a; e2 = c - b_
        n1 = np.array([-e1[1], e1[0]]) / (np.linalg.norm(e1) + 1e-12); n2 = np.array([-e2[1], e2[0]]) / (np.linalg.norm(e2) + 1e-12)
        m = n1 + n2; m /= (np.linalg.norm(m) + 1e-12)
        out.append(b_ + m * d / max(np.dot(m, n1), 0.3))
    return np.array(out)

def reclined_extrusion(outline, ylo, yhi, zb_lo, zb_hi, thick, bevel, bulge=None):
    """extrude a front-view outline (x, y) toward +z, leaning back with height; bevel the front edge.
    bulge(y), if given, pushes the front face forward (a headrest standing proud)"""
    P = np.asarray(outline, float)
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    if area < 0: P = P[::-1]
    I = offset_polygon(P, bevel)
    zb = lambda y: zb_lo + (zb_hi - zb_lo) * (y - ylo) / (yhi - ylo)
    V = []; F = []
    def ring(R_, dz):
        base = len(V)
        for x, y in R_: V.append((x, y, zb(y) + dz + (bulge(y) if bulge and dz > 0 else 0.0)))
        return base
    r0 = ring(P, 0.0); r1 = ring(P, thick - bevel); r2 = ring(I, thick)
    n = len(P)
    for i in range(n):
        j = (i + 1) % n
        F += [(r0 + i, r0 + j, r1 + j), (r0 + i, r1 + j, r1 + i), (r1 + i, r1 + j, r2 + j), (r1 + i, r2 + j, r2 + i)]
    for R_, base in ((P, r0), (I, r2)):
        T = earcut.triangulate_float64(np.asarray(R_, float), np.array([len(R_)], np.uint32)).reshape(-1, 3)
        F += [tuple(base + t) for t in T]
    return np.array(V), np.array(F)

def split_x(V, F, tag, planes, axis=0):
    """cut triangles along the planes x = c (or y = c with axis=1), so colors and bends can change exactly there"""
    V = [tuple(v) for v in V]; F = [tuple(f) for f in F]; tag = list(tag)
    for c in planes:
        nf, nt = [], []
        for f, t in zip(F, tag):
            d = [V[k][axis] - c for k in f]
            d = [0.0 if abs(x) < 1e-7 else x for x in d]
            if all(x >= 0 for x in d) or all(x <= 0 for x in d): nf.append(f); nt.append(t); continue
            def cut(a, b_):
                pa, pb = np.array(V[f[a]]), np.array(V[f[b_]]); u = d[a] / (d[a] - d[b_])
                V.append(tuple(pa + u * (pb - pa))); return len(V) - 1
            if 0.0 in d:                                       # one vertex on the plane: two triangles
                z = d.index(0.0); a, b_ = (z + 1) % 3, (z + 2) % 3; m = cut(a, b_)
                nf += [(f[z], f[a], m), (f[z], m, f[b_])]; nt += [t, t]; continue
            for lone in range(3):                              # one vertex alone: three triangles
                a, b_ = (lone + 1) % 3, (lone + 2) % 3
                if (d[lone] > 0) != (d[a] > 0) and (d[lone] > 0) != (d[b_] > 0): break
            m1 = cut(lone, a); m2 = cut(lone, b_)
            nf += [(f[lone], m1, m2), (m1, f[a], f[b_]), (m1, f[b_], m2)]; nt += [t, t, t]
        F, tag = nf, nt
    return np.array(V), np.array(F), np.array(tag)

def surface_relief(poly, zfun, dz0, dz1):
    """a flat shape (x, y) laid on a surface z = zfun(y), from zfun + dz0 to zfun + dz1"""
    P = np.asarray(poly, float); n = len(P)
    V = [(x, y, zfun(y) + dz0) for x, y in P] + [(x, y, zfun(y) + dz1) for x, y in P]
    F = []
    for i in range(n):
        j = (i + 1) % n; F += [(i, j, n + j), (i, n + j, n + i)]
    T = earcut.triangulate_float64(P, np.array([n], np.uint32)).reshape(-1, 3)
    F += [tuple(t) for t in T] + [tuple(n + t) for t in T]
    return np.array(V), np.array(F)

def wrap_strips(b, path, strips):
    """bands that follow a cushion's side profile (y, z) over the top and down the front.
    strips: (x0, x1, lift0, lift1, color, kind)"""
    P = np.asarray(path, float); T = np.gradient(P, axis=0); N = np.c_[T[:, 1], -T[:, 0]]
    N /= np.linalg.norm(N, axis=1)[:, None]
    for x0, x1, d0, d1, color, kind in strips:
        for k in range(len(P) - 1):
            pts = [(x, *(P[j] + N[j] * dd)) for j in (k, k + 1) for dd in (d0, d1) for x in (x0, x1)]
            b.add_mesh(hull(pts), color, kind=kind)

def dp(p, eps):
    if len(p) < 3: return p
    a, bb = p[0], p[-1]; ab = bb - a; L = np.linalg.norm(ab) + 1e-12
    dist = np.abs(ab[0] * (p[:, 1] - a[1]) - ab[1] * (p[:, 0] - a[0])) / L
    i = np.argmax(dist)
    if dist[i] > eps: return np.vstack([dp(p[:i + 1], eps)[:-1], dp(p[i:], eps)])
    return np.vstack([a, bb])

