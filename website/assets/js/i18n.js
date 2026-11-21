/* ==========================================================================
   Aster 官网 · 中英双语
   - 默认中文，选择记在 localStorage
   - [data-i18n] 文本节点 / [data-i18n-attr] 属性 / [data-i18n-caption] 图片说明
   - 通过 window.AsterI18n.t() 取词，切换语言时触发 aster:lang 事件
   ========================================================================== */

(function () {
  "use strict";

  var STORAGE_KEY = "aster.lang";

  var DICT = {
    zh: {
      "meta.title": "Aster · 星流 — 局域网文件互传，快而克制",
      "meta.desc":
        "Aster · 星流是自研协议的局域网文件互传工具。电脑与手机在同一 Wi-Fi 下直连互传，零中转、零账号、零上传，支持断点续传与 SHA-256 校验。",
      "meta.dlTitle": "下载 Aster 2.0.0 · Windows 安装包 / 免安装版 / Android",
      "meta.dlDesc":
        "下载 Aster · 星流 2.0.0：Windows 安装包、免安装 GUI、命令行版与 Android APK。免运行库，安装即用。",

      "nav.features": "功能",
      "nav.how": "怎么用",
      "nav.speed": "速度",
      "nav.mobile": "手机端",
      "nav.security": "隐私",
      "nav.download": "下载",
      "nav.theme": "切换主题",
      "nav.lang": "切换语言",
      "nav.menu": "打开菜单",
      "theme.dark": "深色",
      "theme.light": "浅色",
      "theme.auto": "跟随系统",
      "nav.featuresAria": "功能",
      "nav.howAria": "怎么用",
      "nav.speedAria": "传输速度",
      "nav.mobileAria": "手机端",
      "nav.securityAria": "隐私与安全",
      "nav.downloadAria": "下载 Aster",

      "hero.badge": "v{v} · 自研局域网协议",
      "hero.line1": "把文件，",
      "hero.line2": "交给星流。",
      "hero.lead":
        "同一 Wi-Fi 下，电脑与手机之间直接互传。没有云、没有账号、没有上传，只有你和你的设备。",
      "hero.cta1": "下载 Windows 版",
      "hero.cta2": "手机怎么连",
      "hero.spec1": "Windows 10 / 11",
      "hero.spec2": "Android / 网页",
      "hero.spec3": "MIT 开源",
      "hero.note": "安装包 70 MB · 免安装版 46 MB · 不需要任何运行库",
      "hero.scroll": "向下滚动",

      "float.pc": "客厅电脑",
      "float.pcSub": "192.168.3.181:47820 · 在线",
      "float.phone": "Pixel 8",
      "float.phoneSub": "手机网页 · 已配对",
      "float.hash": "SHA-256 已校验",
      "transfer.name": "家庭视频集.zip",
      "transfer.meta": "1.2 GB · 3 个文件",
      "transfer.speed": "782 MiB/s",
      "transfer.hash": "SHA-256 校验",

      "marquee.1": "局域网直连",
      "marquee.2": "自研协议",
      "marquee.3": "UDP 多播发现",
      "marquee.4": "断点续传",
      "marquee.5": "SHA-256 校验",
      "marquee.6": "HTTP / HTTPS 双端口",
      "marquee.7": "扫码即用",
      "marquee.8": "无账号 · 无云端",

      "features.label": "能力",
      "features.title": "复杂留给自己，简单留给你。",
      "features.desc":
        "从发现、配对到分片和校验，Aster 把每一步都自己走完，界面上只留你要做的那一下。",

      "f1.title": "零中转，数据不出局域网",
      "f1.desc":
        "文件从这台设备直接到那台，不经过任何服务器。就算外网断了，只要两台机器还在同一个 Wi-Fi，传输照常继续。",
      "f1.t1": "点对点",
      "f1.t2": "无云端",

      "f2.title": "手机扫码，开箱即用",
      "f2.desc":
        "电脑上点开二维码，手机扫一下就能进入网页版。不用装 App，也不用注册账号，配对码只有 6 位。",
      "f2.t1": "6 位配对码",
      "f2.t2": "添加到主屏幕",

      "f3.title": "大文件，从从容容",
      "f3.desc":
        "多文件排队、文件夹递归、断点续传。写入时先用 .part 临时分片，校验通过才移动到接收目录。",
      "f3.demo": "74% · 断点续传已开启",

      "f4.title": "每个字节都有回执",
      "f4.desc":
        "传输结束自动做 SHA-256 校验，不匹配就明说。接收文件还会清洗路径，不会写出接收目录。",
      "f4.t1": "SHA-256",
      "f4.t2": "路径穿越清洗",

      "f5.title": "三种形态，各取所需",
      "f5.desc":
        "图形界面、命令行面板、手机网页与 Android APK，共用同一份配置、历史与下载目录。",
      "f5.t1": "GUI",
      "f5.t2": "CLI / TUI",
      "f5.t3": "Web / APK",

      "how.label": "上手",
      "how.title": "三步，从这台到那台。",
      "how.desc": "不用建群、不用登录，也不用先把文件传到谁的服务器。",
      "s1.title": "在两台设备上运行 Aster",
      "s1.desc": "电脑双击 Aster.exe，手机扫二维码打开网页。同一个 Wi-Fi 下会自动发现彼此。",
      "s2.title": "选设备，拖文件",
      "s2.desc":
        "把文件或文件夹拖进窗口，点一下对面设备的卡片，再点发送。资源管理器右键也能直接入队。",
      "s3.title": "对方确认，收工",
      "s3.desc": "接收方确认后开始传输，进度、速度和剩余时间实时显示，完成后自动校验。",

      "speed.label": "实测",
      "speed.title": "局域网里，速度不该将就。",
      "speed.desc":
        "本机 loopback、1 GiB 与 4 GiB 文件、逐字节 SHA-256 校验之后的实测结果。",
      "speed.cardLabel": "峰值吞吐 · HTTP",
      "speed.cardDesc": "1 GiB 单文件，1.31 秒完成",
      "speed.foot": "同一张网卡，HTTPS 慢约 34–39%。要加密选 HTTPS，要极限速度就保持 HTTP。",
      "speed.copy1":
        "传输层自己分片、自己校验，控制流和文件流分开走。进度、速度和剩余时间都是从真实写入量算出来的，不是估算。",
      "speed.copy2":
        "多文件按队列顺序发送，单个大文件流式读写，内存占用不随文件大小增长。4 GiB 的包也不会把内存吃满。",
      "speed.note":
        "loopback 是上限测试。真实 Wi-Fi 还会受路由器、频段、隔墙和 AP 隔离影响，速度会低不少。",

      "mobile.label": "手机端",
      "mobile.title": "电脑托管网页，扫码就能用。",
      "mobile.desc":
        "不用装 App：网页版由你电脑上的 Aster 直接托管。想要更固定的入口，也可以装可选的 Android APK 壳。",
      "m1.title": "打开二维码",
      "m1.desc": "电脑左下角「手机网页 → 二维码」，或在命令行面板按 6。",
      "m2.title": "扫码或输配对码",
      "m2.desc": "首次进入会要求 6 位配对码，配对后就能收发；HTTP / HTTPS 两个端口同时在线。",
      "m3.title": "添加到主屏幕",
      "m3.desc":
        "浏览器菜单里「添加到主屏幕」即可当快捷方式；局域网 HTTP 下浏览器不会注册完整 Service Worker，但不影响收发。",
      "mobile.note":
        "HTTPS 使用自动生成的自签名证书，首次访问点「高级 → 继续访问」即可，不需要装 CA。",
      "mobile.badge": "扫码即用",
      "mobile.badgeSub": "无需安装 App",
      "tab.home": "首页",
      "tab.upload": "上传中",
      "tab.offer": "电脑发来",

      "gallery.label": "界面",
      "gallery.title": "克制的界面，清楚的进度。",
      "gallery.desc": "浅色与深色都做了完整适配，主题跟着系统走，也可以手动锁定。",
      "gallery.light": "浅色",
      "gallery.dark": "深色",
      "gallery.captionsend": "发送页 · 星轨、设备卡片与拖拽区",
      "gallery.captiondark": "深色主题 · 同一套布局，夜间不刺眼",
      "gallery.captiondevices": "设备选择 · 自动发现局域网内的电脑与手机",
      "gallery.captionsettings": "设置页 · HTTPS、自动接受与开机自启",
      "thumb.send": "发送",
      "thumb.devices": "设备",
      "thumb.settings": "设置",

      "sec.label": "隐私",
      "sec.title": "没有云，没有账号，没有上传。",
      "sec.desc":
        "Aster 只做一件事：把文件从 A 送到 B，然后忘掉它。配置、历史、证书都留在你自己的机器上。",
      "sec1.title": "只在局域网工作",
      "sec1.desc": "UDP 多播发现、TCP 直连传输，不做公网映射就不会出内网。",
      "sec2.title": "配对码 + 可选 PIN",
      "sec2.desc":
        "手机网页需要 6 位配对码；电脑之间默认需要接收方确认，也可以设置 PIN 或自动接受。",
      "sec3.title": "传输全程可校验",
      "sec3.desc": "大文件先写 .part，SHA-256 通过后才移动到接收目录。",
      "sec4.title": "HTTPS 可选",
      "sec4.desc":
        "自签名证书加密传输，不做 CA 链校验；需要时打开，不需要就保持 HTTP 全速。",
      "sec.warn":
        "请只在可信 Wi-Fi 使用 Aster，不要把 47820 / 47821 端口映射到公网。",

      "faq.label": "常见问题",
      "faq.title": "你可能想知道的。",
      "q1": "手机打不开网页？",
      "a1":
        "确认手机与电脑在同一个 Wi-Fi；以管理员身份运行 install-firewall.bat，放行 TCP 47820/47821 与 UDP 47820；在路由器里关闭「AP 隔离 / 客户端隔离」；用 AsterCLI.exe info 查看本机 IP 和端口。",
      "q2": "电脑之间发现不到？",
      "a2": "命令行面板按 7 手动输入 IP:端口，或点 GUI 的「连接 IP」；两台电脑都要运行 Aster。",
      "q3": "HTTPS 提示不安全？",
      "a3": "自签名证书的正常提示，点「高级 → 继续访问」即可，不需要在设备上安装 CA。",
      "q4": "能跟 LocalSend 互传吗？",
      "a4":
        "不能。Aster 是完全自研的协议，只在设计思想上参考了「局域网发现 + 点对点传输」。",
      "q5": "关掉 GUI 传输会断吗？",
      "a5": "不会。关窗默认缩到系统托盘，传输继续；托盘菜单里「退出」才真正停止。",

      "cta.title": "现在，把文件交给星流。",
      "cta.desc": "Windows 安装包、免安装版、命令行版，以及可选的 Android APK，都已经准备好了。",
      "cta.button": "前往下载",
      "cta.ghost": "在 GitHub 查看源码",
      "cta.meta": "v{v} · Windows 10 1809+ · Android 8.0+ · MIT",

      "footer.tagline":
        "Aster · 星流，自研协议的局域网文件互传套件。把文件，交给星流。",
      "footer.product": "产品",
      "footer.resources": "资源",
      "footer.contact": "联系",
      "footer.features": "功能",
      "footer.download": "下载",
      "footer.mobile": "手机端",
      "footer.faq": "常见问题",
      "footer.github": "GitHub",
      "footer.changelog": "更新日志",
      "footer.mail": "邮件",
      "footer.license": "MIT 许可",
      "footer.note": "个人项目 · 不收集任何数据",
      "footer.rights": "© {year} Aster · 星流",
      "footer.made": "用 PySide6 与原生 Web 写成",

      "dlPage.title": "下载 Aster",
      "dlPage.desc": "挑一个适合你的形态。所有版本共用同一套协议，可以互相发现、互传。",
      "dlPage.chip1": "最新版本 v{v}",
      "dlPage.chip2": "MIT 开源",
      "dlPage.chip3": "免运行库依赖",
      "dlPage.notice":
        "安装包正在上传，下载按钮暂时不可用。源码现在就能在 GitHub 获取，页面上的校验值会随文件一起生效。",
      "dlPage.section1": "Windows",
      "dlPage.section1sub": "推荐安装包 · 防火墙规则、快捷方式与卸载一次到位",
      "dlPage.section2": "其他形态",
      "dlPage.section2sub": "免安装、命令行与 Android",
      "setup.title": "Windows 安装包",
      "setup.desc":
        "把 GUI、CLI、启动脚本、防火墙规则、右键菜单和卸载做进一个标准安装包，装完就能用。",
      "gui.title": "免安装 GUI",
      "gui.desc": "解压即用，双击 Aster.exe 启动图形界面，不写系统目录。",
      "cli.title": "命令行版",
      "cli.desc": "5 行 ASCII 大标题的交互面板，同时支持完整子命令。",
      "apk.title": "Android APK",
      "apk.desc": "WebView 壳，连接电脑上的 Aster 使用；适合想固定入口的用户。",
      "dl.recommended": "推荐",
      "dl.optional": "可选",
      "dl.version": "版本",
      "dl.size": "大小",
      "dl.system": "系统",
      "dl.runtime": "运行库",
      "dl.runtimeNone": "不需要",
      "dl.requires": "Windows 10 1809+ / 11 · 64 位 · 需要管理员权限",
      "dl.systemWin": "Windows 10 / 11 · x64",
      "dl.systemWinPortable": "Windows 10 / 11 · 免安装",
      "dl.systemApk": "Android 8.0+",
      "dl.download": "下载",
      "dl.pending": "即将开放",
      "dl.github": "从 GitHub 获取源码",
      "dl.hash": "SHA-256",
      "dl.hashPending": "上传后自动显示",
      "dl.copy": "复制",
      "dl.copied": "已复制",
      "dl.availableSoon": "安装包上传后自动启用",

      "dlSteps.title": "安装只要三步",
      "dlSteps.label": "安装",
      "dlSteps.s1t": "下载并运行安装包",
      "dlSteps.s1d": "双击 Aster-Setup-2.0.0.exe，UAC 提示点「是」。",
      "dlSteps.s2t": "按向导下一步",
      "dlSteps.s2d": "默认装到 C:\\Program Files\\Aster，可取消文档与桌面快捷方式。",
      "dlSteps.s3t": "开始传输",
      "dlSteps.s3d": "防火墙规则由安装器自动写入；首次运行也能手动运行 install-firewall.bat。",

      "warn.title": "没有代码签名，这是正常的",
      "warn.body":
        "项目没有代码签名证书，也不伪造签名。SmartScreen 可能提示「未知发布者」——点「更多信息 → 仍要运行」即可。下载后建议核对 SHA-256。",
      "verify.title": "校验下载",
      "verify.body": "在 PowerShell 里计算文件哈希，与下载卡上的 SHA-256 对比：",
      "verify.note": "一致再进行安装。页面上的校验值来自官方构建目录的 SHA256SUMS.txt。",
      "req.title": "系统要求",
      "req.os": "操作系统",
      "req.osVal": "Windows 10 1809+ / Windows 11，64 位",
      "req.arch": "架构",
      "req.archVal": "x64",
      "req.perm": "权限",
      "req.permVal": "安装需要管理员权限（UAC）；免安装版不需要",
      "req.runtime": "运行库",
      "req.runtimeVal": "不需要 Python、Node.js 或任何运行库",
      "req.port": "端口",
      "req.portVal": "TCP 47820（HTTP）· TCP 47821（HTTPS）· UDP 47820（发现）",
      "req.android": "Android",
      "req.androidVal": "8.0（API 26）及以上；网页版任意现代浏览器",
      "changelog.title": "2.0.0 里有什么",
      "changelog.1": "全新界面：星轨首页、设备卡片、深色主题与手机网页版。",
      "changelog.2": "Windows 安装包：快捷方式、右键菜单、防火墙规则、卸载全自动。",
      "changelog.3": "HTTPS 双端口：47820 / 47821 同时监听，切换不用重启。",
      "changelog.4": "断点续传、文件夹递归与逐文件 SHA-256 校验。",
      "changelog.5": "Android APK：连接页、扫码、文件选择与自签名证书确认。",
      "backHome": "返回首页",
    },

    en: {
      "meta.title": "Aster — Local file transfer, fast and restrained",
      "meta.desc":
        "Aster is a LAN file-transfer suite with its own protocol. PCs and phones transfer directly on the same Wi-Fi — no relay, no account, no uploads — with resume and SHA-256 verification.",
      "meta.dlTitle": "Download Aster 2.0.0 — Windows installer, portable, Android",
      "meta.dlDesc":
        "Download Aster 2.0.0: Windows installer, portable GUI, command line and Android APK. No runtime required.",

      "nav.features": "Features",
      "nav.how": "How it works",
      "nav.speed": "Speed",
      "nav.mobile": "Mobile",
      "nav.security": "Privacy",
      "nav.download": "Download",
      "nav.theme": "Toggle theme",
      "nav.lang": "Switch language",
      "nav.menu": "Open menu",
      "theme.dark": "Dark",
      "theme.light": "Light",
      "theme.auto": "Match system",
      "nav.featuresAria": "Features",
      "nav.howAria": "How it works",
      "nav.speedAria": "Transfer speed",
      "nav.mobileAria": "Mobile",
      "nav.securityAria": "Privacy and security",
      "nav.downloadAria": "Download Aster",

      "hero.badge": "v{v} · LAN-native protocol",
      "hero.line1": "Your files,",
      "hero.line2": "to the stars.",
      "hero.lead":
        "Direct transfers between your PC and phone on the same Wi-Fi. No cloud, no account, no uploads — just you and your devices.",
      "hero.cta1": "Download for Windows",
      "hero.cta2": "How mobile works",
      "hero.spec1": "Windows 10 / 11",
      "hero.spec2": "Android / Web",
      "hero.spec3": "MIT licensed",
      "hero.note": "70 MB installer · 46 MB portable · no runtime required",
      "hero.scroll": "scroll",

      "float.pc": "Living room PC",
      "float.pcSub": "192.168.3.181:47820 · online",
      "float.phone": "Pixel 8",
      "float.phoneSub": "Mobile web · paired",
      "float.hash": "SHA-256 verified",
      "transfer.name": "family-videos.zip",
      "transfer.meta": "1.2 GB · 3 files",
      "transfer.speed": "782 MiB/s",
      "transfer.hash": "SHA-256 check",

      "marquee.1": "LAN direct",
      "marquee.2": "own protocol",
      "marquee.3": "UDP discovery",
      "marquee.4": "resume support",
      "marquee.5": "SHA-256",
      "marquee.6": "HTTP / HTTPS",
      "marquee.7": "scan to pair",
      "marquee.8": "no account · no cloud",

      "features.label": "CAPABILITIES",
      "features.title": "Complex inside. Simple outside.",
      "features.desc":
        "Discovery, pairing, chunking and verification are all handled in-house, so the interface only asks for the one thing you need to do.",

      "f1.title": "Zero relay — data never leaves your LAN",
      "f1.desc":
        "Files travel straight from one device to another with no server in between. Even with the internet down, transfers keep working on the same Wi-Fi.",
      "f1.t1": "peer-to-peer",
      "f1.t2": "no cloud",

      "f2.title": "Scan once, ready to go",
      "f2.desc":
        "Open the QR code on your PC, scan it, and the mobile web app is there. No app install, no sign-up, just a 6-digit pairing code.",
      "f2.t1": "6-digit pairing",
      "f2.t2": "home-screen shortcut",

      "f3.title": "Big files, no drama",
      "f3.desc":
        "Queues, recursive folders and resume. Data lands in .part chunks first and only moves into the download folder after verification.",
      "f3.demo": "74% · resume enabled",

      "f4.title": "Every byte accounted for",
      "f4.desc":
        "SHA-256 is checked after every transfer, and mismatches are reported plainly. Incoming paths are sanitised so nothing escapes the download folder.",
      "f4.t1": "SHA-256",
      "f4.t2": "path sanitising",

      "f5.title": "Three shapes, one protocol",
      "f5.desc":
        "GUI, terminal panel, mobile web and Android APK all share the same config, history and download folder.",
      "f5.t1": "GUI",
      "f5.t2": "CLI / TUI",
      "f5.t3": "Web / APK",

      "how.label": "GETTING STARTED",
      "how.title": "Three steps, one device to another.",
      "how.desc": "No group chat, no login, and no uploading to somebody else's server first.",
      "s1.title": "Run Aster on both devices",
      "s1.desc":
        "Double-click Aster.exe on the PC, scan the QR code on your phone. Devices on the same Wi-Fi discover each other automatically.",
      "s2.title": "Pick a device, drop files",
      "s2.desc":
        "Drag files or folders in, click the target device, hit send. The Explorer right-click menu can queue files too.",
      "s3.title": "They accept, you're done",
      "s3.desc":
        "Transfers start once the receiver confirms. Progress, speed and ETA are live; verification runs at the end.",

      "speed.label": "BENCHMARK",
      "speed.title": "On a LAN, speed shouldn't compromise.",
      "speed.desc":
        "Measured on loopback with 1 GiB and 4 GiB files, verified byte for byte with SHA-256.",
      "speed.cardLabel": "Peak throughput · HTTP",
      "speed.cardDesc": "1 GiB single file in 1.31 s",
      "speed.foot":
        "On the same NIC, HTTPS is ~34–39% slower. Choose HTTPS for encryption, keep HTTP for top speed.",
      "speed.copy1":
        "The transport layer does its own chunking and verification, with control and file streams kept separate. Progress, speed and ETA are computed from actual writes, not guesses.",
      "speed.copy2":
        "Queued files are sent in order and large ones are streamed, so memory use does not grow with file size. A 4 GiB archive won't fill your RAM.",
      "speed.note":
        "Loopback is a ceiling test. Real Wi-Fi is limited by routers, bands, walls and AP isolation, so expect lower numbers.",

      "mobile.label": "ON YOUR PHONE",
      "mobile.title": "Served by your PC. Scan and go.",
      "mobile.desc":
        "No app required: the mobile site is hosted by Aster on your computer. Prefer a fixed entry point? Install the optional Android APK shell.",
      "m1.title": "Open the QR code",
      "m1.desc": "On the PC, click “Mobile web → QR code”, or press 6 in the terminal panel.",
      "m2.title": "Scan or enter the code",
      "m2.desc":
        "The first visit asks for a 6-digit pairing code. After that you can send and receive, with HTTP and HTTPS listening side by side.",
      "m3.title": "Add to home screen",
      "m3.desc":
        "Use “Add to home screen” in the browser menu for a shortcut. Over plain LAN HTTP the browser won't register a full service worker, but transfers still work.",
      "mobile.note":
        "HTTPS uses a self-signed certificate. On first visit choose “Advanced → Proceed”; no CA install needed.",
      "mobile.badge": "scan & go",
      "mobile.badgeSub": "no app needed",
      "tab.home": "Home",
      "tab.upload": "Uploading",
      "tab.offer": "Incoming",

      "gallery.label": "INTERFACE",
      "gallery.title": "A quiet interface with clear progress.",
      "gallery.desc":
        "Both light and dark themes are fully covered. The site follows your system setting, and you can lock it either way.",
      "gallery.light": "Light",
      "gallery.dark": "Dark",
      "gallery.captionsend": "Send view · star trail, device cards and drop zone",
      "gallery.captiondark": "Dark theme · same layout, easier at night",
      "gallery.captiondevices": "Devices · automatic discovery on your LAN",
      "gallery.captionsettings": "Settings · HTTPS, auto-accept and launch at login",
      "thumb.send": "Send",
      "thumb.devices": "Devices",
      "thumb.settings": "Settings",

      "sec.label": "PRIVACY",
      "sec.title": "No cloud. No account. No uploads.",
      "sec.desc":
        "Aster does one thing: move a file from A to B, then forget about it. Config, history and certificates stay on your own machine.",
      "sec1.title": "LAN only, by design",
      "sec1.desc": "UDP multicast discovery and direct TCP transfers. No port forwarding, no internet round-trip.",
      "sec2.title": "Pairing code + optional PIN",
      "sec2.desc":
        "The mobile web app needs a 6-digit code. PC-to-PC transfers ask the receiver by default; you can set a PIN or auto-accept.",
      "sec3.title": "Verifiable transfers",
      "sec3.desc": "Large files go to .part chunks first and only move into place after SHA-256 passes.",
      "sec4.title": "Optional HTTPS",
      "sec4.desc":
        "A self-signed certificate encrypts traffic without CA chain validation. Turn it on when needed, keep HTTP for full speed otherwise.",
      "sec.warn": "Use Aster only on Wi-Fi you trust, and never forward ports 47820 / 47821 to the internet.",

      "faq.label": "FAQ",
      "faq.title": "Things you might ask.",
      "q1": "The phone can't open the page?",
      "a1":
        "Make sure both are on the same Wi-Fi. Run install-firewall.bat as administrator to allow TCP 47820/47821 and UDP 47820. Turn off AP isolation / client isolation on the router. Use AsterCLI.exe info to check the IP and ports.",
      "q2": "PCs don't discover each other?",
      "a2": "Press 7 in the terminal panel to enter IP:port manually, or click “Connect IP” in the GUI. Aster must be running on both machines.",
      "q3": "Why does HTTPS warn?",
      "a3": "That's the normal warning for a self-signed certificate. Choose “Advanced → Proceed”; no CA install is needed.",
      "q4": "Does it work with LocalSend?",
      "a4": "No. Aster uses its own protocol, inspired only by the idea of LAN discovery plus peer-to-peer transfer.",
      "q5": "Does closing the GUI stop transfers?",
      "a5": "No. Closing the window hides it to the tray and transfers continue. Use “Quit” in the tray menu to actually stop.",

      "cta.title": "Hand your files to the starlight.",
      "cta.desc": "The Windows installer, portable build, command line and optional Android APK are ready for you.",
      "cta.button": "Go to downloads",
      "cta.ghost": "View the source on GitHub",
      "cta.meta": "v{v} · Windows 10 1809+ · Android 8.0+ · MIT",

      "footer.tagline":
        "Aster is a LAN file-transfer suite with its own protocol. Hand your files to the starlight.",
      "footer.product": "Product",
      "footer.resources": "Resources",
      "footer.contact": "Contact",
      "footer.features": "Features",
      "footer.download": "Download",
      "footer.mobile": "Mobile",
      "footer.faq": "FAQ",
      "footer.github": "GitHub",
      "footer.changelog": "Changelog",
      "footer.mail": "Email",
      "footer.license": "MIT license",
      "footer.note": "a personal project · no data collected",
      "footer.rights": "© {year} Aster",
      "footer.made": "built with PySide6 and plain web tech",

      "dlPage.title": "Download Aster",
      "dlPage.desc": "Pick the shape that fits. Every build speaks the same protocol and can find each other.",
      "dlPage.chip1": "latest v{v}",
      "dlPage.chip2": "MIT licensed",
      "dlPage.chip3": "no runtime",
      "dlPage.notice":
        "The installers are still being uploaded, so the download buttons are disabled for now. The source is already on GitHub, and checksums will go live with the files.",
      "dlPage.section1": "Windows",
      "dlPage.section1sub": "Recommended · firewall rules, shortcuts and uninstall handled",
      "dlPage.section2": "Other builds",
      "dlPage.section2sub": "portable, command line and Android",
      "setup.title": "Windows installer",
      "setup.desc":
        "GUI, CLI, launch scripts, firewall rules, right-click menu and uninstall in one standard Windows installer.",
      "gui.title": "Portable GUI",
      "gui.desc": "Unzip and run Aster.exe. Nothing is written to system folders.",
      "cli.title": "Command line",
      "cli.desc": "An interactive panel with a 5-line ASCII banner, plus full subcommands.",
      "apk.title": "Android APK",
      "apk.desc": "A WebView shell that connects to Aster on your PC. Good if you want a fixed entry point.",
      "dl.recommended": "recommended",
      "dl.optional": "optional",
      "dl.version": "version",
      "dl.size": "size",
      "dl.system": "system",
      "dl.runtime": "runtime",
      "dl.runtimeNone": "none",
      "dl.requires": "Windows 10 1809+ / 11 · 64-bit · administrator required",
      "dl.systemWin": "Windows 10 / 11 · x64",
      "dl.systemWinPortable": "Windows 10 / 11 · portable",
      "dl.systemApk": "Android 8.0+",
      "dl.download": "Download",
      "dl.pending": "Coming soon",
      "dl.github": "Get the source on GitHub",
      "dl.hash": "SHA-256",
      "dl.hashPending": "shown after upload",
      "dl.copy": "copy",
      "dl.copied": "copied",
      "dl.availableSoon": "enabled once the file is uploaded",

      "dlSteps.title": "Three steps to install",
      "dlSteps.label": "INSTALL",
      "dlSteps.s1t": "Download and run",
      "dlSteps.s1d": "Double-click Aster-Setup-2.0.0.exe and confirm the UAC prompt.",
      "dlSteps.s2t": "Follow the wizard",
      "dlSteps.s2d": "Installs to C:\\Program Files\\Aster. Docs and the desktop shortcut are optional.",
      "dlSteps.s3t": "Start transferring",
      "dlSteps.s3d": "The installer adds firewall rules. You can also run install-firewall.bat manually.",

      "warn.title": "Unsigned on purpose — that's expected",
      "warn.body":
        "This project has no code-signing certificate and does not fake one. SmartScreen may say “unknown publisher” — choose “More info → Run anyway”. Verify the SHA-256 after downloading.",
      "verify.title": "Verify the download",
      "verify.body": "Compute the hash in PowerShell and compare it with the SHA-256 shown on the card:",
      "verify.note": "Only install if it matches. The checksums come from the official SHA256SUMS.txt.",
      "req.title": "System requirements",
      "req.os": "OS",
      "req.osVal": "Windows 10 1809+ / Windows 11, 64-bit",
      "req.arch": "Architecture",
      "req.archVal": "x64",
      "req.perm": "Permissions",
      "req.permVal": "Administrator for the installer (UAC); not needed for the portable build",
      "req.runtime": "Runtime",
      "req.runtimeVal": "No Python, Node.js or any runtime",
      "req.port": "Ports",
      "req.portVal": "TCP 47820 (HTTP) · TCP 47821 (HTTPS) · UDP 47820 (discovery)",
      "req.android": "Android",
      "req.androidVal": "8.0 (API 26)+; any modern browser for the web app",
      "changelog.title": "What's in 2.0.0",
      "changelog.1": "New interface: star-trail hero, device cards, dark theme and a mobile web app.",
      "changelog.2": "Windows installer: shortcuts, context menu, firewall rules and uninstall.",
      "changelog.3": "Dual HTTPS: 47820 and 47821 listen at once; switching never restarts.",
      "changelog.4": "Resume, recursive folders and per-file SHA-256 verification.",
      "changelog.5": "Android APK: connect page, QR scanning, file picker and self-signed cert handling.",
      "backHome": "Back to home",
    },
  };

  var html = document.documentElement;
  var lang = "zh";

  try {
    var qLang = new URLSearchParams(window.location.search).get("lang");
    if (qLang === "zh" || qLang === "en") {
      lang = qLang;
    } else {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "zh" || stored === "en") lang = stored;
    }
  } catch (err) {
    /* localStorage / URL API 不可用时保持中文 */
  }

  function t(key, vars) {
    var table = DICT[lang] || DICT.zh;
    var fallback = DICT.zh[key] || key;
    var text = table[key] || fallback;
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, function (m, name) {
      return vars[name] != null ? String(vars[name]) : m;
    });
  }

  function vars() {
    var cfg = window.ASTER_CONFIG || {};
    return {
      v: cfg.versionLabel || cfg.version || "2.0.0",
      year: String(new Date().getFullYear()),
      domain: cfg.domain || "asterdrop.cn",
    };
  }

  function applyI18n() {
    html.lang = lang === "zh" ? "zh-CN" : "en";
    html.setAttribute("data-lang", lang);

    var v = vars();

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.dataset.i18n, v);
    });

    document.querySelectorAll("[data-i18n-attr]").forEach(function (el) {
      el.dataset.i18nAttr.split(",").forEach(function (pair) {
        var bits = pair.split(":");
        if (bits.length !== 2) return;
        el.setAttribute(bits[0].trim(), t(bits[1].trim(), v));
      });
    });

    document.querySelectorAll("[data-lang-label]").forEach(function (el) {
      el.textContent = lang === "zh" ? "EN" : "中";
    });

    var titleKey = document.body.getAttribute("data-title-key") || "meta.title";
    var descKey = document.body.getAttribute("data-desc-key") || "meta.desc";
    document.title = t(titleKey, v);

    var desc = document.querySelector('meta[name="description"]');
    if (desc) desc.setAttribute("content", t(descKey, v));

    var ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) ogTitle.setAttribute("content", t(titleKey, v));
    var ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) ogDesc.setAttribute("content", t(descKey, v));

    document.dispatchEvent(
      new CustomEvent("aster:lang", { detail: { lang: lang, t: t, vars: v } })
    );
  }

  function setLang(next) {
    if (next !== "zh" && next !== "en") return;
    lang = next;
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (err) {
      /* ignore */
    }
    applyI18n();
  }

  document.querySelectorAll("[data-lang-btn]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setLang(lang === "zh" ? "en" : "zh");
    });
  });

  window.AsterI18n = {
    t: t,
    apply: applyI18n,
    setLang: setLang,
    getLang: function () {
      return lang;
    },
  };

  applyI18n();
})();
