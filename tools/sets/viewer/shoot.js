// Render views of a cartoon set model, headless, with the explorer's lights and materials.
//   node shoot.js <model.glb> <cams.json> '<jobs>' [actors.glb]
// jobs: JSON list of {js, out}: js is setView(k) (an original 3DMM camera, 0-based)
// or setFree(px,py,pz, tx,ty,tz, fov) (eye, target, vertical fov); out is a PNG path.
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const [model, cams, jobsArg, actors] = process.argv.slice(2);
const root = __dirname;
const types = { '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json' };
const srv = http.createServer((q, r) => {
  const u = decodeURIComponent(q.url.split('?')[0]);
  const p = u === '/model.glb' ? path.resolve(model) : u === '/cams.json' ? path.resolve(cams)
    : u === '/actors.glb' ? (actors ? path.resolve(actors) : '/nonexistent') : path.join(root, u);
  fs.readFile(p, (e, d) => {
    if (e) { r.writeHead(404); r.end(); return; }
    r.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' }); r.end(d);
  });
});
srv.listen(0, async () => {
  const port = srv.address().port;
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const pg = await b.newPage({ viewport: { width: 544, height: 306 } });
  pg.on('pageerror', e => console.log('page error:', e.message));
  await pg.goto(`http://localhost:${port}/preview.html?e=1.4`);
  await pg.waitForFunction('window.ready', null, { timeout: 120000 });
  for (const j of JSON.parse(jobsArg)) { await pg.evaluate(j.js); await pg.screenshot({ path: j.out }); }
  await b.close(); srv.close();
});
