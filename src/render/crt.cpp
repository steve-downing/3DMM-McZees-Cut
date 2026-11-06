/***************************************************************************
    3dmm-crt: CRT look for 3dmm-render output.

    Reads a render folder (timeline.ffconcat and the frames folder), turns each
    distinct frame into a 4K CRT image once, and writes constant-frame-rate
    raw video to stdout for ffmpeg:

        3dmm-crt <renderdir> [options] | ffmpeg -f rawvideo -pix_fmt rgb24 -s 3840x2160 -r 30 -i - ...

    The picture is scaled by a whole number (6x by default, so 544x306
    becomes 3264x1836) and centered in the output frame. Each source line
    is drawn as an electron beam whose width grows with brightness (bright
    lines fill in, dark lines leave visible gaps), the result is viewed
    through a phosphor mask, a little glow is added around bright areas,
    and brightness is boosted back up to make up for what the mask and the
    gaps take away. CRT effects are 2-D only: for a stereo render this uses
    the plain 2-D view the renderer keeps alongside the two eyes.

    Options:
        --preset pc|trinitron|tv|hdr   starting point (default pc)
        --mask shadow|grille|slot|none
        --scanlines <0..1>   strength of the gaps between lines
        --glow <0..1>
        --curvature <0..0.25>
        --scale <n>          integer scale (default 6)
        --width/--height     output frame (default 3840x2160)
        --fps <n>            output frame rate (default 30)
        --max-frames <n>     stop early (for previews)
        --info               print "width height pix_fmt fps" and exit
        --frame <n> <out.bmp>  write one processed frame as a BMP and exit

    Presets:
        pc         mid-90s PC monitor: fine shadow mask, light scanlines,
                   mild glow, flat (the default)
        trinitron  aperture grille, a bit more scanline, slight curvature
        tv         consumer TV: slot mask, heavy scanlines, soft focus,
                   curvature
        hdr        pc, written as 10-bit HDR10 (BT.2020 PQ) so the mask's
                   lost light is made up with real brightness, not boost
***************************************************************************/
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>
#include <algorithm>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

struct Image
{
    int w = 0, h = 0;
    std::vector<unsigned char> rgb; // top-down RGB
};

struct Settings
{
    std::string mask = "shadow";
    double scanlines = 0.5; // 0 = beams always fill the line, 1 = thin beams
    double glow = 0.12;
    double curvature = 0.0;
    double softness = 0.30; // horizontal beam spread, in source pixels
    double maskStrength = 0.45;
    bool hdr = false;
    double hdrPaperNits = 203; // SDR white
    double hdrPeakNits = 1000;
    int scale = 6;
    int outW = 3840, outH = 2160;
    int fps = 30;
};

static bool ReadBmp(const std::string &path, Image &img)
{
    FILE *f = fopen(path.c_str(), "rb");
    if (!f)
        return false;
    unsigned char hdr[54];
    if (fread(hdr, 1, 54, f) != 54 || hdr[0] != 'B' || hdr[1] != 'M')
    {
        fclose(f);
        return false;
    }
    int off, w, h;
    short bpp;
    memcpy(&off, hdr + 10, 4);
    memcpy(&w, hdr + 18, 4);
    memcpy(&h, hdr + 22, 4);
    memcpy(&bpp, hdr + 28, 2);
    if (bpp != 24)
    {
        fclose(f);
        return false;
    }
    bool bottomUp = h > 0;
    h = std::abs(h);
    int row = (w * 3 + 3) & ~3;
    std::vector<unsigned char> buf((size_t)row * h);
    fseek(f, off, SEEK_SET);
    size_t got = fread(buf.data(), 1, buf.size(), f);
    fclose(f);
    if (got != buf.size())
        return false;
    img.w = w;
    img.h = h;
    img.rgb.resize((size_t)w * h * 3);
    for (int y = 0; y < h; y++)
    {
        const unsigned char *s = buf.data() + (size_t)(bottomUp ? h - 1 - y : y) * row;
        unsigned char *d = img.rgb.data() + (size_t)y * w * 3;
        for (int x = 0; x < w; x++)
        {
            d[x * 3 + 0] = s[x * 3 + 2];
            d[x * 3 + 1] = s[x * 3 + 1];
            d[x * 3 + 2] = s[x * 3 + 0];
        }
    }
    return true;
}

