# Aster 官网

Aster · 星流 的静态官网：零依赖、纯 HTML / CSS / JS，可整目录上传到阿里云 OSS 静态网站托管、GitHub Pages 或任意静态服务器。

- 线上域名：<https://asterdrop.cn>
- 源码仓库：<https://github.com/JASON-SHEN-0225/Aster>
- 下载页：`download.html`（`/download/` 有一页跳转兜底）
- 中英双语、深色 / 浅色 / 跟随系统三态主题、动效尊重 `prefers-reduced-motion`
- 视觉沿用软件：`#2E7CF6` 蓝 → `#13B99F` 薄荷渐变，深色底 `#0F1522` / 浅色底 `#F4F7FB`
- 全站部署体积约 **0.8 MB**（7 张 WebP 截图 + OG 图），无外部字体、无 CDN 依赖

## 目录

```text
website/
├── index.html                落地页
├── download.html             下载页（按钮由 config 驱动）
├── download/index.html       /download/ 跳转到 /download.html
├── 404.html                  OSS 默认 404 页（样式内联，任意路径可访问）
├── LICENSE.txt               MIT 许可
├── robots.txt / sitemap.xml / site.webmanifest
├── assets/
│   ├── css/style.css         设计令牌与全部样式
│   ├── js/config.js          ★ 站点配置：版本、下载地址、联系方式
│   ├── js/i18n.js            中英词典与切换逻辑
│   ├── js/site.js            主题、动效、界面切换、下载卡片渲染
│   └── img/                  WebP 截图、图标、OG 图
├── releases/                 安装包放这里（默认不启用）
├── preview/                  验收截图（可不上传）
├── tools/make_assets.py      从项目截图重新生成图片素材
├── tools/check-site.js       自检：i18n 键覆盖、重复 id、资源引用
├── tools/cdp-shot.js         开发用：无头 Edge 截图 / 布局诊断
└── README.md
```

## 本地预览

```powershell
# 在项目根目录
python -m http.server 8080 -d website
# 打开 http://127.0.0.1:8080/
```

不要用 `file://` 直接打开 `download.html`：校验值通过 `fetch()` 读取，`file://` 下会被浏览器拦截（页面会优雅降级成「上传后自动显示」）。

预览参数（不影响已保存的偏好）：

- `?theme=dark` / `?theme=light` / `?theme=auto`
- `?lang=zh` / `?lang=en`

例如 `http://127.0.0.1:8080/?theme=light&lang=en`。这也方便把英文版链接直接发给别人。

## 部署到阿里云 OSS

1. **Bucket**：建议与 `asterdrop.cn` 同地域。如用中国大陆地域，域名必须完成 ICP 备案。
2. **基础设置 → 静态页面**：
   - 默认首页：`index.html`
   - 默认 404 页：`404.html`
3. **域名管理**：绑定 `asterdrop.cn`（CNAME 到 Bucket 外网域名），在阿里云 SSL 证书服务申请证书并上传，开启 HTTPS。
4. **上传**：把 `website/` 里的内容上传到 Bucket 根目录（`README.md`、`tools/`、`preview/` 可选不上传）。

```powershell
# ossutil 示例（先 ossutil config 配好 AK/SK）
ossutil cp -r website/ oss://你的bucket/ -f
```

5. **Content-Type**：OSS 会按扩展名推断，确认 `.webp = image/webp`、`.js = application/javascript`、`.svg = image/svg+xml`。
6. **缓存建议**：
   - `*.html`、`site.webmanifest`：`Cache-Control: public, max-age=300`
   - `assets/*`：`Cache-Control: public, max-age=86400`（文件名不带哈希，别设一年）
   - 更新后如果仍是旧样式，在控制台刷新 OSS / CDN 缓存。
7. **CORS**：不需要。页面没有任何跨域请求，`fetch('releases/SHA256SUMS.txt')` 是同源读取。

> `download/index.html` 依赖 OSS 对子目录 `index.html` 的解析；即使不生效，`download.html` 本身始终可用。

## 上线前只改一个文件：`assets/js/config.js`

```js
base: "",                     // 留空 = 下载按钮显示「即将开放」
files: {
  setup: { name: "Aster-Setup-2.0.0.exe", url: "", size: "70 MB" },
  ...
}
```

三种填法：

