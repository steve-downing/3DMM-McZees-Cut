// Screenshots from chosen spots in a scene player site (the review's walk-around).
//   node walk_scene.js <site dir> <out prefix> '<[[px,py,pz, tx,ty,tz, fov], ...]>' [scene fraction]
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const [site, out, spotsArg, frac] = process.argv.slice(2);
const types = { '.js': 'text/javascript', '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.txt': 'text/plain' };
const srv = http.createServer((q, r) => {
  const p = path.join(site, decodeURIComponent(q.url.split('?')[0]));
  fs.readFile(p, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' }); r.end(d); });
});
srv.listen(0, async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const pg = await b.newPage({ viewport: { width: 800, height: 500 } });
  const T = process.env.THREE_DIR;
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
  const spots = JSON.parse(spotsArg);
  for (let k = 0; k < spots.length; k++) {
    const s = spots[k];
    await pg.evaluate(s => window.__look(s.slice(0, 3), s.slice(3, 6), s[6]), s); await pg.waitForTimeout(400);
    await pg.screenshot({ path: `${out}-${k}.png` });
  }
  await b.close(); srv.close();
});
