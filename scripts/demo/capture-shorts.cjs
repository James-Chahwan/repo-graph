#!/usr/bin/env node
// Capture every animated HTML piece to a clean, native-resolution mp4.
//
//   node scripts/demo/capture-shorts.cjs            # all pieces
//   node scripts/demo/capture-shorts.cjs constellation   # just one (by name)
//
// WHY headless: the CLI/kitty pieces had to be captured at 765x1360 then ffmpeg-
// upscaled, because a real 1080x1920 window is TALLER than the 1440px monitor and
// gets clipped (desktop bleed). A browser render uses a VIRTUAL viewport with no
// screen-size limit — so we record at native 1080x1920 directly: no upscale, no
// bleed, no manual screen-recording. One full loop per piece => seamless to loop.

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
const TMP = path.join(OUT, '.webm');
fs.mkdirSync(TMP, { recursive: true });

const V = { w: 1080, h: 1920 };   // 9:16 vertical (Shorts/Reels/TikTok)
const W = { w: 1920, h: 1080 };   // 16:9 landscape (YouTube/Twitter)

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

(async () => {
  const browser = await chromium.launch();
  for (const [name, file, ms, size = V] of list) {
    const [fileOnly, query] = file.split('?');
    const url = 'file://' + path.join(DOCS, fileOnly) + (query ? '?' + query : '');
    const ctx = await browser.newContext({
      viewport: { width: size.w, height: size.h }, deviceScaleFactor: 1,
      recordVideo: { dir: TMP, size: { width: size.w, height: size.h } },
    });
    const page = await ctx.newPage();
    await page.goto(url);
    await page.waitForTimeout(ms + 900);          // one full loop + load settle
    const webm = await page.video().path();
    await ctx.close();                            // finalises the video file
    const mp4 = path.join(OUT, name + '.mp4');
    // trim the first ~0.4s (load) and take exactly one loop -> seamless; force 30fps
    execSync(
      `ffmpeg -y -ss 0.4 -t ${(ms / 1000).toFixed(2)} -i "${webm}" ` +
      `-vf "scale=${size.w}:${size.h}:flags=lanczos,fps=30" ` +
      `-c:v libx264 -pix_fmt yuv420p -crf 18 -an "${mp4}"`,
      { stdio: 'ignore' });
    fs.unlinkSync(webm);
    console.log(`  ✓ ${name}  →  shorts/${name}.mp4  (${size.w}x${size.h}, ${ms / 1000}s)`);
  }
  await browser.close();
  fs.rmSync(TMP, { recursive: true, force: true });
  console.log('\ndone → scripts/demo/shorts/');
})();
