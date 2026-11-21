/* 官网视觉回归小工具（开发用，不随站点上线）
   ------------------------------------------------------------------
   用无头 Edge + CDP 打开页面，设置视口、量尺寸、截屏。零依赖，
   Node.js 24 自带 fetch / WebSocket。

   用法：
     node website/tools/cdp-shot.js --url http://127.0.0.1:8137/ \
       --w 390 --h 844 --out mobile.png --scroll "#mobile" --diag

   参数：
     --url      页面地址
     --w/--h    视口宽高（默认 1440x900）
     --dpr      设备像素比（默认 1；移动端可给 2）
     --out      截图路径（默认 TEMP/aster-cdp.png）
     --scroll   滚动到某个选择器或像素值
     --full     截整页（先触发所有 reveal）
     --diag     输出布局诊断 JSON
     --wait     额外等待毫秒（默认 900）
*/

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const PORT = 9444 + Math.floor(Math.random() * 400);

function arg(name, fallback) {
  const i = process.argv.indexOf("--" + name);
  if (i < 0) return fallback;
  const next = process.argv[i + 1];
  return next && !next.startsWith("--") ? next : true;
}

const url = arg("url", "http://127.0.0.1:8137/index.html");
const width = parseInt(arg("w", "1440"), 10);
const height = parseInt(arg("h", "900"), 10);
const dpr = parseFloat(arg("dpr", "1"));
const out = arg("out", path.join(os.tmpdir(), "aster-cdp.png"));
const scrollTo = arg("scroll", "");
const full = !!arg("full", false);
const diag = !!arg("diag", false);
const extraWait = parseInt(arg("wait", "900"), 10);
const clickSelector = arg("click", "");
const evalExpr = arg("eval", "");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "aster-cdp-"));
  const proc = spawn(
    EDGE,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--hide-scrollbars",
      "--remote-debugging-port=" + PORT,
      "--user-data-dir=" + profile,
      "about:blank",
    ],
    { stdio: "ignore", detached: false }
  );

  let version = null;
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (res.ok) {
        version = await res.json();
        break;
      }
    } catch (e) {
      /* not up yet */
    }
    await sleep(150);
  }
  if (!version) throw new Error("Edge 没有在调试端口启动");

  const target = await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, {
    method: "PUT",
  }).then((r) => r.json());

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

  let nextId = 0;
  const pending = new Map();
  const pageErrors = [];
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      pageErrors.push(msg.params.entry.text);
    }
    if (msg.method === "Runtime.exceptionThrown") {
      pageErrors.push(
        msg.params.exceptionDetails.exception
          ? msg.params.exceptionDetails.exception.description
          : msg.params.exceptionDetails.text
      );
    }
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    }
  };

  function send(method, params) {
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: dpr,
    mobile: width < 600,
  });

  await send("Page.navigate", { url });
  for (let i = 0; i < 80; i++) {
    const state = await send("Runtime.evaluate", {
      expression: "document.readyState",
      returnByValue: true,
    });
    if (state.result.value === "complete") break;
    await sleep(100);
  }
  await sleep(extraWait);

  if (scrollTo) {
    const expr =
      typeof scrollTo === "string" && isNaN(Number(scrollTo))
        ? `(() => { const el = document.querySelector(${JSON.stringify(scrollTo)});
            if (el) el.scrollIntoView({block: "start"});
            return el ? el.getBoundingClientRect().top : null; })()`
        : `window.scrollTo(0, ${Number(scrollTo)}); "ok"`;
    await send("Runtime.evaluate", { expression: expr, returnByValue: true });
    await sleep(900);
  }

  if (clickSelector) {
    await send("Runtime.evaluate", {
      expression: `(() => { const el = document.querySelector(${JSON.stringify(clickSelector)});
        if (el) el.click(); return !!el; })()`,
      returnByValue: true,
    });
    await sleep(650);
  }

  if (evalExpr) {
    const result = await send("Runtime.evaluate", {
      expression: evalExpr,
      returnByValue: true,
    });
    console.log("EVAL " + JSON.stringify(result.result && result.result.value));
    await sleep(500);
  }

  if (diag) {
    const probe = await send("Runtime.evaluate", {
      expression: `(() => {
        const pick = (sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          return {
            x: +r.x.toFixed(1), y: +r.y.toFixed(1),
            w: +r.width.toFixed(1), h: +r.height.toFixed(1),
            right: +r.right.toFixed(1),
            display: cs.display, minWidth: cs.minWidth,
            grid: cs.gridTemplateColumns,
            fontSize: cs.fontSize, overflowX: cs.overflowX,
          };
        };
        return JSON.stringify({
          viewport: [innerWidth, innerHeight],
          docScrollWidth: document.documentElement.scrollWidth,
          bodyScrollWidth: document.body.scrollWidth,
          hero: pick(".hero"),
          heroGrid: pick(".hero-grid"),
          heroCopy: pick(".hero-copy"),
          lead: pick(".hero-lead"),
          specs: pick(".hero-specs"),
          stage: pick(".hero-visual"),
          transfer: pick(".transfer"),
          thumbs: pick(".thumbs"),
          thumb: pick(".thumb"),
          phone: pick(".phone"),
          phoneScreen: pick(".phone__screen"),
          phoneImg: pick(".phone__screen img"),
          windowScreen: pick(".window__screen"),
          windowImg: pick(".window__screen img"),
          panel: pick(".dl-card--featured"),
        }, null, 2);
      })()`,
      returnByValue: true,
    });
    console.log(probe.result.value);
  }

  if (full) {
    await send("Runtime.evaluate", {
      expression: `(() => {
        document.querySelectorAll(".reveal").forEach((el) => el.classList.add("is-in"));
        document.querySelectorAll("[data-count]").forEach((el) => { el.dataset.done = "1"; });
        document.querySelectorAll("[data-bar]").forEach((el) => { el.style.width = el.dataset.bar + "%"; });
        document.querySelectorAll("img").forEach((img) => { img.loading = "eager"; });
        window.scrollTo(0, 0);
        return true;
      })()`,
      returnByValue: true,
    });
    await sleep(2200);
    const metrics = await send("Page.getLayoutMetrics");
    const size = metrics.cssContentSize;
    const shot = await send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: size.width, height: size.height, scale: 1 },
    });
    fs.writeFileSync(out, Buffer.from(shot.data, "base64"));
  } else {
    const shot = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(out, Buffer.from(shot.data, "base64"));
  }

  if (pageErrors.length) {
    console.log("PAGE ERRORS:");
    pageErrors.forEach((e) => console.log("  - " + e));
  } else {
    console.log("PAGE ERRORS: none");
  }

  console.log("SHOT " + out);
  ws.close();
  proc.kill();
  await sleep(200);
}

main().catch((err) => {
  console.error("ERROR", err.message);
  process.exit(1);
});
