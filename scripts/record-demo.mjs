// Record a short demo clip of the Table Topics board and write docs/demo.webm.
//
// It boots its own board server in demo mode, drives the full flow with
// Playwright (welcome -> demo -> roll -> spotlight reveal -> focus -> done),
// and records the page via Chrome's screencast, so the real animations are
// captured rather than stitched from screenshots. Playwright records VP8, so we
// transcode the capture to a smaller VP9 .webm with ffmpeg.
//
//   npm run record:demo
//
// Needs: `npx playwright install chromium` (once) and ffmpeg on PATH
// (macOS: `brew install ffmpeg`).

import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
const PORT = Number(process.env.RECORD_PORT || 3010);
const BASE = `http://127.0.0.1:${PORT}`;
const OUT = join(ROOT, "docs", "demo.webm");
const SIZE = { width: 1280, height: 800 };

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForServer(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await wait(250);
  }
  throw new Error(`server did not start at ${url}`);
}

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: "inherit" });
    p.on("error", (err) => {
      if (err.code === "ENOENT") {
        reject(new Error(`${cmd} not found on PATH. Install it (macOS: brew install ${cmd}).`));
      } else {
        reject(err);
      }
    });
    p.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`))));
  });
}

async function recordWebm(dir) {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: SIZE,
    deviceScaleFactor: 1,
    reducedMotion: "no-preference",
    recordVideo: { dir, size: SIZE },
  });
  const page = await context.newPage();

  // Start from a clean first run: no saved flag, no leftover demo.
  await page.goto(BASE);
  await page.evaluate(async () => {
    localStorage.clear();
    await fetch("/api/demo/stop", { method: "POST" });
  });
  await page.reload();

  // 1. First-run welcome.
  await page.waitForSelector("#welcome:not([hidden])");
  await wait(1900);

  // 2. Load the sample meeting.
  await page.click("#demoStartBtn");
  await page.waitForSelector("#demoBar:not([hidden])");
  await wait(1500);

  // 3. Roll a participant and let the spotlight reveal land.
  await page.click("#pickBtn");
  await page.waitForSelector("#shuffleName.settled", { timeout: 6000 });
  await wait(1800);

  // 4. Hand them a topic -> the name morphs into the focus hero.
  await page.click("#pickTopicsHost .card.choose");
  await page.waitForSelector("#focus:not([hidden])");
  await wait(2800);

  // 5. Mark done -> celebration, back to the board.
  await page.click("#focusDoneBtn");
  await page.waitForSelector("#board:not([hidden])");
  await wait(1700);

  // 6. Exit the demo back to a clean slate.
  await page.click("#demoExitBtn");
  await wait(1100);

  const video = page.video();
  await context.close();
  await browser.close();
  return video.path();
}

async function toVp9(src) {
  // CRF VP9 (constant quality, -b:v 0) is well suited to a flat-color, text-heavy
  // screencast and meaningfully smaller than the VP8 capture. yuv420p keeps it
  // broadly playable; row multithreading speeds the encode up.
  await run("ffmpeg", [
    "-y",
    "-i",
    src,
    "-an",
    "-c:v",
    "libvpx-vp9",
    "-crf",
    "32",
    "-b:v",
    "0",
    "-pix_fmt",
    "yuv420p",
    "-row-mt",
    "1",
    OUT,
  ]);
}

async function main() {
  const server = spawn("uv", ["run", "board.py", "--no-ax", "--port", String(PORT)], {
    cwd: ROOT,
    stdio: "ignore",
  });
  const tmp = await mkdtemp(join(tmpdir(), "ttdemo-"));
  try {
    await waitForServer(`${BASE}/`);
    console.log("recording demo flow...");
    const webm = await recordWebm(tmp);
    console.log("transcoding to VP9...");
    await toVp9(webm);
    console.log(`wrote ${OUT}`);
  } finally {
    server.kill("SIGTERM");
    await rm(tmp, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
