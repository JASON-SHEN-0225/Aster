/* 官网自检：
   1. HTML 里用到的 i18n 键是否在 zh / en 词典中都存在
   2. 是否有重复 id
   3. 资源引用是否存在

   用法：node website/tools/check-site.js
*/

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const errors = [];
const warnings = [];

function read(file) {
  return fs.readFileSync(path.join(root, file), "utf8");
}

/* ---------------------------------------------------------- 词典解析 */
const i18nSrc = read("assets/js/i18n.js");
const zhStart = i18nSrc.indexOf("zh: {");
const enStart = i18nSrc.indexOf("en: {");
const dictEnd = i18nSrc.lastIndexOf("};");

if (zhStart < 0 || enStart < 0) {
  errors.push("i18n.js: 找不到 zh / en 词典");
}

function keysOf(block) {
  const keys = new Set();
  const re = /^\s*"([^"\n]+)"\s*:/gm;
  let m;
  while ((m = re.exec(block))) keys.add(m[1]);
  return keys;
}

const zhBlock = i18nSrc.slice(zhStart, enStart);
const enBlock = i18nSrc.slice(enStart, dictEnd);
const zhKeys = keysOf(zhBlock);
const enKeys = keysOf(enBlock);

for (const key of zhKeys) {
  if (!enKeys.has(key)) errors.push(`缺少英文翻译: ${key}`);
}
for (const key of enKeys) {
  if (!zhKeys.has(key)) errors.push(`缺少中文翻译: ${key}`);
}

/* --------------------------------------------------------------- HTML */
const pages = ["index.html", "download.html"];
const usedKeys = new Map();

for (const page of pages) {
  const html = read(page);

  const idRe = /\sid="([^"]+)"/g;
  const ids = new Set();
  let m;
  while ((m = idRe.exec(html))) {
    if (ids.has(m[1])) warnings.push(`${page}: 重复 id="${m[1]}"`);
    ids.add(m[1]);
  }

  const keyRe = /data-i18n="([^"]+)"/g;
  while ((m = keyRe.exec(html))) {
    if (!usedKeys.has(m[1])) usedKeys.set(m[1], []);
    usedKeys.get(m[1]).push(page);
  }

  const attrRe = /data-i18n-attr="([^"]+)"/g;
  while ((m = attrRe.exec(html))) {
    m[1].split(",").forEach((pair) => {
      const bits = pair.split(":");
      if (bits.length !== 2) {
        errors.push(`${page}: data-i18n-attr 格式错误 "${pair}"`);
        return;
      }
      const key = bits[1].trim();
      if (!usedKeys.has(key)) usedKeys.set(key, []);
      usedKeys.get(key).push(page);
    });
  }

  const captionRe = /data-caption="([^"]+)"/g;
  while ((m = captionRe.exec(html))) {
    if (!usedKeys.has(m[1])) usedKeys.set(m[1], []);
    usedKeys.get(m[1]).push(page);
  }

  const titleKey = html.match(/data-title-key="([^"]+)"/);
  const descKey = html.match(/data-desc-key="([^"]+)"/);
  [titleKey, descKey].forEach((hit) => {
    if (!hit) {
      errors.push(`${page}: 缺少 data-title-key / data-desc-key`);
      return;
    }
    if (!usedKeys.has(hit[1])) usedKeys.set(hit[1], []);
    usedKeys.get(hit[1]).push(page);
  });

  /* 静态资源引用检查 */
  const srcRe = /(?:src|href)="((?!https?:|mailto:|#|\/\/)[^"]+)"/g;
  while ((m = srcRe.exec(html))) {
    const target = m[1].split("#")[0].split("?")[0];
    if (!target || target.startsWith("data:")) continue;
    const abs = path.resolve(root, target);
    if (!fs.existsSync(abs)) errors.push(`${page}: 资源不存在 -> ${target}`);
  }
}

for (const [key, where] of usedKeys) {
  if (!zhKeys.has(key)) errors.push(`中文词典缺少 "${key}"（${where.join(", ")}）`);
  if (!enKeys.has(key)) errors.push(`英文词典缺少 "${key}"（${where.join(", ")}）`);
}

/* 词典里有、页面没用到的键只提示，不算错；动态拼接的键除外 */
const DYNAMIC_KEYS = new Set([
  "theme.dark",
  "theme.light",
  "theme.auto",
  "dl.download",
  "dl.pending",
  "dl.hashPending",
  "dl.copied",
]);

for (const key of DYNAMIC_KEYS) {
  if (!zhKeys.has(key)) errors.push(`中文词典缺少动态键 "${key}"`);
  if (!enKeys.has(key)) errors.push(`英文词典缺少动态键 "${key}"`);
}

const unused = [...zhKeys].filter((k) => !usedKeys.has(k) && !DYNAMIC_KEYS.has(k));

/* ------------------------------------------------------------- 输出 */
console.log(`中文词典 ${zhKeys.size} 键 · 英文词典 ${enKeys.size} 键`);
console.log(`页面引用 ${usedKeys.size} 键`);
if (unused.length) {
  warnings.push(`未使用的词典键: ${unused.join(", ")}`);
}

for (const w of warnings) console.log("WARN  " + w);

if (errors.length) {
  for (const e of errors) console.error("ERROR " + e);
  process.exit(1);
}

console.log("OK  i18n 与资源引用检查通过");