static bool WriteBmp(const std::string &path, const unsigned char *rgb, int w, int h)
{
    FILE *f = fopen(path.c_str(), "wb");
    if (!f)
        return false;
    int row = (w * 3 + 3) & ~3;
    unsigned char hdr[54] = {0};
    int size = 54 + row * h, off = 54, dib = 40, img = row * h;
    short planes = 1, bpp = 24;
    hdr[0] = 'B';
    hdr[1] = 'M';
    memcpy(hdr + 2, &size, 4);
    memcpy(hdr + 10, &off, 4);
    memcpy(hdr + 14, &dib, 4);
    memcpy(hdr + 18, &w, 4);
    memcpy(hdr + 22, &h, 4);
    memcpy(hdr + 26, &planes, 2);
    memcpy(hdr + 28, &bpp, 2);
    memcpy(hdr + 34, &img, 4);
    fwrite(hdr, 1, 54, f);
    std::vector<unsigned char> line(row, 0);
    for (int y = h - 1; y >= 0; y--)
    {
        const unsigned char *s = rgb + (size_t)y * w * 3;
        for (int x = 0; x < w; x++)
        {
            line[x * 3 + 0] = s[x * 3 + 2];
            line[x * 3 + 1] = s[x * 3 + 1];
            line[x * 3 + 2] = s[x * 3 + 0];
        }
        fwrite(line.data(), 1, row, f);
    }
    fclose(f);
    return true;
}

/***************************************************************************
    Timeline: which frame file is on screen when.
***************************************************************************/
struct Entry
{
    std::string file;
    double start, duration;
};

static bool ReadTimeline(const std::string &dir, std::vector<Entry> &entries)
{
    FILE *f = fopen((dir + "/timeline.ffconcat").c_str(), "r");
    if (!f)
        return false;
    char line[1024];
    double t = 0;
    while (fgets(line, sizeof(line), f))
    {
        if (0 == strncmp(line, "file '", 6))
        {
            char *q = strrchr(line + 6, '\'');
            if (!q)
                continue;
            *q = 0;
            entries.push_back({line + 6, t, 0});
        }
        else if (0 == strncmp(line, "duration ", 9) && !entries.empty())
        {
            entries.back().duration = atof(line + 9);
            t += entries.back().duration;
        }
    }
    fclose(f);
    // the final repeated entry has no duration; drop it
    while (!entries.empty() && entries.back().duration <= 0)
        entries.pop_back();
    return !entries.empty();
}

/***************************************************************************
    The CRT model.
***************************************************************************/
class Crt
{
  public:
    Settings s;
    int srcW = 0, srcH = 0; // one eye
    int picW = 0, picH = 0; // scaled picture inside the output frame
    int x0 = 0, y0 = 0;
    std::vector<float> toLinear; // 256 entries
    std::vector<float> hrows;    // srcH x picW x 3, horizontally filtered linear light
    std::vector<float> glowImg;  // srcH x srcW x 3, blurred linear light
    std::vector<float> maskTile; // tile of per-channel mask weights
    int maskW = 1, maskH = 1;
    double brightnessComp = 1;

    void Setup(int w, int h)
    {
        srcW = w;
        srcH = h;
        int scale = s.scale;
        while (scale > 1 && (w * scale > s.outW || h * scale > s.outH))
            scale--;
        picW = w * scale;
        picH = h * scale;
        x0 = (s.outW - picW) / 2;
        y0 = (s.outH - picH) / 2;
        s.scale = scale;
        toLinear.resize(256);
        for (int i = 0; i < 256; i++)
            toLinear[i] = (float)std::pow(i / 255.0, 2.2);
        BuildMask();
        // what the mask and the beam gaps cost on a flat white field
        double maskMean = 0;
        for (float m : maskTile)
            maskMean += m;
        maskMean /= maskTile.size();
        double beamMean = 0;
        for (int k = 0; k < scale; k++)
        {
            double d = (k + 0.5) / scale - 0.5;
            beamMean += Beam(d, 1.0) + Beam(d - 1, 1.0) + Beam(d + 1, 1.0);
        }
        beamMean /= scale;
        brightnessComp = 1.0 / (maskMean * beamMean);
        if (s.hdr)
            brightnessComp = 1.0 / beamMean; // the mask's loss is made up by HDR headroom instead
    }