| 场景 | 配置 |
|---|---|
| 安装包跟网站放同一个 Bucket | `base: "releases/"`，文件传到 `releases/` 目录 |
| 安装包放在独立 OSS / CDN 域名 | `base: "https://dl.asterdrop.cn/"`（结尾必须有斜杠） |
| 只给某个文件单独指定链接 | 给该文件填 `url: "https://..."`，优先级高于 `base` |

校验值：把 `SHA256SUMS.txt` 放在与文件相同的目录并上传，页面会自动读取并显示；也可以直接写死 `sha256` 字段。

任意一个文件链接为空时，对应卡片保持「即将开放」状态，不会出现死链或 404；页面顶部会显示「安装包正在上传」的提示，链接填好后自动消失。

## 改内容

| 想改什么 | 去哪儿 |
|---|---|
| 版本号、下载地址、GitHub、邮箱 | `assets/js/config.js` |
| 文案（中文 / 英文） | `assets/js/i18n.js` 的 `DICT.zh` / `DICT.en` |
| 配色、圆角、间距、动效 | `assets/css/style.css` 顶部 `:root` 令牌 |
| 截图 / 图标 / OG 图 | 换掉 `docs/screenshots/` 或 `assets/aster.png` 后运行 `python website/tools/make_assets.py` |
| 下载页卡片、安装步骤、系统要求 | `download.html` + 对应 i18n 键 |

新增文案时，两个词典都要加键；页面里写 `data-i18n="your.key"` 即可。属性翻译用 `data-i18n-attr="aria-label:your.key"`。

改完跑一遍自检：

```powershell
node website/tools/check-site.js
```

会检查：中英词典键是否对齐、HTML 用到的键是否都存在、重复 id、资源文件是否存在。

## 视觉回归 / 布局诊断

`tools/cdp-shot.js` 用无头 Edge + CDP 截图，零第三方依赖：

```powershell
node website/tools/cdp-shot.js --url http://127.0.0.1:8080/ --w 390 --h 844 --dpr 2 --out mobile.png --scroll "#mobile" --diag
node website/tools/cdp-shot.js --url http://127.0.0.1:8080/?theme=light\&lang=en --w 1440 --h 900 --out light-en.png
node website/tools/cdp-shot.js --url http://127.0.0.1:8080/download.html --w 1440 --h 900 --out dl.png --click ".gallery-tabs button:nth-child(2)" --wait 1500
```

支持 `--full` 整页截图、`--diag` 输出布局尺寸、`--click` / `--eval` 做交互检查，并会打印页面 JS 报错。

## 发布新版本时

1. 改 `config.js`：`version`、`versionLabel`、`files.*.name`。
2. 把新安装包放进 `releases/`（或对应 CDN），重新生成 `SHA256SUMS.txt`。
3. 同步改 `download.html` 里两处硬编码的示例文件名（`Aster-Setup-2.0.0.exe`）和 `dlSteps.s1d` 文案。
4. 删除旧版本文件，避免域名下留存过期安装包。
5. 更新 `download.html` 的更新日志与 `og.png`（如果需要）。

## 图片素材

```powershell
python website/tools/make_assets.py
```

- 从 `docs/screenshots/*.png` 生成 WebP（GUI 1160 × 780、手机 780 × 1688）；
- 从 `assets/aster.png` 生成 favicon（16 / 32 / 48 / 64 的 `.ico`）、`icon-*.png`、`apple-touch-icon`；
- 生成 1200 × 630 的 `og.png`（社交分享卡片）。

## 设计与可访问性

- 深色 / 浅色两套令牌都检查过正文对比度：浅色下的薄荷小字用 `--mint-ink: #0B7F70`（4.56:1），三级文字用 `#5F6E84`（4.83:1）。
- 所有动画都走 `transform` / `opacity`；`prefers-reduced-motion` 下自动关闭。
- 无 JS 时内容仍然可读（`html:not(.js) .reveal` 直接显示），但主题、双语、下载卡片状态不可用。
- 图片懒加载；订阅号 / 社交平台抓取 OG 图时不会执行 JS，分享卡片固定为中文深色版。

## 已知取舍

- OG 图是静态中文标题，英文分享卡片不会自动切换（社交平台抓取不支持运行时替换）。
- 404 页样式内联，避免 OSS 在任意路径返回 404 时相对资源路径失效。
- 安装包默认不随站点提供（`base` 为空），需要手动上传并填链接；`releases/README.txt` 里有步骤。
