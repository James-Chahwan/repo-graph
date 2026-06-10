#!/usr/bin/env node
// Capture every animated HTML piece to a clean, native-resolution, 60fps mp4.
//
//   node scripts/demo/capture-shorts.cjs            # all pieces
//   node scripts/demo/capture-shorts.cjs constellation   # just one (by name)
//
// HOW: headless chromium with the frame-rate limiter OFF paints these CSS/SVG
// animations at ~90fps. We grab every painted frame via CDP Page.screencast
// (real frames — no interpolation/ghosting), then resample to a constant 60fps
// with ffmpeg using the frames' own timestamps, and clip to exactly one loop so
// it loops seamlessly. Output is NATIVE res (1080x1920 / 1920x1080) — no upscale,
// no monitor clip (the kitty pieces needed 765x1360->upscale; a virtual viewport
// doesn't). Output -> scripts/demo/shorts/<name>.mp4 (crf 18 source; re-encode
// to whatever you like, e.g. VP9/AV1 crf for tiny web files).

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const os = require('os');

function loadPlaywright() {
  try { return require('playwright'); } catch (e) {}
  const found = execSync(
    `find ${os.homedir()}/.npm/_npx -maxdepth 4 -type d -path '*node_modules/playwright' 2>/dev/null | head -1`
  ).toString().trim();
  if (found) return require(found);
  throw new Error('playwright not found. Install once: npm i -g playwright');
}
const { chromium } = loadPlaywright();

const DOCS = path.resolve(__dirname, '../../docs');
const OUT = path.resolve(__dirname, 'shorts');
const TMP = path.join(OUT, '.frames');
fs.mkdirSync(OUT, { recursive: true });

const V = { w: 1080, h: 1920 };   // 9:16 vertical
const W = { w: 1920, h: 1080 };   // 16:9 landscape

// name, file (+ optional ?query), loop length ms (= the piece's TOTAL), [size]
const PIECES = [
  ['explainer', 'explainer.html', 30000],
  ['usage', 'usage.html', 30000],
  ['monorepo', 'wow-monorepo.html', 12000],
  ['constellation', 'wow-constellation.html', 12000],
  ['tectonic', 'wow-tectonic.html', 12500],
  ['receipt', 'wow-receipt.html', 13500],
  ['skyline', 'wow-skyline.html', 12500],
  ['twomaps', 'wow-twomaps.html', 13500],
  ['roulette', 'wow-roulette.html', 12500],
  ['typed-blast', 'wow-typed-blast.html', 12500],
  ['polyglot', 'wow-polyglot.html', 12000],
  ['fresh', 'wow-fresh.html', 11500],
  ['dayone', 'wow-dayone.html', 12000],
  ['invisible', 'wow-invisible.html', 12500],
  ['yours', 'wow-yours.html', 12500],
  ['clip-ground', 'clips.html?clip=ground', 10200],
  ['clip-context', 'clips.html?clip=context', 6800],
  ['clip-trace', 'clips.html?clip=trace', 10200],
  ['clip-find', 'clips.html?clip=find', 10200],
  ['clip-flow', 'clips.html?clip=flow', 10200],
  ['clip-install', 'clips.html?clip=install', 10200],
  ['explainer-wide', 'explainer-wide.html', 30000, W],
];

const only = process.argv[2];
const list = PIECES.filter(p => !only || p[0] === only || p[1].includes(only));
if (!list.length) { console.error('no piece matches', only); process.exit(1); }

async function capture(browser, name, file, ms, size) {
  fs.rmSync(TMP, { recursive: true, force: true });
  fs.mkdirSync(TMP, { recursive: true });
  const [fileOnly, query] = file.split('?');
  const url = 'file://' + path.join(DOCS, fileOnly) + (query ? '?' + query : '');

  // capture at 0.8x (where headless paints >60fps; full res caps at ~37fps), then
  // upscale to the output size — true 60fps motion, negligible softness on flat art.
  const cap = { w: Math.round(size.w * 0.8), h: Math.round(size.h * 0.8) };
  const ctx = await browser.newContext({ viewport: { width: cap.w, height: cap.h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  const frames = [];
  cdp.on('Page.screencastFrame', async f => {
    const fn = path.join(TMP, `f${String(frames.length).padStart(6, '0')}.jpg`);
    try { fs.writeFileSync(fn, Buffer.from(f.data, 'base64')); frames.push({ file: fn, ts: f.metadata.timestamp }); } catch (e) {}
    try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) {}
  });
  await page.goto(url);
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 80, everyNthFrame: 1 });
  await page.waitForTimeout(ms + 400);
  try { await cdp.send('Page.stopScreencast'); } catch (e) {}
  await ctx.close();

  // keep exactly one loop [t0, t0+ms); ffmpeg concat with per-frame durations -> 60fps CFR
  const t0 = frames[0].ts, end = t0 + ms / 1000;
  const keep = frames.filter(f => f.ts < end);
  let concat = '';
  for (let i = 0; i < keep.length; i++) {
    const next = (i < keep.length - 1) ? keep[i + 1].ts : end;
    concat += `file '${keep[i].file}'\nduration ${Math.max(next - keep[i].ts, 0.001).toFixed(5)}\n`;
  }
  concat += `file '${keep[keep.length - 1].file}'\n`;
  const listFile = path.join(TMP, 'list.txt');
  fs.writeFileSync(listFile, concat);

  const mp4 = path.join(OUT, name + '.mp4');
  execSync(
    `ffmpeg -y -f concat -safe 0 -i "${listFile}" ` +
    `-vf "fps=60,scale=${size.w}:${size.h}:flags=lanczos" ` +
    `-c:v libx264 -pix_fmt yuv420p -crf 18 -an "${mp4}"`,
    { stdio: 'ignore' });
  fs.rmSync(TMP, { recursive: true, force: true });
  return { mp4, frames: keep.length };
}

(async () => {
  const browser = await chromium.launch({ args: ['--disable-frame-rate-limit', '--disable-gpu-vsync', '--disable-background-timer-throttling'] });
  for (const [name, file, ms, size = V] of list) {
    const r = await capture(browser, name, file, ms, size);
    console.log(`  ✓ ${name}  →  shorts/${name}.mp4  (${size.w}x${size.h} · 60fps · ${ms / 1000}s · ${r.frames} src frames)`);
  }
  await browser.close();
  console.log('\ndone → scripts/demo/shorts/');
})();