    // phosphor mask, at output-pixel resolution
    void BuildMask()
    {
        double lo = 1.0 - s.maskStrength;
        auto set = [&](int x, int y, int ch) {
            for (int c = 0; c < 3; c++)
                maskTile[(y * maskW + x) * 3 + c] = (float)(c == ch ? 1.0 : lo);
        };
        if (s.mask == "none")
        {
            maskW = maskH = 1;
            maskTile.assign(3, 1.0f);
        }
        else if (s.mask == "grille")
        {
            // aperture grille: continuous vertical R, G, B stripes
            maskW = 3;
            maskH = 1;
            maskTile.assign(maskW * maskH * 3, 0);
            for (int x = 0; x < 3; x++)
                set(x, 0, x);
        }
        else if (s.mask == "slot")
        {
            // slot mask: RGB columns broken into slots, staggered by column triad
            maskW = 6;
            maskH = 4;
            maskTile.assign(maskW * maskH * 3, 0);
            for (int y = 0; y < maskH; y++)
            {
                for (int x = 0; x < maskW; x++)
                {
                    int triad = x / 3;
                    bool gap = (y == (triad == 0 ? 3 : 1));
                    if (gap)
                        for (int c = 0; c < 3; c++)
                            maskTile[(y * maskW + x) * 3 + c] = (float)lo;
                    else
                        set(x, y, x % 3);
                }
            }
        }
        else
        {
            // shadow mask: dot triads, alternate rows shifted (a delta
            // pattern, which reads as dot triads at 4K)
            maskW = 3;
            maskH = 2;
            maskTile.assign(maskW * maskH * 3, 0);
            for (int x = 0; x < maskW; x++)
            {
                set(x, 0, x);
                set(x, 1, (x + 2) % 3);
            }
        }
    }

    // beam profile across the scanline: d in source lines from the line center
    double Beam(double d, double brightness) const
    {
        // sigma grows with brightness; scanlines=0 -> always wide
        double thin = 0.18 + 0.30 * (1.0 - s.scanlines);
        double wide = 0.42 + 0.10 * (1.0 - s.scanlines);
        double sigma = thin + (wide - thin) * std::max(0.0, std::min(1.0, brightness));
        return std::exp(-0.5 * (d / sigma) * (d / sigma));
    }

    void Prepare(const Image &frame, int xOffset)
    {
        // horizontal pass: each source line resampled to the picture width
        // with a gaussian beam spread
        hrows.assign((size_t)srcH * picW * 3, 0);
        int scale = s.scale;
        std::vector<float> wts;
        std::vector<int> base(picW);
        const int taps = 3;
        wts.resize((size_t)picW * taps);
        for (int x = 0; x < picW; x++)
        {
            double u = (x + 0.5) / scale - 0.5;
            int c = (int)std::floor(u);
            base[x] = c - 1;
            double sum = 0;
            for (int t = 0; t < taps; t++)
            {
                double d = (c - 1 + t) - u;
                double w = std::exp(-0.5 * (d / s.softness) * (d / s.softness));
                wts[(size_t)x * taps + t] = (float)w;
                sum += w;
            }
            for (int t = 0; t < taps; t++)
                wts[(size_t)x * taps + t] /= (float)sum;
        }
        for (int y = 0; y < srcH; y++)
        {
            const unsigned char *src = frame.rgb.data() + ((size_t)y * frame.w + xOffset) * 3;
            float *dst = hrows.data() + (size_t)y * picW * 3;
            for (int x = 0; x < picW; x++)
            {
                float r = 0, g = 0, b = 0;
                for (int t = 0; t < taps; t++)
                {
                    int sx = std::max(0, std::min(srcW - 1, base[x] + t));
                    float w = wts[(size_t)x * taps + t];
                    r += w * toLinear[src[sx * 3 + 0]];
                    g += w * toLinear[src[sx * 3 + 1]];
                    b += w * toLinear[src[sx * 3 + 2]];
                }
                dst[x * 3 + 0] = r;
                dst[x * 3 + 1] = g;
                dst[x * 3 + 2] = b;
            }
        }
        // glow: wide blur of the source, in linear light
        glowImg.assign((size_t)srcW * srcH * 3, 0);
        if (s.glow > 0)
        {
            std::vector<float> tmp((size_t)srcW * srcH * 3);
            const int rad = 4;
            float k[2 * rad + 1], ks = 0;
            for (int i = -rad; i <= rad; i++)
                ks += (k[i + rad] = (float)std::exp(-0.5 * (i / 1.8) * (i / 1.8)));
            for (int i = 0; i < 2 * rad + 1; i++)
                k[i] /= ks;
            for (int y = 0; y < srcH; y++)
                for (int x = 0; x < srcW; x++)
                    for (int c = 0; c < 3; c++)
                    {
                        float a = 0;
                        for (int i = -rad; i <= rad; i++)
                        {
                            int sx = std::max(0, std::min(srcW - 1, x + i));
                            a += k[i + rad] * toLinear[frame.rgb[((size_t)y * frame.w + xOffset + sx) * 3 + c]];
                        }
                        tmp[((size_t)y * srcW + x) * 3 + c] = a;
                    }
            for (int y = 0; y < srcH; y++)
                for (int x = 0; x < srcW; x++)
                    for (int c = 0; c < 3; c++)
                    {
                        float a = 0;
                        for (int i = -rad; i <= rad; i++)
                        {
                            int sy = std::max(0, std::min(srcH - 1, y + i));
                            a += k[i + rad] * tmp[((size_t)sy * srcW + x) * 3 + c];
                        }
                        glowImg[((size_t)y * srcW + x) * 3 + c] = a;
                    }
        }
    }

