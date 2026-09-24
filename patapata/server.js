'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const puppeteer = require('puppeteer');
const ffmpegPath = require('ffmpeg-static');
const AdmZip = require('adm-zip');

const PORT = Number(process.env.PORT || 10000);
const HOST = '0.0.0.0';
const ARCHIVE_RE = /^latest\.zip\.b64\.\d+$/;
const EXTRACT = path.join('/tmp', 'matsuyama-patapata-web');

function findWebRoot(dir) {
  if (fs.existsSync(path.join(dir, 'index.html'))) return dir;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const found = findWebRoot(path.join(dir, entry.name));
    if (found) return found;
  }
  return null;
}

function prepareWeb() {
  const parts = fs.readdirSync(__dirname).filter(name => ARCHIVE_RE.test(name)).sort();
  if (!parts.length) throw new Error('patapata archive parts missing');
  const packed = parts.map(name => fs.readFileSync(path.join(__dirname, name), 'utf8').trim()).join('');
  const bytes = Buffer.from(packed, 'base64');
  fs.rmSync(EXTRACT, { recursive: true, force: true });
  fs.mkdirSync(EXTRACT, { recursive: true });
  new AdmZip(bytes).extractAllTo(EXTRACT, true);
  const root = findWebRoot(EXTRACT);
  if (!root) throw new Error('index.html not found in latest.zip');
  return root;
}

const WEB = prepareWeb();
const WIDTH = Number(process.env.PATAPATA_WIDTH || 1280);
const HEIGHT = Number(process.env.PATAPATA_HEIGHT || 720);
const FPS = Math.max(1, Math.min(8, Number(process.env.PATAPATA_FPS || 4)));
const MAX_STREAMS = Math.max(1, Math.min(2, Number(process.env.PATAPATA_MAX_STREAMS || 1)));
let activeStreams = 0;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.txt': 'text/plain; charset=utf-8'
};

function send(res, code, body, type = 'text/plain; charset=utf-8') {
  const b = Buffer.isBuffer(body) ? body : Buffer.from(String(body));
  res.writeHead(code, {
    'Content-Type': type,
    'Content-Length': b.length,
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*'
  });
  res.end(b);
}

function serveStatic(req, res, pathname) {
  let rel = pathname.replace(/^\/view\/?/, '');
  if (!rel || rel.endsWith('/')) rel += 'index.html';
  let decoded;
  try { decoded = decodeURIComponent(rel); } catch { return send(res, 400, 'bad path\n'); }
  const full = path.resolve(WEB, decoded);
  if (!full.startsWith(path.resolve(WEB) + path.sep)) return send(res, 403, 'forbidden\n');
  fs.readFile(full, (err, data) => {
    if (err) return send(res, err.code === 'ENOENT' ? 404 : 500, 'not found\n');
    const ext = path.extname(full).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Content-Length': data.length,
      'Cache-Control': ext === '.json' || ext === '.js' ? 'no-cache' : 'public, max-age=300',
      'Access-Control-Allow-Origin': '*'
    });
    if (req.method === 'HEAD') return res.end();
    res.end(data);
  });
}

async function launchPage() {
  const browser = await puppeteer.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--hide-scrollbars',
      '--autoplay-policy=no-user-gesture-required'
    ]
  });
  const page = await browser.newPage();
  await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });
  await page.goto(`http://127.0.0.1:${PORT}/view/`, {
    waitUntil: 'domcontentloaded',
    timeout: 25000
  });
  await page.addStyleTag({ content: '#update-modal{display:none!important}' });
  await new Promise(resolve => setTimeout(resolve, 1200));
  return { browser, page };
}

function ffmpegArgs() {
  return [
    '-hide_banner', '-loglevel', 'warning',
    '-f', 'image2pipe', '-vcodec', 'mjpeg', '-framerate', String(FPS), '-i', 'pipe:0',
    '-re', '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
    '-map', '0:v:0', '-map', '1:a:0',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
    '-profile:v', 'baseline', '-level', '3.1',
    '-pix_fmt', 'yuv420p', '-r', String(FPS), '-g', String(FPS * 2),
    '-keyint_min', String(FPS * 2), '-sc_threshold', '0',
    '-b:v', '950k', '-maxrate', '1100k', '-bufsize', '2200k',
    '-c:a', 'aac', '-b:a', '64k', '-ar', '48000', '-ac', '2',
    '-muxdelay', '0', '-muxpreload', '0', '-flush_packets', '1',
    '-mpegts_flags', 'resend_headers',
    '-f', 'mpegts', 'pipe:1'
  ];
}

