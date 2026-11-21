/* ==========================================================================
   Aster 官网配置
   --------------------------------------------------------------------------
   上线前只需要改这里：

   1) 安装包放哪儿？
      · 直接跟网站一起放 OSS：把文件上传到站点根目录的 releases/ 里，
        然后 base = "releases/"（相对路径，域名换了也不用改）。
      · 放 CDN / 独立 bucket：base = "https://dl.asterdrop.cn/"（记得结尾斜杠）。
      · 每个文件单独指定：给某一项填 url 即可，url 优先于 base。
      · 链接没填 = 下载按钮显示「即将开放」，不会出现 404。

   2) 校验值
      · 把 SHA256SUMS.txt 放在同一个目录，页面会自动读取并显示（同源 fetch）。
      · 也可以直接写死 sha256（32 位以上都行，页面会截断展示，复制得到完整值）。
   ========================================================================== */

window.ASTER_CONFIG = {
  version: "2.0.0",
  releaseDate: "", // 例如 "2026-12-01"，留空就不显示

  domain: "asterdrop.cn",
  github: "https://github.com/JASON-SHEN-0225/Aster",
  email: "jasonshen0225@163.com",

  // 安装包下载基地址；留空表示全部按下架处理（按钮显示「即将开放」）
  // 注意：当前安装包在 OSS 的 website/releases/ 下（上传时多带了一层 website）
  base: "website/releases/",

  // 校验值文件（相对站点根目录，或绝对 URL）
  sumsUrl: "website/releases/SHA256SUMS.txt",

  files: {
    setup: {
      name: "Aster-Setup-2.0.0.exe",
      url: "",
      size: "48.6 MB",
      sha256: "19b741e7b4f09bc180b96df48447321046578def8f4971059925dcf0f918443e",
      badge: "recommended",
    },
    gui: {
      name: "Aster.exe",
      url: "",
      size: "47 MB",
      sha256: "3b5f69c5b0de0dbff2d205ed7f42e14e229036d3997719350218c7bc51f40df1",
      badge: "",
    },
    apk: {
      name: "Aster-2.0.0-release.apk",
      url: "",
      size: "2.4 MB",
      sha256: "15ef5580ca624900efccac3102ab06e51ef52ed6eabbed45c4db1da592063ea9",
      badge: "optional",
    },
  },

  // 页面上的版本号文本统一从这里来
  versionLabel: "2.0.0",
};
