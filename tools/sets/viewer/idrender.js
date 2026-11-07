// node idrender.js <dir with ids.bin + ids.json> : writes id<k>.rgba (bottom-up RGBA) per view
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const dir = path.resolve(process.argv[2]); const root = __dirname;
const srv = http.createServer((q, r) => { let u = decodeURIComponent(q.url.split('?')[0]);
  const p = (u === '/ids.bin' || u === '/ids.json') ? path.join(dir, u) : path.join(root, u);
  fs.readFile(p, (e, d) => { if (e) { r.writeHead(404); r.end(); return; }
    r.writeHead(200, { 'Content-Type': p.endsWith('.js') ? 'text/javascript' : p.endsWith('.html') ? 'text/html' : 'application/octet-stream' }); r.end(d); }); });
srv.listen(8766, async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const pg = await b.newPage({ viewport: { width: 544, height: 306 } });
  pg.on('pageerror', e => console.log('err:', e.message));
  await pg.goto('http://localhost:8766/idrender.html'); await pg.waitForFunction('window.ready', null, { timeout: 120000 });
  const n = JSON.parse(fs.readFileSync(path.join(dir, 'ids.json'))).views.length;
  for (let k = 0; k < n; k++) { const s = await pg.evaluate(`renderView(${k})`); fs.writeFileSync(path.join(dir, `id${k}.rgba`), Buffer.from(s, 'base64')); }
  const sp = path.join(dir, 'samples.json');
  if (fs.existsSync(sp)) { const s = await pg.evaluate(`visibleFrom(${fs.readFileSync(sp)})`); fs.writeFileSync(path.join(dir, 'seen.bin'), Buffer.from(s, 'base64')); }
  await b.close(); srv.close();
});
