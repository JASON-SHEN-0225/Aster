/**
 * Aster 手机网页端真实浏览器探针：
 *  - 390x844 手机视口
 *  - 自动配对
 *  - 发送文本
 *  - 上传 6MB 文件（限速观察进度）
 *  - 主题 / 设置抽屉截图
 *  - 收集控制台错误、失败请求、服务端落盘结果
 *
 * 用法（先启动 aster web --port 47880，拿到配对码）：
 *   node tools/uiprobe/probe.js http://127.0.0.1:47880 611240
 */
'use strict';

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const ROOT = path.resolve(__dirname, '..', '..');
const SHOTS = path.join(ROOT, 'build', 'ui-shots');
const baseUrl = (process.argv[2] || 'http://127.0.0.1:47880').replace(/\/$/, '');
const code = process.argv[3] || '';
const pairUrl = `${baseUrl}/${code ? `?pair=${code}` : ''}`;

fs.mkdirSync(SHOTS, { recursive: true });
const uploadPath = path.join(ROOT, 'build', 'probe-upload.bin');
const uploadBytes = Buffer.alloc(6 * 1024 * 1024);
for (let i = 0; i < uploadBytes.length; i += 1) uploadBytes[i] = (i * 37 + 11) & 0xff;
fs.writeFileSync(uploadPath, uploadBytes);
const uploadSha = crypto.createHash('sha256').update(uploadBytes).digest('hex');

function shot(page, name, fullPage = false) {
  return page.screenshot({ path: path.join(SHOTS, name), fullPage });
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: 'new',
    defaultViewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
    args: ['--disable-gpu', '--no-first-run', '--no-default-browser-check'],
  });
  const page = await browser.newPage();
  await page.setDefaultTimeout(20000);

  const errors = [];
  const failedRequests = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`console: ${msg.text()}`);
  });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  page.on('requestfailed', (req) => failedRequests.push(`${req.url()} :: ${req.failure() && req.failure().errorText}`));

  const result = { steps: [], errors, failedRequests, uploadSha, uploadSize: uploadBytes.length };
  try {
    await page.goto(pairUrl, { waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForSelector('#app-view:not([hidden])', { timeout: 20000 });
    await new Promise((r) => setTimeout(r, 1600));
    result.steps.push('paired');
    await shot(page, '01-mobile-top.png');
    await page.screenshot({ path: path.join(SHOTS, '01-mobile-top-full.png'), fullPage: true });

    await page.click('#send-mode-switch [data-mode="text"]');
    await new Promise((r) => setTimeout(r, 350));
    // 文本区
    await page.evaluate(() => {
      const el = document.querySelector('#texts-title');
      window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 24);
      const banner = document.querySelector('#install-banner');
      if (banner) banner.hidden = true;
      const row = document.querySelector('#install-row');
      if (row) row.hidden = true;
    });
    await new Promise((r) => setTimeout(r, 600));
    await shot(page, '02-mobile-text.png');

    await page.type('#text-input', '来自 Puppeteer 的文本：你好，星流 ☄');
    await page.click('#text-send');
    await page.waitForFunction(
      () => {
        const el = document.querySelector('#texts-list');
        return el && el.innerText.includes('Puppeteer');
      },
      { timeout: 15000 }
    );
    result.steps.push('text-sent');
    await shot(page, '03-mobile-text-sent.png');

    // 返回顶部，上传文件
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await new Promise((r) => setTimeout(r, 300));
    const input = await page.$('#file-input');
    await input.uploadFile(uploadPath);
    await page.waitForSelector('#send-sheet.is-open', { timeout: 8000 });
    await new Promise((r) => setTimeout(r, 700));
    result.steps.push('send-sheet-open');
    result.sendSheetRect = await page.evaluate(() => {
      const el = document.querySelector('#send-sheet');
      return el ? el.getBoundingClientRect().toJSON() : null;
    });
    await shot(page, '04-mobile-send-sheet.png');

    // 限速，观察进度与速度
    const cdp = await page.createCDPSession();
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: 15,
      downloadThroughput: 3 * 1024 * 1024,
      uploadThroughput: 1.5 * 1024 * 1024,
    });

    await page.click('#send-confirm');
    await page.waitForFunction(
      () => document.querySelector('#transfers-list .transfer-card'),
      { timeout: 10000 }
    );
    await new Promise((r) => setTimeout(r, 1800));
    await shot(page, '05-mobile-uploading.png');
    result.steps.push('upload-started');

    await page.waitForFunction(
      () => {
        const cards = Array.from(document.querySelectorAll('#transfers-list .transfer-card'));
        return cards.some((c) => c.classList.contains('is-complete'));
      },
      { timeout: 60000 }
    );
    result.steps.push('upload-completed');
    await new Promise((r) => setTimeout(r, 800));
    await shot(page, '06-mobile-upload-done.png');

    await cdp.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: 0,
      downloadThroughput: -1,
      uploadThroughput: -1,
    });

    // 主题切换
    await page.click('#theme-toggle');
    await new Promise((r) => setTimeout(r, 500));
    result.theme = await page.evaluate(() => document.documentElement.dataset.theme);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await shot(page, '07-mobile-light.png');
    await page.click('#theme-toggle');
    await new Promise((r) => setTimeout(r, 400));

    // 设置抽屉
    await page.click('#settings-btn');
    await page.waitForSelector('#settings-sheet.is-open', { timeout: 5000 });
    await new Promise((r) => setTimeout(r, 350));
    await shot(page, '08-mobile-settings.png');
    await page.click('#settings-close');
    await new Promise((r) => setTimeout(r, 450));

    // 历史抽屉
    await page.evaluate(() => {
      document.querySelector('#open-history').scrollIntoView({ block: 'center', behavior: 'instant' });
    });
    await new Promise((r) => setTimeout(r, 300));
    await page.evaluate(() => document.querySelector('#open-history').click());
    await page.waitForSelector('#history-sheet.is-open', { timeout: 5000 });
    await new Promise((r) => setTimeout(r, 350));
    await shot(page, '09-mobile-history.png');

    result.token = await page.evaluate(() => localStorage.getItem('aster.token'));
    result.webId = await page.evaluate(() => localStorage.getItem('aster.web_id'));
    result.phoneName = await page.evaluate(() => localStorage.getItem('aster.phone_name'));
    result.finalTitle = await page.title();
    result.bodyHasPairView = await page.evaluate(() => {
      const el = document.querySelector('#pair-view');
      return el ? !el.hidden : null;
    });
  } catch (err) {
    result.fatal = err.message;
    try { await shot(page, '99-failure.png'); } catch (_) { /* ignore */ }
  } finally {
    await browser.close();
  }

  // 服务端落盘检查（假设服务 Download 目录为 build/web_dl）
  const serverFile = path.join(ROOT, 'build', 'web_dl', 'probe-upload.bin');
  result.serverFile = serverFile;
  result.serverFileExists = fs.existsSync(serverFile);
  if (result.serverFileExists) {
    const got = fs.readFileSync(serverFile);
    result.serverSha = crypto.createHash('sha256').update(got).digest('hex');
    result.serverFileMatches = result.serverSha === uploadSha;
  }
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.fatal || errors.length ? 1 : 0);
})();
