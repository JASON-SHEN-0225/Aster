'use strict';
const puppeteer = require('puppeteer-core');
const path = require('path');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const ROOT = path.resolve(__dirname, '..');
(async () => {
  const browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: 'new',
    defaultViewport: { width: 1000, height: 1100, deviceScaleFactor: 2 },
    args: ['--disable-gpu', '--no-first-run'],
  });
  const page = await browser.newPage();
  await page.goto('file:///' + path.join(ROOT, 'docs', 'design', 'mobile-localsend.html').replace(/\\/g, '/'), {
    waitUntil: 'load',
    timeout: 30000,
  });
  await new Promise((r) => setTimeout(r, 800));
  await page.screenshot({
    path: path.join(ROOT, 'docs', 'design', 'mobile-localsend-design.png'),
    fullPage: true,
  });
  const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
  console.log('saved', size);
  await browser.close();
})();
