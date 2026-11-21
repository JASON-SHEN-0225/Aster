'use strict';
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const ROOT = path.resolve(__dirname, '..', '..');
const SHOTS = path.join(ROOT, 'build', 'ui-shots');
const DOWNLOADS = path.join(ROOT, 'build', 'offer_dl');
const WEBID_FILE = path.join(ROOT, 'build', 'offer_webid.txt');
const baseUrl = (process.argv[2] || 'http://127.0.0.1:47883').replace(/\/$/, '');
const code = process.argv[3] || '';
const pairUrl = `${baseUrl}/?pair=${code}`;
fs.mkdirSync(SHOTS, { recursive: true });
fs.mkdirSync(DOWNLOADS, { recursive: true });
for (const f of fs.readdirSync(DOWNLOADS)) {
  try { fs.unlinkSync(path.join(DOWNLOADS, f)); } catch (_) { /* ignore */ }
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: 'new',
    defaultViewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
    args: ['--disable-gpu', '--no-first-run'],
  });
  const page = await browser.newPage();
  await page.setDefaultTimeout(25000);
  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  const result = { errors, downloads: [] };
  try {
    await page.goto(pairUrl, { waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForSelector('#app-view:not([hidden])', { timeout: 20000 });
    await new Promise((r) => setTimeout(r, 1000));
    const webId = await page.evaluate(() => localStorage.getItem('aster.web_id'));
    fs.writeFileSync(WEBID_FILE, webId || '', 'utf8');
    result.webId = webId;

    await page.waitForSelector('#offers-section:not([hidden])', { timeout: 35000 });
    await new Promise((r) => setTimeout(r, 700));
    result.offerText = await page.evaluate(() => document.querySelector('#offers-list').innerText);
    await page.screenshot({ path: path.join(SHOTS, '10-mobile-offer.png') });

    const cdp = await page.createCDPSession();
    if (process.env.OFFER_THROTTLE === '1') {
      await cdp.send('Network.enable');
      await cdp.send('Network.emulateNetworkConditions', {
        offline: false,
        latency: 10,
        downloadThroughput: 1024 * 1024,
        uploadThroughput: 1024 * 1024,
      });
    }
    try {
      await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: DOWNLOADS });
    } catch (_) {
      try { await cdp.send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: DOWNLOADS }); } catch (_) { /* ignore */ }
    }

    const buttons = await page.evaluate(() =>
      Array.from(document.querySelectorAll('#offers-list button')).map((b) => b.textContent.trim())
    );
    result.buttons = buttons;
    const accepted = await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('#offers-list button')).find((b) => {
        const t = b.textContent.trim();
        return t.includes('接收') || t.includes('接受');
      });
      if (!btn) return false;
      btn.click();
      return true;
    });
    result.accepted = accepted;
    if (!accepted) throw new Error('没有找到接受按钮');
    await new Promise((r) => setTimeout(r, 150));
    result.progress = await page.evaluate(() => {
      const box = document.querySelector('.offer-progress');
      return {
        visible: !!box && !box.hidden,
        text: box ? box.innerText : '',
      };
    });
    await new Promise((r) => setTimeout(r, 750));
    await page.screenshot({ path: path.join(SHOTS, '11-mobile-offer-accepted.png') });
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      const files = fs.readdirSync(DOWNLOADS).filter((f) => !f.endsWith('.crdownload'));
      if (files.length) break;
      await new Promise((r) => setTimeout(r, 300));
    }
    result.downloads = fs.readdirSync(DOWNLOADS);
    result.downloaded = result.downloads.length > 0;
    if (result.downloaded) {
      const file = path.join(DOWNLOADS, result.downloads[0]);
      const buf = fs.readFileSync(file);
      result.downloadSha = crypto.createHash('sha256').update(buf).digest('hex');
      result.downloadSize = buf.length;
      result.downloadText = buf.toString('utf8').slice(0, 100);
    }
    await new Promise((r) => setTimeout(r, 800));
    await page.screenshot({ path: path.join(SHOTS, '12-mobile-offer-downloaded.png') });
  } catch (err) {
    result.fatal = err.message;
    try { await page.screenshot({ path: path.join(SHOTS, '99-offer-failure.png') }); } catch (_) { /* ignore */ }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.fatal || errors.length ? 1 : 0);
})();