    // map an output pixel (inside the picture) to source coordinates,
    // with optional barrel curvature; false if it falls off the tube
    bool MapToSource(double px, double py, double &u, double &v, double &edge) const
    {
        double nx = (px + 0.5) / picW * 2 - 1;
        double ny = (py + 0.5) / picH * 2 - 1;
        edge = 1;
        if (s.curvature > 0)
        {
            double aspect = (double)picW / picH;
            double cx = nx * aspect, cy = ny;
            double r2 = cx * cx + cy * cy;
            double f = 1 + s.curvature * r2 * 0.25;
            nx *= f;
            ny *= f;
            if (std::fabs(nx) > 1 || std::fabs(ny) > 1)
                return false;
            // rounded, slightly darkened corners
            double ex = std::max(0.0, std::fabs(nx) - 0.94) / 0.06;
            double ey = std::max(0.0, std::fabs(ny) - 0.92) / 0.08;
            edge = std::max(0.0, 1 - (ex * ex + ey * ey));
        }
        u = (nx + 1) / 2 * srcW; // in source pixels
        v = (ny + 1) / 2 * srcH; // in source lines
        return true;
    }

    // linear light -> output code value(s)
    static double SoftClip(double x)
    {
        const double knee = 0.85;
        if (x <= knee)
            return x;
        return knee + (1 - knee) * std::tanh((x - knee) / (1 - knee));
    }

    static double Pq(double nits)
    {
        const double m1 = 0.1593017578125, m2 = 78.84375, c1 = 0.8359375, c2 = 18.8515625, c3 = 18.6875;
        double y = std::max(0.0, nits / 10000.0);
        double p = std::pow(y, m1);
        return std::pow((c1 + c2 * p) / (1 + c3 * p), m2);
    }

