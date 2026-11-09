"""The dining room rug's pattern, drawn as a texture.

    python rug.py                 -> data/rug.png

The 1995 rug is a purple field inside a pale, busy border; at that resolution the
pattern is a blur, so this draws an ornate rug in the same colors instead: guard
stripes, a border of rosettes on a scrolling vine, a trellis field with small
flowers, corner spandrels and a lobed central medallion with pendants. Drawn at
twice the size and shrunk, for clean edges."""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))

W_UNITS, H_UNITS, BORDER = 45.3, 34.5, 4.0          # the rug (toon.py RUG), x by z
PX = 34                                             # pixels per unit, final
SS = 2                                              # supersampling

# colors (sRGB), in the room's palette
FIELD = (88, 30, 104); FIELD_DK = (64, 22, 80); FIELD_LT = (112, 52, 126)
BORDER_BG = (52, 46, 82); BORDER_LT = (104, 96, 136); CREAM = (150, 136, 156)
GOLD = (150, 116, 58); DARK = (34, 20, 44); BLUE = (70, 76, 120)

def main(out=os.path.join(HERE, 'data', 'rug.png')):
    W, H = int(W_UNITS * PX * SS), int(H_UNITS * PX * SS)
    s = PX * SS
    im = Image.new('RGB', (W, H), FIELD); d = ImageDraw.Draw(im)
    b = int(BORDER * s)

    # --- field: a diagonal trellis with a small four-petal flower at every node
    step = 2.3 * s
    for i in range(-40, 80):
        x0 = i * step
        d.line([(x0, 0), (x0 + H, H)], fill=FIELD_DK, width=max(2, int(0.07 * s)))
        d.line([(x0, 0), (x0 - H, H)], fill=FIELD_DK, width=max(2, int(0.07 * s)))
    for i in range(-40, 80):
        for j in range(0, int(2 * H / step) + 2):
            cy = j * step / 2
            cx = i * step + (j % 2) * step / 2
            r = 0.22 * s
            for a in range(4):
                t = a * math.pi / 2
                d.ellipse([cx + math.cos(t) * r - r * 0.6, cy + math.sin(t) * r - r * 0.6, cx + math.cos(t) * r + r * 0.6, cy + math.sin(t) * r + r * 0.6], fill=FIELD_LT)
            d.ellipse([cx - r * 0.45, cy - r * 0.45, cx + r * 0.45, cy + r * 0.45], fill=GOLD)

    # --- central medallion: lobed star, rings, pendants along the long axis
    cx, cy = W / 2, H / 2
    def star(r_out, r_in, n, fill, rot=0.0, sx=1.25):
        pts = []
        for k in range(2 * n):
            r = r_out if k % 2 == 0 else r_in
            t = rot + k * math.pi / n
            pts.append((cx + math.cos(t) * r * sx, cy + math.sin(t) * r))
        d.polygon(pts, fill=fill)
    for x in (-1, 1):   # pendants
        px = cx + x * 8.6 * s
        # a pendant: a lobed drop pointing out from the medallion, a finial bud at its tip
        d.polygon([(px - x * 2.2 * s, cy - 1.3 * s), (px + x * 0.4 * s, cy - 0.55 * s), (px + x * 1.6 * s, cy), (px + x * 0.4 * s, cy + 0.55 * s), (px - x * 2.2 * s, cy + 1.3 * s)], fill=BORDER_BG)
        d.polygon([(px - x * 1.6 * s, cy - 0.75 * s), (px + x * 0.3 * s, cy - 0.3 * s), (px + x * 1.0 * s, cy), (px + x * 0.3 * s, cy + 0.3 * s), (px - x * 1.6 * s, cy + 0.75 * s)], fill=BORDER_LT)
        d.ellipse([px + x * 1.6 * s - 0.4 * s, cy - 0.4 * s, px + x * 1.6 * s + 0.4 * s, cy + 0.4 * s], fill=GOLD)
    star(6.6 * s, 5.4 * s, 16, DARK)
    star(6.2 * s, 5.1 * s, 16, BORDER_BG)
    d.ellipse([cx - 5.0 * s * 1.25, cy - 5.0 * s, cx + 5.0 * s * 1.25, cy + 5.0 * s], outline=GOLD, width=int(0.12 * s))
    star(4.6 * s, 3.4 * s, 8, BORDER_LT, rot=math.pi / 8)
    star(3.8 * s, 2.9 * s, 8, FIELD_DK, rot=math.pi / 8)
    d.ellipse([cx - 2.6 * s * 1.25, cy - 2.6 * s, cx + 2.6 * s * 1.25, cy + 2.6 * s], fill=CREAM)
    star(2.2 * s, 1.1 * s, 8, FIELD, rot=0)
    d.ellipse([cx - 0.7 * s, cy - 0.7 * s, cx + 0.7 * s, cy + 0.7 * s], fill=GOLD)
    for k in range(8):   # petals round the middle ring
        t = k * math.pi / 4 + math.pi / 8
        ex, ey = cx + math.cos(t) * 3.9 * s * 1.25, cy + math.sin(t) * 3.9 * s
        d.ellipse([ex - 0.35 * s, ey - 0.35 * s, ex + 0.35 * s, ey + 0.35 * s], fill=CREAM)

    # --- corner spandrels: quarter medallions in the field's corners
    for (qx, qy) in ((b, b), (W - b, b), (b, H - b), (W - b, H - b)):
        for r, col in ((4.6, FIELD_DK), (4.3, BORDER_BG), (3.3, FIELD_LT), (2.9, FIELD_DK), (1.6, BORDER_LT)):
            d.ellipse([qx - r * s, qy - r * s, qx + r * s, qy + r * s], fill=col)
        for k in range(12):
            t = k * math.pi / 6
            ex, ey = qx + math.cos(t) * 3.8 * s, qy + math.sin(t) * 3.8 * s
            d.ellipse([ex - 0.22 * s, ey - 0.22 * s, ex + 0.22 * s, ey + 0.22 * s], fill=GOLD)

    # --- the border band (drawn last, over the field's edges)
    d.rectangle([0, 0, W, b], fill=BORDER_BG); d.rectangle([0, H - b, W, H], fill=BORDER_BG)
    d.rectangle([0, 0, b, H], fill=BORDER_BG); d.rectangle([W - b, 0, W, H], fill=BORDER_BG)
    # guard stripes: outer and inner, each a dark rule, a gold rule and a row of dots
    def guards(inset, width):
        o = int(inset * s)
        d.rectangle([o, o, W - o, H - o], outline=DARK, width=int(width * s))
    guards(0.0, 0.32); guards(0.32, 0.1)
    guards(BORDER - 0.42, 0.1); guards(BORDER - 0.32, 0.32)
    gold = lambda inset: d.rectangle([int(inset * s)] * 2 + [W - int(inset * s), H - int(inset * s)], outline=GOLD, width=max(2, int(0.08 * s)))
    gold(0.62); gold(BORDER - 0.62)
    def dots_along(inset, spacing, r, col):
        o = inset * s
        for (x0, y0, x1, y1) in ((o, o, W - o, o), (o, H - o, W - o, H - o), (o, o, o, H - o), (W - o, o, W - o, H - o)):
            n = int(max(abs(x1 - x0), abs(y1 - y0)) / (spacing * s))
            for k in range(n + 1):
                t = k / max(n, 1); x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                d.ellipse([x - r * s, y - r * s, x + r * s, y + r * s], fill=col)
    dots_along(0.45, 0.55, 0.09, CREAM); dots_along(BORDER - 0.45, 0.55, 0.09, CREAM)
    # main band: a scrolling vine with leaves, rosettes in its loops
    mid = BORDER / 2
    def band_path(t_len):
        # walk round the band's centerline: returns points and inward normals
        o = mid * s; P = []
        for (x0, y0, x1, y1, nx, ny) in ((o, o, W - o, o, 0, 1), (W - o, o, W - o, H - o, -1, 0), (W - o, H - o, o, H - o, 0, -1), (o, H - o, o, o, 1, 0)):
            L = math.hypot(x1 - x0, y1 - y0); n = int(L / (0.08 * s))
            for k in range(n):
                t = k / n; P.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, nx, ny))
        return P
    P = band_path(0); amp = 0.85 * s; period = 3.6 * s
    vine = []
    acc = 0.0
    for k, (x, y, nx, ny) in enumerate(P):
        if k: acc += math.hypot(x - P[k - 1][0], y - P[k - 1][1])
        w = math.sin(acc / period * 2 * math.pi)
        vine.append((x + nx * w * amp, y + ny * w * amp, acc, nx, ny))
    d.line([(v[0], v[1]) for v in vine], fill=GOLD, width=int(0.14 * s))
    for k in range(0, len(vine), 3):   # leaves along the vine
        x, y, a, nx, ny = vine[k]
        if int(a / (period / 4)) % 2: continue
    last = -1e9
    for k, (x, y, a, nx, ny) in enumerate(vine):
        phase = (a / period) % 1.0
        if abs(phase - 0.25) < 0.01 and a - last > period * 0.4 or abs(phase - 0.75) < 0.01 and a - last > period * 0.4:
            last = a
            side = 1 if phase < 0.5 else -1
            rx, ry = P[k][0] - nx * side * 0.6 * s, P[k][1] - ny * side * 0.6 * s   # rosette in the loop
            for rr, col in ((0.95, CREAM), (0.7, BORDER_LT), (0.42, FIELD), (0.18, GOLD)):
                d.ellipse([rx - rr * s, ry - rr * s, rx + rr * s, ry + rr * s], fill=col)
            for q in range(6):
                t = q * math.pi / 3
                ex, ey = rx + math.cos(t) * 0.95 * s, ry + math.sin(t) * 0.95 * s
                d.ellipse([ex - 0.22 * s, ey - 0.22 * s, ex + 0.22 * s, ey + 0.22 * s], fill=CREAM)
            # a leaf on the vine opposite the rosette
            lx, ly = x + nx * side * 0.35 * s, y + ny * side * 0.35 * s
            d.ellipse([lx - 0.38 * s, ly - 0.2 * s, lx + 0.38 * s, ly + 0.2 * s] if nx == 0 else [lx - 0.2 * s, ly - 0.38 * s, lx + 0.2 * s, ly + 0.38 * s], fill=BLUE)
    # corner squares of the border: a rosette each
    for (qx, qy) in ((mid * s, mid * s), (W - mid * s, mid * s), (mid * s, H - mid * s), (W - mid * s, H - mid * s)):
        for rr, col in ((1.5, DARK), (1.3, CREAM), (0.95, BORDER_BG), (0.55, GOLD)):
            d.ellipse([qx - rr * s, qy - rr * s, qx + rr * s, qy + rr * s], fill=col)
    # a little wear: soft mottling so it reads as wool, not print
    img = np.asarray(im).astype(float)
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, (H // 16 + 1, W // 16 + 1))
    noise = np.asarray(Image.fromarray(((noise - noise.min()) / np.ptp(noise) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)).astype(float) / 255
    img *= (0.9 + 0.2 * noise)[..., None]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W // SS, H // SS), Image.LANCZOS)
    im.save(out)
    print('rug', im.size, '->', out)

if __name__ == '__main__':
    main(*sys.argv[1:2])
