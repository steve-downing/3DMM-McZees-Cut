// Review a rebuilt set through the scene player: the page from build_scene_site.py,
// seen from every original camera, next to the 1995 render.
//   node compare_scene.js <site dir> <views dir> <out.png> [scene fraction]
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const [site, views, out, frac] = process.argv.slice(2);
const types = { '.js': 'text/javascript', '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.txt': 'text/plain' };
const srv = http.createServer((q, r) => {
  const p = path.join(site, decodeURIComponent(q.url.split('?')[0]));
  fs.readFile(p, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' }); r.end(d); });
});
srv.listen(0, async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const pg = await b.newPage({ viewport: { width: 544, height: 306 } });
  const T = process.env.THREE_DIR;   // a local three.js, if the CDN isn't reachable
  if (T) await pg.route(/cdn\.jsdelivr\.net\/npm\/three@[^/]+\/(.*)/, r => {
    const f = path.join(T, r.request().url().replace(/.*three@[^/]+\//, ''));
    fs.existsSync(f) ? r.fulfill({ body: fs.readFileSync(f), contentType: 'text/javascript' }) : r.abort();
  });
  await pg.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
  pg.on('pageerror', e => console.log('page error:', e.message));
  await pg.goto(`http://localhost:${srv.address().port}/scene.html`);
  await pg.waitForSelector('#start:not([hidden])', { timeout: 120000 });
  await pg.addStyleTag({ content: '.hud, #start { display: none !important; }' });
  if (frac) await pg.evaluate(v => { const s = document.getElementById('scrub'); s.value = Math.round(v * 1000); s.dispatchEvent(new Event('input')); }, Number(frac));
  const cams = JSON.parse(fs.readFileSync(path.join(site, 'scene.json'))).cams.length;
  const shots = [];
  for (let k = 0; k < cams; k++) {
    await pg.evaluate(k => window.__setCam(k), k); await pg.waitForTimeout(400);
    const f = path.join(path.dirname(out), `_cmp${k}.png`); await pg.screenshot({ path: f }); shots.push(f);
  }
  await b.close(); srv.close();
  const { execFileSync } = require('child_process');
  execFileSync('python3', ['-c', `
import sys
from PIL import Image, ImageDraw
shots, views, out = sys.argv[1].split(','), sys.argv[2], sys.argv[3]
W, H = 544, 306
s = Image.new('RGB', (2 * W + 8, len(shots) * (H + 8)), (20, 20, 24)); d = ImageDraw.Draw(s)
for k, f in enumerate(shots):
    y = k * (H + 8)
    s.paste(Image.open(f).convert('RGB').resize((W, H)), (0, y)); s.paste(Image.open('%s/cam%d.jpg' % (views, k)).convert('RGB'), (W + 8, y))
    d.text((6, y + 4), 'camera %d' % (k + 1), fill=(255, 255, 0))
s.save(out)`, shots.join(','), views, out]);
  shots.forEach(f => fs.unlinkSync(f));
  console.log('wrote', out);
});