    void RenderRows(int yFrom, int yTo, unsigned char *out8, unsigned short *out16) const
    {
        static const double bt709to2020[3][3] = {
            {0.6274, 0.3293, 0.0433}, {0.0691, 0.9195, 0.0114}, {0.0164, 0.0880, 0.8956}};
        for (int oy = yFrom; oy < yTo; oy++)
        {
            for (int ox = 0; ox < s.outW; ox++)
            {
                double rgb[3] = {0, 0, 0};
                int px = ox - x0, py = oy - y0;
                double u, v, edge;
                if (px >= 0 && px < picW && py >= 0 && py < picH && MapToSource(px, py, u, v, edge))
                {
                    // sample the horizontally-filtered rows at picture column u*scale
                    double hx = u * s.scale - 0.5;
                    int hx0 = std::max(0, std::min(picW - 1, (int)std::floor(hx)));
                    int hx1 = std::min(picW - 1, hx0 + 1);
                    double fx = std::max(0.0, std::min(1.0, hx - hx0));
                    double lineC = v - 0.5;
                    int l0 = (int)std::floor(lineC);
                    for (int li = l0 - 1; li <= l0 + 2; li++)
                    {
                        if (li < 0 || li >= srcH)
                            continue;
                        const float *row = hrows.data() + (size_t)li * picW * 3;
                        double d = lineC - li;
                        for (int c = 0; c < 3; c++)
                        {
                            double val = row[hx0 * 3 + c] * (1 - fx) + row[hx1 * 3 + c] * fx;
                            rgb[c] += val * Beam(d, val);
                        }
                    }
                    // phosphor mask, in screen space
                    const float *m = maskTile.data() + (((oy % maskH) * maskW) + (ox % maskW)) * 3;
                    int gx = std::max(0, std::min(srcW - 1, (int)u)), gy = std::max(0, std::min(srcH - 1, (int)v));
                    const float *g = glowImg.data() + ((size_t)gy * srcW + gx) * 3;
                    for (int c = 0; c < 3; c++)
                        rgb[c] = (rgb[c] * m[c] * brightnessComp + s.glow * g[c]) * edge;
                }
                size_t o = ((size_t)oy * s.outW + ox) * 3;
                if (!s.hdr)
                {
                    for (int c = 0; c < 3; c++)
                        out8[o + c] = (unsigned char)std::lround(255.0 * std::pow(SoftClip(rgb[c]), 1 / 2.2));
                }
                else
                {
                    // SDR white at paper-white nits; mask brought up with real headroom
                    double maskMean = 1 - s.maskStrength * 2.0 / 3.0;
                    double nitsScale = s.hdrPaperNits / maskMean;
                    for (int c = 0; c < 3; c++)
                    {
                        double lin = 0;
                        for (int k = 0; k < 3; k++)
                            lin += bt709to2020[c][k] * rgb[k];
                        double nits = std::min(s.hdrPeakNits, lin * nitsScale);
                        out16[o + c] = (unsigned short)std::lround(65535.0 * Pq(nits));
                    }
                }
            }
        }
    }

    void Render(std::vector<unsigned char> &out8, std::vector<unsigned short> &out16) const
    {
        size_t n = (size_t)s.outW * s.outH * 3;
        if (s.hdr)
            out16.assign(n, 0);
        else
            out8.assign(n, 0);
        int nthreads = std::max(1u, std::thread::hardware_concurrency());
        std::vector<std::thread> pool;
        int rows = (s.outH + nthreads - 1) / nthreads;
        for (int t = 0; t < nthreads; t++)
        {
            int a = t * rows, b = std::min(s.outH, a + rows);
            if (a >= b)
                break;
            pool.emplace_back([=, &out8, &out16] { RenderRows(a, b, out8.data(), out16.data()); });
        }
        for (auto &th : pool)
            th.join();
    }
};

static void ApplyPreset(Settings &s, const std::string &p)
{
    if (p == "trinitron")
    {
        s.mask = "grille";
        s.scanlines = 0.5;
        s.glow = 0.12;
        s.curvature = 0.04;
        s.maskStrength = 0.5;
    }
    else if (p == "tv")
    {
        s.mask = "slot";
        s.scanlines = 0.75;
        s.glow = 0.18;
        s.curvature = 0.10;
        s.softness = 0.55;
        s.maskStrength = 0.55;
    }
    else if (p == "hdr")
    {
        s.hdr = true;
        s.maskStrength = 0.6; // HDR headroom can afford a stronger, more visible mask
    }
    // "pc" is the Settings default
}

