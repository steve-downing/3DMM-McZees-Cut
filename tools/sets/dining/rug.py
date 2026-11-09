"""The dining room rug's pattern, drawn as a texture.

    python rug.py                 -> data/rug.png

The 1995 rug is a purple field inside a pale, busy border; at that resolution the
pattern is a blur, so this draws an ornate rug in the same colors instead: guard
stripes, a trellis field with small flowers in muted colors, and a quiet border
close to the field in tone: a line of small flowers running round it. Drawn at
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
BORDER_BG = (60, 40, 84); BORDER_LT = (86, 62, 112); CREAM = (110, 88, 126)
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

    # --- the border band (drawn last, over the field's edges): quiet, close to the field in
    # tone: thin guard rules, and a line running round the middle of the band with small
    # flowers spaced evenly along it, one at each corner where the sides meet
    BAND = (70, 34, 86); RULE = (56, 26, 70); LINE = (84, 46, 98); FLOWER = (90, 52, 104); HEART = (104, 76, 82)
    d.rectangle([0, 0, W, b], fill=BAND); d.rectangle([0, H - b, W, H], fill=BAND)
    d.rectangle([0, 0, b, H], fill=BAND); d.rectangle([W - b, 0, W, H], fill=BAND)
    def rule(inset, width, col):
        o = int(inset * s)
        d.rectangle([o, o, W - o, H - o], outline=col, width=max(2, int(width * s)))
    rule(0.0, 0.3, RULE); rule(0.55, 0.06, LINE); rule(BORDER - 0.55, 0.06, LINE); rule(BORDER - 0.25, 0.25, RULE)
    rule(BORDER / 2 - 0.03, 0.06, LINE)
    mid = BORDER / 2 * s
    def flower(fx, fy):
        for q in range(4):
            th = q * math.pi / 2
            ex, ey = fx + math.cos(th) * 0.24 * s, fy + math.sin(th) * 0.24 * s
            d.ellipse([ex - 0.18 * s, ey - 0.18 * s, ex + 0.18 * s, ey + 0.18 * s], fill=FLOWER)
        d.ellipse([fx - 0.1 * s, fy - 0.1 * s, fx + 0.1 * s, fy + 0.1 * s], fill=HEART)
    corners = [(mid, mid), (W - mid, mid), (W - mid, H - mid), (mid, H - mid)]
    for k in range(4):
        (x0, y0), (x1, y1) = corners[k], corners[(k + 1) % 4]
        n = max(1, round(math.hypot(x1 - x0, y1 - y0) / (2.6 * s)))    # whole spacings per side
        for i in range(n):
            flower(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)
    # a little wear: soft mottling so it reads as wool, not print
    img = np.asarray(im).astype(float)
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, (H // 16 + 1, W // 16 + 1))
    noise = np.asarray(Image.fromarray(((noise - noise.min()) / np.ptp(noise) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)).astype(float) / 255
    img *= (0.9 + 0.2 * noise)[..., None]
    # dulled: a third of the way to gray, and a little darker, so it sits under the furniture
    gray = img.mean(-1, keepdims=True)
    img = (img * 0.62 + gray * 0.38) * 0.9
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W // SS, H // SS), Image.LANCZOS)
    im.save(out)
    print('rug', im.size, '->', out)

if __name__ == '__main__':
    main(*sys.argv[1:2])