async function streamTs(req, res) {
  if (req.method === 'HEAD') {
    res.writeHead(200, {
      'Content-Type': 'video/mp2t',
      'Cache-Control': 'no-store',
      'Access-Control-Allow-Origin': '*'
    });
    return res.end();
  }
  if (activeStreams >= MAX_STREAMS) return send(res, 429, 'patapata stream busy\n');
  activeStreams += 1;

  let browser = null;
  let page = null;
  let ff = null;
  let closed = false;
  const cleanup = async () => {
    if (closed) return;
    closed = true;
    try { if (ff && ff.stdin && !ff.stdin.destroyed) ff.stdin.destroy(); } catch {}
    try { if (ff && !ff.killed) ff.kill('SIGKILL'); } catch {}
    try { if (page) await page.close(); } catch {}
    try { if (browser) await browser.close(); } catch {}
    activeStreams = Math.max(0, activeStreams - 1);
  };

  req.on('close', () => { cleanup(); });
  res.on('close', () => { cleanup(); });

  try {
    ({ browser, page } = await launchPage());
    ff = spawn(ffmpegPath, ffmpegArgs(), { stdio: ['pipe', 'pipe', 'pipe'] });
    let fferr = '';
    ff.stderr.on('data', d => { fferr = (fferr + d.toString()).slice(-6000); });
    ff.on('error', async err => {
      console.error('[patapata] ffmpeg error', err);
      await cleanup();
    });

    res.writeHead(200, {
      'Content-Type': 'video/mp2t',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma': 'no-cache',
      'Access-Control-Allow-Origin': '*',
      'Connection': 'close'
    });
    ff.stdout.pipe(res);

    const frameMs = Math.round(1000 / FPS);
    while (!closed && ff.exitCode === null) {
      const started = Date.now();
      const jpg = await page.screenshot({ type: 'jpeg', quality: 82, captureBeyondViewport: false });
      if (!ff.stdin.write(jpg)) {
        await new Promise(resolve => ff.stdin.once('drain', resolve));
      }
      const wait = frameMs - (Date.now() - started);
      if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
    }
    if (ff.exitCode && ff.exitCode !== 0) console.error('[patapata] ffmpeg exited', ff.exitCode, fferr);
  } catch (err) {
    console.error('[patapata] stream start failed', err && err.stack ? err.stack : err);
    if (!res.headersSent) send(res, 503, `patapata start failed: ${err.message || err}\n`);
  } finally {
    await cleanup();
  }
}

async function snapshot(res) {
  let browser = null;
  try {
    const launched = await launchPage();
    browser = launched.browser;
    const png = await launched.page.screenshot({ type: 'png', captureBeyondViewport: false });
    res.writeHead(200, {
      'Content-Type': 'image/png',
      'Content-Length': png.length,
      'Cache-Control': 'no-store',
      'Access-Control-Allow-Origin': '*'
    });
    res.end(png);
  } catch (err) {
    send(res, 503, `snapshot failed: ${err.message || err}\n`);
  } finally {
    try { if (browser) await browser.close(); } catch {}
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (url.pathname === '/health') return send(res, 200, `ok active=${activeStreams}\n`);
  if (url.pathname === '/stream.ts') return streamTs(req, res);
  if (url.pathname === '/snapshot.png') return snapshot(res);
  if (url.pathname === '/') {
    res.writeHead(302, { Location: '/view/' });
    return res.end();
  }
  if (url.pathname.startsWith('/view/')) return serveStatic(req, res, url.pathname);
  return send(res, 404, 'not found\n');
});

server.listen(PORT, HOST, () => {
  console.log(`[patapata] listening on http://${HOST}:${PORT} ${WIDTH}x${HEIGHT}@${FPS}fps`);
});