int main(int argc, char **argv)
{
    if (argc < 2)
    {
        fprintf(stderr, "usage: 3dmm-crt <renderdir> [--preset pc|trinitron|tv|hdr] [--mask shadow|grille|slot|none]\n"
                        "       [--scanlines x] [--glow x] [--curvature x] [--scale n] [--width w] [--height h]\n"
                        "       [--fps n] [--max-frames n] [--info] [--frame n out.bmp]\n");
        return 1;
    }
    std::string dir = argv[1];
    Settings s;
    // presets first, so explicit options override them
    for (int i = 2; i + 1 < argc; i++)
        if (0 == strcmp(argv[i], "--preset"))
            ApplyPreset(s, argv[i + 1]);
    bool info = false;
    long maxFrames = 0, oneFrame = -1;
    std::string oneFrameOut;
    for (int i = 2; i < argc; i++)
    {
        std::string a = argv[i];
        auto next = [&]() -> const char * { return i + 1 < argc ? argv[++i] : ""; };
        if (a == "--preset")
            next();
        else if (a == "--mask")
            s.mask = next();
        else if (a == "--scanlines")
            s.scanlines = atof(next());
        else if (a == "--glow")
            s.glow = atof(next());
        else if (a == "--curvature")
            s.curvature = atof(next());
        else if (a == "--scale")
            s.scale = atoi(next());
        else if (a == "--width")
            s.outW = atoi(next());
        else if (a == "--height")
            s.outH = atoi(next());
        else if (a == "--fps")
            s.fps = atoi(next());
        else if (a == "--max-frames")
            maxFrames = atol(next());
        else if (a == "--info")
            info = true;
        else if (a == "--frame")
        {
            oneFrame = atol(next());
            oneFrameOut = next();
        }
        else
        {
            fprintf(stderr, "unknown option %s\n", a.c_str());
            return 1;
        }
    }
    if (info)
    {
        printf("%d %d %s %d\n", s.outW, s.outH, s.hdr ? "rgb48le" : "rgb24", s.fps);
        return 0;
    }

    std::vector<Entry> entries;
    if (!ReadTimeline(dir, entries))
    {
        fprintf(stderr, "can't read %s/timeline.ffconcat\n", dir.c_str());
        return 2;
    }

    Crt crt;
    crt.s = s;
    Image frame;
    std::vector<unsigned char> out8;
    std::vector<unsigned short> out16;
    long current = -1;
    bool setup = false;

    auto load = [&](long idx) -> bool {
        if (idx == current)
            return true;
        if (!ReadBmp(dir + "/" + entries[idx].file, frame))
        {
            fprintf(stderr, "can't read %s\n", entries[idx].file.c_str());
            return false;
        }
        // stereo renders are left | right | 2-D (older ones just left | right)
        int eyeW = frame.w, xOffset = 0;
        const char *view = "2-D render";
        if (frame.w >= frame.h * 4)
        {
            eyeW = frame.w / 3;
            xOffset = 2 * eyeW;
            view = "the 2-D view of a stereo render";
        }
        else if (frame.w >= frame.h * 3)
        {
            eyeW = frame.w / 2;
            view = "the left eye (stereo render without a 2-D view)";
        }
        if (!setup)
        {
            crt.Setup(eyeW, frame.h);
            setup = true;
            fprintf(stderr, "3dmm-crt: %dx%d -> %dx%d at %dx in a %dx%d frame, mask %s, %s, from %s\n", eyeW, frame.h,
                    crt.picW, crt.picH, crt.s.scale, crt.s.outW, crt.s.outH, crt.s.mask.c_str(),
                    crt.s.hdr ? "HDR10" : "SDR", view);
        }
        crt.Prepare(frame, xOffset);
        crt.Render(out8, out16);
        current = idx;
        return true;
    };

    if (oneFrame >= 0)
    {
        if (oneFrame >= (long)entries.size() || !load(oneFrame))
            return 3;
        if (crt.s.hdr)
        {
            // preview of an HDR frame: write the PQ code values as 8-bit
            out8.resize(out16.size());
            for (size_t i = 0; i < out16.size(); i++)
                out8[i] = (unsigned char)(out16[i] >> 8);
        }
        return WriteBmp(oneFrameOut, out8.data(), crt.s.outW, crt.s.outH) ? 0 : 4;
    }

#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    double total = entries.back().start + entries.back().duration;
    long nOut = (long)std::ceil(total * s.fps - 1e-6);
    if (maxFrames > 0)
        nOut = std::min(nOut, maxFrames);
    size_t idx = 0;
    for (long n = 0; n < nOut; n++)
    {
        double t = (n + 0.5) / s.fps;
        while (idx + 1 < entries.size() && entries[idx + 1].start <= t)
            idx++;
        if (!load((long)idx))
            return 3;
        size_t wrote =
            crt.s.hdr ? fwrite(out16.data(), 2, out16.size(), stdout) : fwrite(out8.data(), 1, out8.size(), stdout);
        if (wrote != (crt.s.hdr ? out16.size() : out8.size()))
            return 0; // reader went away (e.g. ffmpeg stopped at -shortest)
    }
    fflush(stdout);
    return 0;
}
