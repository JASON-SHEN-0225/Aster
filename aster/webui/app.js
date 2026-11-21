/* ==========================================================================
   Aster · 星流 — 手机端 PWA 逻辑
   纯原生 JS，无构建、无依赖。所有服务端文本均通过 textContent 渲染。
   ========================================================================== */
(() => {
  "use strict";

  /* ------------------------------------------------------------------------
     1. 常量 / 本地存储 / 应用状态
     ------------------------------------------------------------------------ */
  const STORAGE = {
    token: "aster.token",
    webId: "aster.web_id",
    phoneName: "aster.phone_name",
    theme: "aster.theme",
    installDismissed: "aster.install_dismissed",
  };

  const MAX_TEXT = 20000;
  const MAX_FILE_RETRIES = 3;
  const INSTALL_SNOOZE_MS = 30 * 24 * 60 * 60 * 1000;

  const store = {
    get(key) {
      try {
        return window.localStorage.getItem(key);
      } catch (_) {
        return null;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(key, String(value));
      } catch (_) {
        /* 隐私模式下无法写入时静默降级 */
      }
    },
    remove(key) {
      try {
        window.localStorage.removeItem(key);
      } catch (_) {
        /* ignore */
      }
    },
  };

  const app = {
    token: store.get(STORAGE.token) || "",
    webId: store.get(STORAGE.webId) || "",
    phoneName: normalizePhoneName(store.get(STORAGE.phoneName) || ""),
    theme: store.get(STORAGE.theme) === "dark" ? "dark" : "light",
    state: null,
    view: "boot",
    tab: "send",
    sendMode: "files",
    connected: false,
    pairingBusy: false,
    autoPairScheduled: false,
    sse: null,
    sseFailures: 0,
    reconnectTimer: 0,
    reconnectAttempts: 0,
    probeTimer: 0,
    probing: false,
    lastProbeAt: 0,
    pollTimer: 0,
    polling: false,
    lastFrameAt: 0,
    lastConnectionKey: "",
    unauthorizedLock: 0,
    renderRaf: 0,
    renderQueued: false,
    sigs: {},
    offerStatus: new Map(),
    knownOfferIds: new Set(),
    offersInitialized: false,
    offerBusy: new Set(),
    selection: [],
    upload: null,
    uploadRenderTimer: 0,
    uploadClearTimer: 0,
    lastSampleAt: 0,
    autoAcceptBusy: false,
    httpsBusy: false,
    activeSheet: null,
    sheetEpoch: 0,
    lastManualRefresh: 0,
    textExpanded: false,
    themeInitialized: false,
    swRegistered: false,
    install: {
      event: null,
      dismissedUntil: Number(store.get(STORAGE.installDismissed)) || 0,
      bannerTimer: 0,
    },
    disconnectArmedUntil: 0,
    disconnectTimer: 0,
    hasEnteredApp: false,
    lastNetworkOnline: navigator.onLine,
  };

  const ui = {};
  const svgNS = "http://www.w3.org/2000/svg";

  class ClientError extends Error {
    constructor(message, status = 0, data = null) {
      super(message);
      this.name = "ClientError";
      this.status = status;
      this.data = data;
    }
  }

  /* ------------------------------------------------------------------------
     2. DOM 引用
     ------------------------------------------------------------------------ */
  function cacheDom() {
    const byId = (id) => document.getElementById(id);
    Object.assign(ui, {
      bootView: byId("boot-view"),
      pairView: byId("pair-view"),
      appView: byId("app-view"),
      main: byId("main"),
      metaTheme: byId("meta-theme"),
      pairForm: byId("pair-form"),
      pairCode: byId("pair-code"),
      pairName: byId("pair-name"),
      pairSubmit: byId("pair-submit"),
      pairHint: byId("pair-hint"),
      pairError: byId("pair-error"),
      pairCard: document.querySelector(".pair-card"),
      connChip: byId("conn-chip"),
      connLabel: byId("conn-label"),
      themeToggle: byId("theme-toggle"),
      settingsBtn: byId("settings-btn"),
      pageTitle: byId("mobile-page-title"),
      modeSwitch: byId("send-mode-switch"),
      bottomNav: byId("bottom-nav"),
      deviceName: byId("device-name"),
      deviceAddr: byId("device-addr"),
      deviceCopy: byId("device-copy"),
      webName: byId("web-name"),
      peersChip: byId("peers-chip"),
      peersLabel: byId("peers-label"),
      offersSection: byId("offers-section"),
      offersTitle: byId("offers-title"),
      offersLabel: byId("offers-label"),
      offersList: byId("offers-list"),
      offersCount: byId("offers-count"),
      sendFiles: byId("send-files"),
      sendFolder: byId("send-folder"),
      sendText: byId("send-text"),
      fileInput: byId("file-input"),
      folderInput: byId("folder-input"),
      dropzone: byId("dropzone"),
      transfersList: byId("transfers-list"),
      transfersEmpty: byId("transfers-empty"),
      transfersSummary: byId("transfers-summary"),
      textForm: byId("text-form"),
      textInput: byId("text-input"),
      textCount: byId("text-count"),
      textSend: byId("text-send"),
      textsCard: byId("texts-card"),
      textsList: byId("texts-list"),
      textsToggle: byId("texts-toggle"),
      textsEmpty: byId("texts-empty"),
      historyPreview: byId("history-preview"),
      historyEmpty: byId("history-empty"),
      openHistory: byId("open-history"),
      footerVersion: byId("footer-version"),
      sheetBackdrop: byId("sheet-backdrop"),
      historySheet: byId("history-sheet"),
      historyClose: byId("history-close"),
      historySheetList: byId("history-sheet-list"),
      historySheetEmpty: byId("history-sheet-empty"),
      settingsSheet: byId("settings-sheet"),
      settingsClose: byId("settings-close"),
      settingsWebName: byId("settings-web-name"),
      settingsWebMeta: byId("settings-web-meta"),
      autoAcceptToggle: byId("auto-accept-toggle"),
      httpsToggle: byId("https-toggle"),
      settingsScheme: byId("settings-scheme"),
      openHttps: byId("open-https"),
      settingsDeviceName: byId("settings-device-name"),
      settingsAddress: byId("settings-address"),
      settingsDir: byId("settings-dir"),
      copyDir: byId("copy-dir"),
      settingsPairing: byId("settings-pairing"),
      settingsSessions: byId("settings-sessions"),
      settingsVersion: byId("settings-version"),
      installRow: byId("install-row"),
      installBtn: byId("install-btn"),
      disconnectBtn: byId("disconnect-btn"),
      sendSheet: byId("send-sheet"),
      sendClose: byId("send-close"),
      sendList: byId("send-list"),
      sendTargetName: byId("send-target-name"),
      sendCount: byId("send-count"),
      sendTotal: byId("send-total"),
      sendCancel: byId("send-cancel"),
      sendConfirm: byId("send-confirm"),
      installBanner: byId("install-banner"),
      installAdd: byId("install-add"),
      installDismiss: byId("install-dismiss"),
      toastRegion: byId("toast-region"),
      srStatus: byId("sr-status"),
    });

    ui.themeChoices = Array.from(document.querySelectorAll("[data-theme-choice]"));
    ui.modeButtons = ui.modeSwitch ? Array.from(ui.modeSwitch.querySelectorAll("[data-mode]")) : [];
    ui.tabButtons = ui.bottomNav ? Array.from(ui.bottomNav.querySelectorAll("[data-tab]")) : [];
    ui.sheets = [ui.settingsSheet, ui.historySheet, ui.sendSheet];
    ui.templates = {
      transfer: byId("tpl-transfer"),
      offerFiles: byId("tpl-offer-files"),
      offerText: byId("tpl-offer-text"),
      offerFile: byId("tpl-offer-file"),
      textItem: byId("tpl-text-item"),
      historyItem: byId("tpl-history-item"),
      fileRow: byId("tpl-file-row"),
    };
  }

  /* ------------------------------------------------------------------------
     3. 通用工具
     ------------------------------------------------------------------------ */
  function normalizePhoneName(value) {
    const name = String(value || "")
      .replace(/[\u0000-\u001f\u007f]/g, "")
      .trim();
    return name || defaultPhoneName();
  }

  function defaultPhoneName() {
    const ua = navigator.userAgent || "";
    if (/iPhone/i.test(ua)) return "我的 iPhone";
    if (/iPad/i.test(ua)) return "我的 iPad";
    if (/Android/i.test(ua)) return "我的 Android 手机";
    return "我的手机";
  }

  function normalizeCode(value) {
    return String(value || "").replace(/\D/g, "").slice(0, 6);
  }

  function randomHex32() {
    const bytes = new Uint8Array(16);
    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      window.crypto.getRandomValues(bytes);
    } else {
      for (let i = 0; i < bytes.length; i += 1) {
        bytes[i] = Math.floor(Math.random() * 256);
      }
    }
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function formatBytes(value) {
    let n = Number(value);
    if (!Number.isFinite(n) || n < 0) n = 0;
    if (n < 1024) return `${Math.round(n)} B`;
    const units = ["KB", "MB", "GB", "TB", "PB"];
    let index = -1;
    do {
      n /= 1024;
      index += 1;
    } while (n >= 1024 && index < units.length - 1);
    const rounded = n >= 100 ? Math.round(n) : n >= 10 ? Math.round(n * 10) / 10 : Math.round(n * 100) / 100;
    return `${rounded} ${units[index]}`;
  }

  function formatSpeed(bytesPerSecond) {
    const speed = Number(bytesPerSecond);
    if (!Number.isFinite(speed) || speed <= 0) return "";
    return `${formatBytes(speed)}/s`;
  }

  function formatEta(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return "正在估算";
    if (value < 1) return "即将完成";
    if (value < 60) return `剩余 ${Math.ceil(value)} 秒`;
    if (value < 3600) {
      const minutes = Math.floor(value / 60);
      const rest = Math.ceil(value % 60);
      return `剩余 ${minutes} 分${rest ? ` ${rest} 秒` : ""}`;
    }
    const hours = Math.floor(value / 3600);
    const minutes = Math.ceil((value % 3600) / 60);
    return `剩余 ${hours} 小时${minutes ? ` ${minutes} 分` : ""}`;
  }

  function formatDuration(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return "";
    if (value < 60) return `${Math.max(1, Math.round(value))} 秒`;
    if (value < 3600) {
      const minutes = Math.floor(value / 60);
      const rest = Math.round(value % 60);
      return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`;
    }
    const hours = Math.floor(value / 3600);
    const minutes = Math.round((value % 3600) / 60);
    return minutes ? `${hours} 小时 ${minutes} 分` : `${hours} 小时`;
  }

  function formatClock(timestamp) {
    const value = Number(timestamp);
    if (!Number.isFinite(value) || value <= 0) return "—";
    const date = new Date(value * 1000);
    if (Number.isNaN(date.getTime())) return "—";
    const now = new Date();
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const sameDay =
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate();
    if (sameDay) return `${hours}:${minutes}`;
    return `${date.getMonth() + 1}/${date.getDate()} ${hours}:${minutes}`;
  }

  function formatRelative(timestamp) {
    const value = Number(timestamp);
    if (!Number.isFinite(value) || value <= 0) return "";
    const diff = Math.max(0, Date.now() / 1000 - value);
    if (diff < 60) return "刚刚";
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    if (diff < 172800) return "昨天";
    const date = new Date(value * 1000);
    return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  }

  function dirnameOf(relPath) {
    const path = String(relPath || "");
    const index = path.lastIndexOf("/");
    return index > 0 ? path.slice(0, index) : "";
  }

  function isIOS() {
    const ua = navigator.userAgent || "";
    return /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function isStandalone() {
    return (
      (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true
    );
  }

  function safeText(value, fallback = "") {
    if (value === null || value === undefined) return fallback;
    return String(value);
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function icon(name, className = "icon") {
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", className);
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS(svgNS, "use");
    use.setAttribute("href", `#i-${name}`);
    svg.appendChild(use);
    return svg;
  }

  function cloneTemplate(template) {
    if (!template || !template.content || !template.content.firstElementChild) return null;
    return template.content.firstElementChild.cloneNode(true);
  }

  function setNodeText(root, selector, value) {
    const node = root.querySelector(selector);
    if (node) node.textContent = value === null || value === undefined ? "" : String(value);
    return node;
  }

  function setNodeHidden(root, selector, hidden) {
    const node = root.querySelector(selector);
    if (node) node.hidden = !!hidden;
    return node;
  }

  function clearNode(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function canUseClipboard() {
    return !!(navigator.clipboard && window.isSecureContext && typeof navigator.clipboard.writeText === "function");
  }

  async function copyText(text, options = {}) {
    const value = String(text === null || text === undefined ? "" : text);
    if (!value) return false;
    if (canUseClipboard()) {
      try {
        await navigator.clipboard.writeText(value);
        if (!options.silent) showToast("已复制到剪贴板", "success");
        return true;
      } catch (_) {
        /* 继续走兼容方案 */
      }
    }
    try {
      const area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.top = "-1200px";
      area.style.left = "-1200px";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      area.setSelectionRange(0, area.value.length);
      const ok = document.execCommand("copy");
      document.body.removeChild(area);
      if (ok) {
        if (!options.silent) showToast("已复制到剪贴板", "success");
        return true;
      }
    } catch (_) {
      /* ignore */
    }
    if (!options.silent) showToast("复制失败，请长按文本手动复制", "error");
    return false;
  }

  function friendlyError(error, fallback = "操作失败，请稍后重试。") {
    if (!error) return fallback;
    if (error.status === 401) return "配对已失效，请重新连接电脑。";
    if (error.status === 0) return error.message || "无法连接到电脑。";
    if (error.status === 429) return "操作太频繁，请稍后再试。";
    if (error.status === 404) return "电脑端服务暂时不可用，请确认 Aster 正在运行。";
    if (error.status === 405 || error.status === 501) return "没有找到 Aster 服务，请确认电脑端已经启动。";
    if (error.status === 507) return "电脑磁盘空间不足，无法接收文件。";
    return error.message || fallback;
  }

  function showToast(message, type = "info", timeout = 3300) {
    if (!ui.toastRegion) return;
    const toast = make("div", `toast ${type}`);
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    const iconWrap = make("span", "toast-icon");
    iconWrap.appendChild(icon(type === "success" ? "check" : type === "error" ? "alert" : "info"));
    const text = make("span", "toast-text", message);
    toast.append(iconWrap, text);
    ui.toastRegion.appendChild(toast);
    while (ui.toastRegion.children.length > 3) {
      ui.toastRegion.removeChild(ui.toastRegion.firstElementChild);
    }
    window.setTimeout(() => {
      toast.classList.add("is-out");
      window.setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 280);
    }, timeout);
  }

  function setSRStatus(message) {
    if (ui.srStatus) ui.srStatus.textContent = String(message || "");
  }

  function setSignature(key, value) {
    if (app.sigs[key] === value) return false;
    app.sigs[key] = value;
    return true;
  }

  function resetSignatures() {
    app.sigs = {};
  }

  /* ------------------------------------------------------------------------
     4. 主题
     ------------------------------------------------------------------------ */
  function applyTheme(theme, options = {}) {
    const next = theme === "light" ? "light" : "dark";
    app.theme = next;
    document.documentElement.dataset.theme = next;
    if (ui.metaTheme) ui.metaTheme.setAttribute("content", next === "dark" ? "#070B14" : "#F2F4FB");
    if (options.persist !== false) store.set(STORAGE.theme, next);
    if (ui.themeToggle) {
      ui.themeToggle.setAttribute("aria-label", next === "dark" ? "切换为浅色主题" : "切换为深色主题");
      ui.themeToggle.setAttribute("title", next === "dark" ? "切换到浅色" : "切换到深色");
      ui.themeToggle.setAttribute("aria-pressed", next === "light" ? "true" : "false");
    }
    ui.themeChoices.forEach((button) => {
      const active = button.dataset.themeChoice === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function toggleTheme() {
    applyTheme(app.theme === "dark" ? "light" : "dark");
  }

  /* ------------------------------------------------------------------------
     5. 网络请求
     ------------------------------------------------------------------------ */
  async function api(path, options = {}) {
    const {
      method = "GET",
      body,
      auth = true,
      timeout = 15000,
      handle401 = true,
      headers: extraHeaders = {},
    } = options;
    const headers = Object.assign({ Accept: "application/json" }, extraHeaders);
    if (auth && app.token) headers["X-Aster-Web-Token"] = app.token;
    const init = { method, headers, cache: "no-store" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    if (controller) {
      init.signal = controller.signal;
    }
    const timer = controller
      ? window.setTimeout(() => {
          try {
            controller.abort();
          } catch (_) {
            /* ignore */
          }
        }, timeout)
      : 0;
    let response;
    try {
      response = await fetch(path, init);
    } catch (error) {
      if (error && error.name === "AbortError") {
        throw new ClientError("请求超时，请检查网络。", 0);
      }
      throw new ClientError("无法连接到电脑。", 0);
    } finally {
      if (timer) window.clearTimeout(timer);
    }

    let data = null;
    const raw = await response.text();
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch (_) {
        data = { error: raw.slice(0, 240) };
      }
    }
    if (!response.ok) {
      if (response.status === 401 && auth && handle401) onUnauthorized();
      const message =
        (data && (data.error || data.message)) || `请求失败（${response.status}）`;
      throw new ClientError(String(message), response.status, data);
    }
    return data && typeof data === "object" ? data : {};
  }

  function fetchState(options = {}) {
    return api("/api/v1/web/state", {
      auth: true,
      timeout: options.timeout || 8000,
      handle401: options.handle401 !== false,
    });
  }

  /* ------------------------------------------------------------------------
     6. 配对 / 会话 / 视图
     ------------------------------------------------------------------------ */
  function normalizeUrlPairCode() {
    const params = new URL(location.href).searchParams;
    const raw = String(params.get("pair") || "");
    const digits = raw.replace(/\D/g, "").slice(0, 6);
    return { raw, digits, valid: digits.length === 6 };
  }

  function cleanPairQuery() {
    const url = new URL(location.href);
    if (!url.searchParams.has("pair")) return;
    url.searchParams.delete("pair");
    const query = url.searchParams.toString();
    try {
      history.replaceState(null, "", `${url.pathname}${query ? `?${query}` : ""}${url.hash}`);
    } catch (_) {
      /* ignore */
    }
  }

  function saveSession(token, webId, phoneName) {
    app.token = String(token || "");
    app.webId = String(webId || "");
    app.phoneName = normalizePhoneName(phoneName || app.phoneName);
    store.set(STORAGE.token, app.token);
    store.set(STORAGE.webId, app.webId);
    store.set(STORAGE.phoneName, app.phoneName);
  }

  function clearSession() {
    app.token = "";
    app.webId = "";
    app.state = null;
    app.connected = false;
    app.hasEnteredApp = false;
    store.remove(STORAGE.token);
    store.remove(STORAGE.webId);
    stopRealtime();
    resetSignatures();
    app.offerStatus.clear();
    app.knownOfferIds.clear();
    app.offersInitialized = false;
  }

  function setSendMode(mode) {
    const next = mode === "text" ? "text" : "files";
    app.sendMode = next;
    if (ui.appView) {
      ui.appView.classList.toggle("mode-text", next === "text");
      ui.appView.dataset.mode = next;
    }
    ui.modeButtons.forEach((button) => {
      const active = button.dataset.mode === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (next === "text" && ui.textInput) {
      window.setTimeout(() => ui.textInput.focus({ preventScroll: true }), 80);
    }
  }

  function setTab(tab, options = {}) {
    const next = tab === "receive" ? "receive" : "send";
    app.tab = next;
    if (ui.appView) ui.appView.dataset.tab = next;
    if (ui.pageTitle) ui.pageTitle.textContent = next === "receive" ? "接收" : "发送";
    ui.tabButtons.forEach((button) => {
      const active = button.dataset.tab === next;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    if (options.scroll !== false) {
      const target = next === "receive" ? ui.offersSection || ui.main : ui.main;
      try {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (_) {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }
  }

  function setView(view) {
    app.view = view;
    if (ui.bootView) ui.bootView.hidden = view !== "boot";
    if (ui.pairView) ui.pairView.hidden = view !== "pair";
    if (ui.appView) ui.appView.hidden = view !== "app";
    if (view === "app") {
      setTab(app.tab || "send", { scroll: false });
    }
    if (view !== "app") {
      hideInstallBanner();
      if (ui.installRow) ui.installRow.hidden = true;
    }
    if (view === "pair") {
      window.setTimeout(() => {
        if (app.view === "pair" && !app.pairingBusy) {
          try {
            ui.pairCode.focus({ preventScroll: true });
          } catch (_) {
            ui.pairCode.focus();
          }
        }
      }, 160);
    }
    if (view === "app") {
      if (!app.hasEnteredApp) {
        app.hasEnteredApp = true;
        window.scrollTo(0, 0);
      }
      updateInstallRow();
    }
  }

  function setPairLoading(loading, label) {
    app.pairingBusy = !!loading;
    if (!ui.pairSubmit) return;
    ui.pairSubmit.classList.toggle("is-loading", !!loading);
    ui.pairSubmit.disabled = !!loading;
    ui.pairSubmit.setAttribute("aria-busy", loading ? "true" : "false");
    if (ui.pairCode) ui.pairCode.disabled = !!loading;
    if (ui.pairName) ui.pairName.disabled = !!loading;
    const labelNode = ui.pairSubmit.querySelector(".btn-label");
    if (labelNode) labelNode.textContent = loading ? "正在连接…" : label || "连接电脑";
  }

  function showPairError(message) {
    if (!ui.pairError) return;
    ui.pairError.textContent = String(message || "");
    ui.pairError.hidden = !message;
  }

  function clearPairHint() {
    if (!ui.pairHint) return;
    ui.pairHint.hidden = true;
    ui.pairHint.textContent = "";
  }

  function shakePairCard() {
    if (!ui.pairCard) return;
    ui.pairCard.classList.remove("is-shaking");
    void ui.pairCard.offsetWidth;
    ui.pairCard.classList.add("is-shaking");
  }

  function showPairing(message = "", options = {}) {
    stopRealtime();
    closeAllSheets(true, false);
    app.connected = false;
    const view = "pair";
    setView(view);
    app.autoPairScheduled = false;
    showPairError(message || "");
    clearPairHint();
    if (typeof options.code === "string") {
      ui.pairCode.value = normalizeCode(options.code);
    }
    if (ui.pairName) ui.pairName.value = app.phoneName;
    setPairLoading(false);
    document.title = "连接 · Aster 星流";
    if (message) {
      setSRStatus(`连接失败：${message}`);
    }
    if (options.auto) {
      app.autoPairScheduled = true;
      if (ui.pairHint) {
        ui.pairHint.textContent = "已从链接读取配对码，正在连接电脑…";
        ui.pairHint.hidden = false;
      }
      window.setTimeout(() => {
        if (app.view === "pair" && !app.pairingBusy && app.autoPairScheduled) {
          submitPair({ auto: true });
        }
      }, 420);
    }
  }

  function pairErrorMessage(error) {
    if (!error) return "连接失败，请重试。";
    if (error.status === 403) return "配对码不正确，请核对电脑上显示的 6 位数字。";
    if (error.status === 429) return "尝试次数过多，请等一分钟再试。";
    if (error.status === 404 || error.status === 405 || error.status === 501) {
      return "没有找到 Aster 服务，请确认电脑端已经启动。";
    }
    if (error.status === 0) return "无法连接到电脑。";
    return error.message || "连接失败，请重试。";
  }

  async function submitPair(options = {}) {
    if (app.pairingBusy) return;
    const code = normalizeCode(ui.pairCode.value);
    const name = normalizePhoneName(ui.pairName.value);
    ui.pairCode.value = code;
    ui.pairName.value = name;
    showPairError("");
    clearPairHint();
    if (code.length !== 6) {
      showPairError("请输入电脑上显示的 6 位数字配对码。");
      shakePairCard();
      try {
        ui.pairCode.focus();
      } catch (_) {
        /* ignore */
      }
      return;
    }
    app.phoneName = name;
    store.set(STORAGE.phoneName, name);
    setPairLoading(true);
    try {
      const data = await api("/api/v1/web/pair", {
        method: "POST",
        auth: false,
        timeout: 12000,
        handle401: false,
        body: {
          code,
          name,
          ua: navigator.userAgent,
        },
      });
      if (!data || !data.token) {
        throw new ClientError("电脑返回的配对信息不完整，请重试。", 0);
      }
      saveSession(data.token, data.web_id, name);
      app.state = data.state || null;
      app.connected = true;
      app.offersInitialized = false;
      app.knownOfferIds.clear();
      app.offerStatus.clear();
      cleanPairQuery();
      ui.pairCode.value = "";
      app.autoPairScheduled = false;
      setPairLoading(false);
      resetSignatures();
      enterApp({ welcome: true });
    } catch (error) {
      app.autoPairScheduled = false;
      setPairLoading(false);
      const message = pairErrorMessage(error);
      showPairError(message);
      shakePairCard();
      setSRStatus(`连接失败：${message}`);
      window.setTimeout(() => {
        if (app.view === "pair") {
          try {
            ui.pairCode.focus();
            ui.pairCode.select();
          } catch (_) {
            /* ignore */
          }
        }
      }, 180);
    }
  }

  function enterApp(options = {}) {
    setView("app");
    updateConnection();
    resetSignatures();
    renderAll(true);
    startRealtime();
    registerServiceWorker();
    updateInstallRow();
    maybeShowInstallBanner();
    if (options.welcome) {
      const deviceName = app.state && app.state.device ? app.state.device.alias : "电脑";
      showToast(`已连接到 ${deviceName}`, "success", 2800);
    }
    window.setTimeout(() => {
      if (app.view === "app" && !app.connected) probeConnection({ quiet: true });
    }, 3500);
  }

  async function routeBoot() {
    const { raw, digits, valid } = normalizeUrlPairCode();
    if (raw) ui.pairCode.value = raw.replace(/\D/g, "").slice(0, 6);
    if (app.token) {
      setView("boot");
      updateConnection();
      try {
        const state = await fetchState({ handle401: false });
        app.state = state;
        app.connected = true;
        if (valid) cleanPairQuery();
        enterApp({ welcome: false });
        return;
      } catch (error) {
        if (error.status === 401) {
          clearSession();
          if (valid) {
            showPairing("", { auto: true, code: digits });
            return;
          }
          showPairing("配对已失效，请输入电脑上新的 6 位配对码。");
          return;
        }
        if (valid) {
          showPairing("", { auto: true, code: digits });
          return;
        }
        showPairing("无法连接到电脑。");
        return;
      }
    }
    if (valid) {
      showPairing("", { auto: true, code: digits });
    } else {
      showPairing();
    }
  }

  function onUnauthorized() {
    const now = Date.now();
    if (app.unauthorizedLock && now - app.unauthorizedLock < 4000) return;
    if (app.view === "pair") return;
    app.unauthorizedLock = now;
    const wasApp = app.view === "app";
    clearSession();
    closeAllSheets(true, false);
    showPairing("配对已失效，请在电脑上查看新的配对码重新连接。");
    if (wasApp) showToast("网页配对已失效，请重新连接", "error", 4200);
    window.setTimeout(() => {
      app.unauthorizedLock = 0;
    }, 4200);
  }

  /* ------------------------------------------------------------------------
     7. 实时连接（SSE / 轮询 / 状态探测）
     ------------------------------------------------------------------------ */
  function updateConnection() {
    if (!ui.connChip) return;
    const online = !!app.connected && navigator.onLine;
    const label = !navigator.onLine
      ? "离线"
      : online
        ? "已连接"
        : app.state
          ? "重连中"
          : "连接中";
    ui.connChip.classList.toggle("is-online", online);
    ui.connChip.classList.toggle("is-connecting", !online && navigator.onLine);
    ui.connChip.classList.toggle("is-offline", !navigator.onLine);
    if (ui.connLabel) ui.connLabel.textContent = label;
    ui.connChip.setAttribute(
      "aria-label",
      online ? "已连接到电脑，点击刷新连接" : `${label}，点击重试连接`
    );
    const key = `${label}|${online}`;
    if (app.lastConnectionKey !== key) {
      app.lastConnectionKey = key;
      if (app.view === "app") setSRStatus(`连接状态：${label}`);
    }
  }

  function stopRealtime() {
    if (app.sse) {
      try {
        app.sse.onopen = null;
        app.sse.onmessage = null;
        app.sse.onerror = null;
        app.sse.close();
      } catch (_) {
        /* ignore */
      }
      app.sse = null;
    }
    if (app.reconnectTimer) {
      window.clearTimeout(app.reconnectTimer);
      app.reconnectTimer = 0;
    }
    if (app.probeTimer) {
      window.clearTimeout(app.probeTimer);
      app.probeTimer = 0;
    }
    if (app.pollTimer) {
      window.clearInterval(app.pollTimer);
      app.pollTimer = 0;
    }
    app.polling = false;
    app.sseFailures = 0;
    app.reconnectAttempts = 0;
  }

  function startRealtime() {
    stopRealtime();
    if (!app.token || app.view !== "app") return;
    if (!("EventSource" in window)) {
      startPolling();
      return;
    }
    connectSSE();
  }

  function connectSSE() {
    if (!app.token || app.view !== "app") return;
    if (app.sse) {
      try {
        app.sse.close();
      } catch (_) {
        /* ignore */
      }
      app.sse = null;
    }
    const tokenAtStart = app.token;
    let source;
    try {
      source = new EventSource(`/api/v1/web/events?token=${encodeURIComponent(tokenAtStart)}`);
    } catch (_) {
      startPolling();
      return;
    }
    app.sse = source;
    source.onopen = () => {
      if (tokenAtStart !== app.token) return;
      app.connected = true;
      app.sseFailures = 0;
      app.reconnectAttempts = 0;
      app.lastFrameAt = Date.now();
      updateConnection();
      if (!app.state) refreshStateSilently();
    };
    source.onmessage = (event) => {
      if (tokenAtStart !== app.token) return;
      if (!event.data) return;
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (_) {
        return;
      }
      if (!data || typeof data !== "object") return;
      app.connected = true;
      app.sseFailures = 0;
      app.lastFrameAt = Date.now();
      app.state = data;
      updateConnection();
      scheduleRender();
    };
    source.onerror = () => {
      if (tokenAtStart !== app.token) return;
      app.connected = false;
      app.sseFailures += 1;
      updateConnection();
      if (source.readyState === EventSource.CLOSED) {
        scheduleReconnect();
      }
      if (app.sseFailures >= 2) {
        scheduleProbe();
      }
    };
  }

  function scheduleReconnect() {
    if (app.reconnectTimer || !app.token || app.view !== "app") return;
    if (typeof EventSource === "undefined") {
      if (!app.polling) startPolling();
      return;
    }
    app.reconnectAttempts += 1;
    const delay = Math.min(12000, 1400 * Math.pow(1.7, Math.min(app.reconnectAttempts, 5)));
    app.reconnectTimer = window.setTimeout(() => {
      app.reconnectTimer = 0;
      if (!app.token || app.view !== "app") return;
      if (app.sse) {
        try {
          app.sse.close();
        } catch (_) {
          /* ignore */
        }
        app.sse = null;
      }
      connectSSE();
    }, delay);
  }

  function sseConnectionClosed() {
    if (typeof EventSource === "undefined") return true;
    return !app.sse || app.sse.readyState === EventSource.CLOSED;
  }

  function scheduleProbe() {
    if (app.probeTimer || app.probing) return;
    const now = Date.now();
    const wait = Math.max(1200, 5000 - (now - app.lastProbeAt));
    app.probeTimer = window.setTimeout(() => {
      app.probeTimer = 0;
      probeConnection({ quiet: true });
    }, wait);
  }

  async function probeConnection(options = {}) {
    if (app.probing || app.view !== "app" || !app.token) return;
    app.probing = true;
    app.lastProbeAt = Date.now();
    const tokenAtStart = app.token;
    try {
      const state = await fetchState({ timeout: 6000, handle401: true });
      if (tokenAtStart !== app.token) return;
      app.state = state;
      app.connected = true;
      app.sseFailures = 0;
      updateConnection();
      scheduleRender();
      if (sseConnectionClosed()) {
        if (app.reconnectTimer) {
          window.clearTimeout(app.reconnectTimer);
          app.reconnectTimer = 0;
        }
        if (typeof EventSource !== "undefined") {
          connectSSE();
        } else if (!app.polling) {
          startPolling();
        }
      }
    } catch (error) {
      if (error.status === 401) return;
      app.connected = false;
      updateConnection();
      if (!options.quiet) {
        showToast(friendlyError(error), "error", 4000);
      }
      if (sseConnectionClosed() && typeof EventSource !== "undefined") scheduleReconnect();
      if (typeof EventSource === "undefined" && !app.polling) startPolling();
    } finally {
      app.probing = false;
    }
  }

  async function refreshStateSilently() {
    try {
      const state = await fetchState({ timeout: 8000, handle401: true });
      app.state = state;
      app.connected = true;
      updateConnection();
      scheduleRender();
    } catch (error) {
      if (error.status === 401) return;
      app.connected = false;
      updateConnection();
    }
  }

  function startPolling() {
    if (app.polling || !app.token || app.view !== "app") return;
    app.polling = true;
    const tick = async () => {
      if (!app.token || app.view !== "app") return;
      try {
        const state = await fetchState({ timeout: 6000, handle401: true });
        app.state = state;
        app.connected = true;
        updateConnection();
        scheduleRender();
      } catch (error) {
        if (error.status === 401) return;
        app.connected = false;
        updateConnection();
      }
    };
    tick();
    app.pollTimer = window.setInterval(tick, 3000);
  }

  async function manualRefresh() {
    if (app.view !== "app") return;
    const now = Date.now();
    if (now - app.lastManualRefresh < 1500) return;
    app.lastManualRefresh = now;
    ui.connChip.setAttribute("aria-busy", "true");
    try {
      const state = await fetchState({ timeout: 7000, handle401: true });
      app.state = state;
      app.connected = true;
      app.sseFailures = 0;
      updateConnection();
      renderAll(true);
      showToast("连接已刷新", "success", 1800);
    } catch (error) {
      if (error.status !== 401) {
        app.connected = false;
        updateConnection();
        showToast(friendlyError(error), "error", 3800);
      }
    } finally {
      ui.connChip.removeAttribute("aria-busy");
    }
  }

  /* ------------------------------------------------------------------------
     8. 渲染总控
     ------------------------------------------------------------------------ */
  function scheduleRender() {
    app.renderQueued = true;
    if (app.renderRaf) return;
    if (document.hidden) return;
    app.renderRaf = window.requestAnimationFrame(() => {
      app.renderRaf = 0;
      if (!app.renderQueued || document.hidden) return;
      app.renderQueued = false;
      renderAll(false);
    });
  }

  function renderAll(force = false) {
    if (!app.state || app.view !== "app") return;
    safeRender("设备信息", () => renderDevice(force));
    safeRender("接收请求", () => renderOffers(force));
    safeRender("传输进度", () => renderTransfers(force));
    safeRender("文本", () => renderTexts(force));
    safeRender("历史", () => renderHistory(force));
    safeRender("设置", () => renderSettings());
    updateConnection();
    updateDocumentTitle();
  }

  function safeRender(label, fn) {
    try {
      fn();
    } catch (error) {
      console.error(`[Aster] 渲染${label}失败`, error);
    }
  }

  function updateDocumentTitle() {
    if (app.view === "pair") {
      document.title = "连接 · Aster 星流";
      return;
    }
    if (app.view !== "app" || !app.state) {
      document.title = "Aster · 星流";
      return;
    }
    const pending = (app.state.offers || []).filter((offer) => {
      const status = app.offerStatus.get(offer.id) || offer.status;
      return status === "pending";
    }).length;
    document.title = pending ? `(${pending}) 待接收 · Aster 星流` : "Aster · 星流";
  }

  /* ------------------------------------------------------------------------
     9. 渲染 — 设备 / 顶部
     ------------------------------------------------------------------------ */
  function renderDevice() {
    const state = app.state;
    if (!state) return;
    const device = state.device || {};
    const alias = safeText(device.alias, "这台电脑");
    if (ui.deviceName) ui.deviceName.textContent = alias;
    if (ui.deviceAddr) {
      const ip = safeText(device.ip, location.hostname);
      const port = safeText(device.port, location.port || "47820");
      ui.deviceAddr.textContent = `${ip}:${port}`;
    }
    if (ui.webName) ui.webName.textContent = safeText(state.web && state.web.name, app.phoneName);
    if (ui.peersLabel) {
      const onlinePeers = Array.isArray(state.peers)
        ? state.peers.filter((peer) => peer && peer.online).length
        : 0;
      ui.peersLabel.textContent = onlinePeers > 0 ? `另有 ${onlinePeers} 台电脑在线` : "仅此一台";
      if (ui.peersChip) {
        const names = (state.peers || [])
          .filter((peer) => peer && peer.online)
          .map((peer) => safeText(peer.alias, "未命名电脑"))
          .slice(0, 5)
          .join("、");
        ui.peersChip.title = names || "局域网内暂未发现其他电脑";
      }
    }
    if (ui.footerVersion) {
      const version = safeText((state.settings && state.settings.version) || state.version, "—");
      ui.footerVersion.textContent = version === "—" ? "v—" : `v${version}`;
    }
    if (ui.deviceCopy) {
      const hasUrl = !!(state.web_url || location.origin);
      ui.deviceCopy.disabled = !hasUrl;
    }
  }

  /* ------------------------------------------------------------------------
     10. 渲染 — 待接收 offer
     ------------------------------------------------------------------------ */
  function effectiveOfferStatus(offer) {
    if (!offer) return "pending";
    const local = app.offerStatus.get(offer.id);
    if (offer.status !== "pending") {
      if (local) app.offerStatus.delete(offer.id);
      return offer.status;
    }
    return local || offer.status || "pending";
  }

  function renderOffers(force = false) {
    const state = app.state;
    if (!state) return;
    const allOffers = Array.isArray(state.offers) ? state.offers : [];
    const present = new Set(allOffers.map((offer) => offer.id));
    app.offerStatus.forEach((_, id) => {
      if (!present.has(id)) app.offerStatus.delete(id);
    });

    const visible = [];
    allOffers.forEach((offer) => {
      if (!offer || !offer.id) return;
      const status = effectiveOfferStatus(offer);
      if (status === "pending" || status === "accepted" || status === "downloading") {
        visible.push({ offer, status });
      }
    });
    visible.sort((a, b) => {
      const pendingDelta = (a.status === "pending" ? 0 : 1) - (b.status === "pending" ? 0 : 1);
      if (pendingDelta !== 0) return pendingDelta;
      return Number(b.offer.created || 0) - Number(a.offer.created || 0);
    });

    const pending = visible.filter((entry) => entry.status === "pending");
    const pendingIds = new Set(pending.map((entry) => entry.offer.id));
    if (!app.offersInitialized) {
      app.offersInitialized = true;
      pendingIds.forEach((id) => app.knownOfferIds.add(id));
    } else {
      const fresh = pending.filter((entry) => !app.knownOfferIds.has(entry.offer.id));
      if (fresh.length) {
        const fileCount = fresh.reduce(
          (total, entry) => total + (Array.isArray(entry.offer.files) ? entry.offer.files.length : 0),
          0
        );
        const message =
          fileCount > 0
            ? `电脑想发送 ${fileCount} 个文件，等待接收`
            : "电脑发来一段文本，等待接收";
        showToast(message, "info", 4300);
        setSRStatus(message);
        fresh.forEach((entry) => app.knownOfferIds.add(entry.offer.id));
        if (app.view === "app" && !app.upload && !app.activeSheet) {
          window.setTimeout(() => setTab("receive"), 120);
        }
      }
    }
    app.knownOfferIds.forEach((id) => {
      if (!present.has(id)) app.knownOfferIds.delete(id);
    });

    if (ui.offersSection) ui.offersSection.hidden = visible.length === 0;
    if (ui.offersCount) {
      ui.offersCount.textContent = String(pending.length);
      ui.offersCount.hidden = pending.length === 0;
    }
    if (ui.offersLabel) {
      ui.offersLabel.textContent = pending.length > 0 ? "待你接收" : "接收文件";
    }

    const signature = JSON.stringify(
      visible.map(({ offer, status }) => [
        offer.id,
        status,
        Array.isArray(offer.files)
          ? offer.files.map((file) => [file.id, file.status, file.sent, file.size])
          : [],
        offer.text,
        offer.updated,
        offer.done_bytes,
        offer.speed,
        offer.avg_speed,
        offer.eta,
      ])
    );
    if (!force && !setSignature("offers", signature)) return;

    const list = ui.offersList;
    if (!list) return;
    clearNode(list);
    visible.forEach(({ offer, status }) => {
      const isFiles = Array.isArray(offer.files) && offer.files.length > 0;
      const card = buildOfferCard(offer, status, isFiles);
      if (card) list.appendChild(card);
    });
    updateDocumentTitle();
  }

  function buildOfferCard(offer, status, isFiles) {
    const template = isFiles ? ui.templates.offerFiles : ui.templates.offerText;
    const card = cloneTemplate(template);
    if (!card) return null;
    card.dataset.offerId = offer.id;
    card.classList.toggle("is-pending", status === "pending");
    card.classList.toggle("is-accepted", status !== "pending");

    const device = (app.state && app.state.device) || {};
    const alias = safeText(device.alias, "电脑");
    const files = Array.isArray(offer.files) ? offer.files : [];
    const totalBytes = Number(offer.total_bytes) || files.reduce((sum, file) => sum + (Number(file.size) || 0), 0);

    const kicker = card.querySelector(".offer-kicker");
    if (kicker) kicker.textContent = isFiles ? "来自电脑" : "来自电脑的文本";

    const title = card.querySelector(".offer-title");
    if (title) {
      if (isFiles) {
        title.textContent =
          status === "pending"
            ? `电脑想发送 ${files.length} 个文件`
            : `来自电脑的 ${files.length} 个文件`;
      } else {
        title.textContent = "电脑发来一段文本";
      }
    }

    const sub = card.querySelector(".offer-sub");
    if (sub) {
      if (isFiles) {
        const hint =
          status === "pending"
            ? "等待确认"
            : status === "downloading"
              ? "下载中"
              : "逐个保存";
        sub.textContent = `${alias} · ${formatBytes(totalBytes)} · ${hint}`;
      } else {
        sub.textContent = `${alias} · ${formatRelative(offer.created)}`;
      }
    }

    const pill = card.querySelector(".offer-pill");
    if (pill) {
      if (status === "pending") {
        pill.textContent = "等待确认";
        pill.classList.remove("is-accepted");
      } else {
        pill.textContent = status === "downloading" ? "下载中" : "已接收";
        pill.classList.add("is-accepted");
      }
    }

    if (isFiles) {
      const filesBox = card.querySelector(".offer-files");
      const progressBox = card.querySelector(".offer-progress");
      const progressFill = card.querySelector(".offer-progress-fill");
      const progressText = card.querySelector(".offer-progress-text");
      const progressSpeed = card.querySelector(".offer-progress-speed");
      const doneBytes =
        Number(offer.done_bytes) ||
        files.reduce((sum, file) => sum + (Number(file.sent) || 0), 0);
      const speed = Number(offer.speed) || Number(offer.avg_speed) || 0;
      if (progressBox) {
        const showProgress = status !== "pending" && totalBytes > 0;
        progressBox.hidden = !showProgress;
        if (showProgress) {
          const percent = Math.max(0, Math.min(100, (doneBytes / totalBytes) * 100));
          if (progressFill) progressFill.style.width = `${percent}%`;
          if (progressText) {
            progressText.textContent = `${formatBytes(doneBytes)} / ${formatBytes(totalBytes)} · ${Math.round(percent)}%`;
          }
          if (progressSpeed) {
            progressSpeed.textContent = speed > 0 ? formatSpeed(speed) : "";
          }
        }
      }
      if (filesBox) {
        files.forEach((file) => {
          const row = cloneTemplate(ui.templates.offerFile);
          if (!row) return;
          setNodeText(row, ".offer-file-name", safeText(file.name, "未命名文件"));
          let meta = formatBytes(file.size);
          const dir = dirnameOf(file.rel_path);
          if (dir) meta += ` · ${dir}`;
          if (status !== "pending" && Number(file.sent) > 0 && file.status !== "completed") {
            meta = `${formatBytes(file.sent)} / ${formatBytes(file.size)}`;
          }
          setNodeText(row, ".offer-file-meta", meta);
          const side = row.querySelector(".offer-file-side");
          if (side) {
            if (status === "pending") {
              /* 等待确认，不提供下载 */
            } else if (file.status === "completed") {
              const done = make("span", "offer-file-done");
              done.appendChild(icon("check"));
              done.appendChild(document.createTextNode("已保存"));
              side.appendChild(done);
            } else {
              const href = safeDownloadUrl(file);
              if (href) {
                const link = make("a", "download-link");
                link.href = href;
                link.setAttribute("download", safeText(file.name, "download"));
                link.setAttribute("aria-label", `保存 ${safeText(file.name, "文件")}`);
                link.appendChild(icon("download"));
                link.appendChild(document.createTextNode("保存"));
                side.appendChild(link);
              } else {
                side.appendChild(make("span", "offer-file-done", "暂不可下载"));
              }
            }
          }
          filesBox.appendChild(row);
        });
      }
    } else {
      const quote = card.querySelector(".offer-quote");
      if (quote) quote.textContent = safeText(offer.text);
    }

    const actions = card.querySelector(".offer-actions");
    if (actions) {
      if (status === "pending") {
        const reject = make("button", "btn btn-ghost", "忽略");
        reject.type = "button";
        reject.setAttribute("aria-label", "忽略这次接收请求");
        const accept = make("button", "btn btn-primary");
        accept.type = "button";
        accept.appendChild(icon("check"));
        accept.appendChild(
          document.createTextNode(isFiles ? (files.length > 1 ? `接收 ${files.length} 个文件` : "接收文件") : "接收并复制")
        );
        accept.setAttribute("aria-label", isFiles ? "接收电脑发来的文件" : "接收文本并复制");
        reject.addEventListener("click", () => {
          respondOffer(offer, false, isFiles, accept, reject);
        });
        accept.addEventListener("click", () => {
          respondOffer(offer, true, isFiles, accept, reject);
        });
        actions.append(reject, accept);
      } else if (!isFiles) {
        const copy = make("button", "btn btn-ghost", "复制文本");
        copy.type = "button";
        copy.addEventListener("click", () => copyText(offer.text));
        actions.appendChild(copy);
      } else {
        const cancel = make("button", "btn btn-ghost btn-cancel", "取消下载");
        cancel.type = "button";
        cancel.setAttribute("aria-label", "取消正在下载的文件");
        cancel.addEventListener("click", () => cancelOfferDownload(offer, cancel));
        actions.appendChild(cancel);
      }
    }

    return card;
  }

  function safeDownloadUrl(file) {
    if (!file || !app.token) return null;
    const raw = safeText(file.url);
    if (!raw.startsWith("/api/v1/web/offers/")) return null;
    let url;
    try {
      url = new URL(raw, location.origin);
    } catch (_) {
      return null;
    }
    if (url.origin !== location.origin) return null;
    if (!/^\/api\/v1\/web\/offers\/[0-9a-f]+\/files\/[0-9a-fA-F]+\/download$/.test(url.pathname)) {
      return null;
    }
    url.search = "";
    url.searchParams.set("token", app.token);
    return `${url.pathname}?${url.searchParams.toString()}`;
  }

  function autoDownloadOffer(offer) {
    if (!offer || !Array.isArray(offer.files) || !offer.files.length) return;
    const urls = [];
    offer.files.forEach((file) => {
      const href = safeDownloadUrl(file);
      if (!href) return;
      urls.push({ href, name: safeText(file.name, "download") });
    });
    if (!urls.length) return;
    showToast(
      urls.length > 1 ? `已开始下载 ${urls.length} 个文件` : "已开始下载文件",
      "success",
      3000
    );
    setSRStatus(`已开始下载 ${urls.length} 个文件`);
    urls.forEach((entry, index) => {
      window.setTimeout(() => {
        const a = document.createElement("a");
        a.href = entry.href;
        a.download = entry.name;
        a.rel = "noopener";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }, 120 + index * 280);
    });
  }

  async function cancelOfferDownload(offer, button) {
    if (!offer || app.offerBusy.has(offer.id)) return;
    app.offerBusy.add(offer.id);
    if (button) {
      button.disabled = true;
      button.textContent = "取消中…";
    }
    try {
      await api(`/api/v1/web/offers/${encodeURIComponent(offer.id)}/cancel`, {
        method: "POST",
        timeout: 8000,
      });
      app.offerStatus.set(offer.id, "cancelled");
      showToast("已取消下载", "info", 2800);
      setSRStatus("已取消下载");
      renderOffers(true);
      renderTransfers(true);
    } catch (error) {
      if (button) {
        button.disabled = false;
        button.textContent = "取消下载";
      }
      if (error.status !== 401) {
        showToast(friendlyError(error, "取消下载失败，请重试。"), "error", 3600);
      }
    } finally {
      app.offerBusy.delete(offer.id);
    }
  }

  async function respondOffer(offer, accept, isFiles, acceptButton, rejectButton) {    if (!offer || app.offerBusy.has(offer.id)) return;
    app.offerBusy.add(offer.id);
    if (acceptButton) {
      acceptButton.disabled = true;
      if (accept) acceptButton.textContent = "处理中…";
    }
    if (rejectButton) rejectButton.disabled = true;
    try {
      const result = await api(`/api/v1/web/offers/${encodeURIComponent(offer.id)}/respond`, {
        method: "POST",
        body: { accept: !!accept },
        timeout: 12000,
      });
      const status = result && result.status ? String(result.status) : accept ? "accepted" : "rejected";
      app.offerStatus.set(offer.id, status);
      if (accept) {
        if (!isFiles) {
          const copied = await copyText(offer.text, { silent: true });
          showToast(copied ? "文本已接收，并复制到剪贴板" : "文本已接收", copied ? "success" : "info", 3200);
          setSRStatus("已接收电脑发来的文本");
        } else {
          autoDownloadOffer(offer);
        }
      } else {
        showToast("已忽略这次接收", "info");
      }
      renderOffers(true);
    } catch (error) {
      if (error.status !== 401) {
        app.offerStatus.delete(offer.id);
        showToast(friendlyError(error, "处理接收请求失败，请重试。"), "error", 3800);
      }
      renderOffers(true);
    } finally {
      app.offerBusy.delete(offer.id);
    }
  }

  /* ------------------------------------------------------------------------
     11. 渲染 — 传输
     ------------------------------------------------------------------------ */
  const TERMINAL_STATUSES = new Set(["completed", "failed", "rejected", "cancelled"]);

  function isTerminal(status) {
    return TERMINAL_STATUSES.has(status);
  }

  function findUploadTransfer() {
    const upload = app.upload;
    if (!upload || !Array.isArray(upload.fileIds) || upload.fileIds.length === 0) return null;
    if (!app.state || !Array.isArray(app.state.transfers)) return null;
    const ids = new Set(upload.fileIds);
    return (
      app.state.transfers.find(
        (transfer) =>
          transfer &&
          transfer.kind === "files" &&
          Array.isArray(transfer.files) &&
          transfer.files.some((file) => ids.has(file.id))
      ) || null
    );
  }

  function buildSyntheticUpload() {
    const upload = app.upload;
    if (!upload) return null;
    const state = app.state || {};
    const device = state.device || {};
    const status =
      upload.status === "completed"
        ? "completed"
        : upload.status === "failed"
          ? "failed"
          : upload.status === "preparing"
            ? "pending"
            : "active";
    const files = upload.files.map((item) => ({
      id: item.id,
      name: item.name,
      rel_path: item.relPath,
      size: item.size,
      done: item.done ? item.size : 0,
      status: item.done ? "completed" : "pending",
    }));
    return {
      id: `local-${upload.startedAt}`,
      direction: "in",
      via: "web",
      kind: "files",
      peer: { id: `web:${app.webId}`, alias: state.web ? state.web.name : app.phoneName, device_type: "web" },
      files,
      text: "",
      status,
      total_bytes: upload.totalBytes,
      done_bytes: upload.completedBytes + upload.currentLoaded,
      speed: upload.speed,
      eta: upload.eta,
      current_file: upload.currentName,
      started_at: upload.startedAt / 1000,
      finished_at: upload.finishedAt ? upload.finishedAt / 1000 : null,
      error: upload.error || "",
      __localUpload: true,
      __deviceAlias: safeText(device.alias, "电脑"),
    };
  }

  function renderTransfers(force = false) {
    if (!app.state) return;
    const state = app.state;
    const all = Array.isArray(state.transfers) ? state.transfers.filter((t) => t && t.kind === "files") : [];
    const upload = app.upload;
    const matched = findUploadTransfer();
    const matchedId = matched ? matched.id : "";
    const active = [];
    const recent = [];
    all.forEach((transfer) => {
      if (isTerminal(transfer.status)) {
        recent.push(transfer);
      } else {
        active.push(transfer);
      }
    });
    active.sort((a, b) => Number(b.started_at || 0) - Number(a.started_at || 0));
    recent.sort(
      (a, b) =>
        Number(b.finished_at || b.started_at || 0) - Number(a.finished_at || a.started_at || 0)
    );
    let display = active.concat(recent.slice(0, 3));
    if (upload && !matched) {
      const synthetic = buildSyntheticUpload();
      if (synthetic) display = [synthetic].concat(display);
    }
    if (display.length > 10) display = display.slice(0, 10);

    const signature = JSON.stringify({
      upload: upload
        ? [
            upload.status,
            upload.completedBytes,
            upload.currentLoaded,
            upload.currentIndex,
            upload.currentName,
            upload.speed,
            upload.eta,
            upload.error,
            upload.files.length,
            upload.totalBytes,
            upload.startedAt,
          ]
        : null,
      transfers: display.map((transfer) => [
        transfer.id,
        transfer.status,
        transfer.direction,
        transfer.via,
        transfer.total_bytes,
        transfer.done_bytes,
        Math.round(Number(transfer.speed) || 0),
        transfer.eta,
        transfer.current_file,
        transfer.error,
        transfer.finished_at,
        Array.isArray(transfer.files) ? transfer.files.length : 0,
      ]),
    });

    const activeCount = display.filter((transfer) => !isTerminal(effectiveTransferStatus(transfer))).length;
    if (ui.transfersSummary) {
      ui.transfersSummary.textContent =
        activeCount > 0 ? `${activeCount} 个进行中` : "";
    }
    if (ui.transfersEmpty) ui.transfersEmpty.hidden = display.length > 0;

    if (!force && !setSignature("transfers", signature)) return;

    const list = ui.transfersList;
    if (!list) return;
    clearNode(list);
    display.forEach((transfer) => {
      const local = upload && transfer.id === matchedId ? upload : null;
      const card = buildTransferCard(transfer, local);
      if (card) list.appendChild(card);
    });
  }

  function effectiveTransferStatus(transfer) {
    if (transfer && transfer.__localUpload) return transfer.status;
    return transfer ? transfer.status : "";
  }

  function transferStatusMeta(status, transfer, local) {
    if (status === "waiting" || status === "pending") {
      return { label: "等待中", className: "is-warning" };
    }
    if (status === "active") {
      let label = "发送中";
      if (transfer && transfer.via === "peer") {
        label = transfer.direction === "out" ? "发送中" : "接收中";
      } else if (transfer && transfer.direction === "out") {
        label = "接收中";
      } else if (!local && transfer && transfer.peer && transfer.peer.id !== `web:${app.webId}`) {
        label = "上传中";
      }
      return { label, className: "is-active" };
    }
    if (status === "verifying") return { label: "校验中", className: "is-active" };
    if (status === "completed") return { label: "已完成", className: "is-done" };
    if (status === "failed") return { label: "失败", className: "is-error" };
    if (status === "rejected") return { label: "已拒绝", className: "is-muted" };
    if (status === "cancelled") return { label: "已取消", className: "is-muted" };
    return { label: safeText(status, "未知"), className: "is-muted" };
  }

  function transferDirectionLabel(transfer, isLocal) {
    if (!transfer) return "";
    if (transfer.via === "peer") {
      return "电脑互传";
    }
    if (transfer.direction === "out") {
      return "来自电脑";
    }
    if (isLocal || (transfer.peer && transfer.peer.id === `web:${app.webId}`)) {
      return `发送至 ${transfer.__deviceAlias || safeText((app.state.device || {}).alias, "电脑")}`;
    }
    return "网页上传";
  }

  function buildTransferCard(transfer, localUpload) {
    const card = cloneTemplate(ui.templates.transfer);
    if (!card) return null;
    const local = localUpload || (transfer && transfer.__localUpload ? app.upload : null);
    const files = Array.isArray(transfer.files) ? transfer.files : [];
    let status = effectiveTransferStatus(transfer);
    let total = Number(transfer.total_bytes) || 0;
    let done = Number(transfer.done_bytes) || 0;
    let speed = Number(transfer.speed) || 0;
    let eta = transfer.eta;
    let currentFile = safeText(transfer.current_file);
    let error = safeText(transfer.error);

    if (local) {
      total = Number(local.totalBytes) || total;
      done =
        local.status === "completed"
          ? total
          : clamp(Number(local.completedBytes || 0) + Number(local.currentLoaded || 0), 0, total);
      speed = Number(local.speed) || 0;
      eta = local.eta;
      currentFile = safeText(local.currentName);
      error = safeText(local.error);
      if (local.status === "completed") status = "completed";
      else if (local.status === "failed") status = "failed";
      else if (local.status === "preparing") status = "pending";
      else status = "active";
    }

    if (status === "verifying" || status === "completed") {
      done = total;
    }
    done = clamp(done, 0, total || done);
    const percent = total > 0 ? clamp(Math.round((done / total) * 100), 0, 100) : status === "completed" ? 100 : 0;
    const meta = transferStatusMeta(status, transfer, Boolean(local));

    card.dataset.transferId = transfer.id;
    card.classList.toggle("is-complete", status === "completed");
    card.classList.toggle("is-error", status === "failed");

    const iconUse = card.querySelector(".transfer-icon use");
    if (iconUse) {
      iconUse.setAttribute("href", status === "completed" ? "#i-check" : transfer.direction === "out" ? "#i-download" : "#i-upload");
    }

    let title = "";
    if (files.length === 1) {
      title = safeText(files[0].name, "未命名文件");
    } else if (files.length > 1) {
      title = `${safeText(files[0].name, "文件")} 等 ${files.length} 个文件`;
    } else if (transfer.kind === "text") {
      title = "文本";
    } else {
      title = "文件传输";
    }
    setNodeText(card, ".transfer-title", title);

    const dirLabel = transferDirectionLabel(transfer, Boolean(local));
    const subParts = [dirLabel];
    if (files.length > 0) subParts.push(`${files.length} 个文件`);
    if (total > 0) subParts.push(formatBytes(total));
    setNodeText(card, ".transfer-sub", subParts.filter(Boolean).join(" · "));

    const pill = card.querySelector(".status-pill");
    if (pill) {
      pill.textContent = meta.label;
      pill.className = `status-pill ${meta.className}`;
    }

    const current = card.querySelector(".transfer-current");
    if (current) {
      let text = "";
      if (status === "active" && currentFile) {
        const indexText = local && local.files.length > 1 ? `${local.currentIndex + 1}/${local.files.length} · ` : "";
        text = `正在传输 ${indexText}${currentFile}`;
      } else if (status === "pending" && local) {
        text = "正在建立传输会话…";
      } else if (status === "verifying") {
        text = "正在校验文件完整性";
      }
      current.textContent = text;
      current.hidden = !text;
    }

    const fill = card.querySelector(".progress-fill");
    if (fill) fill.style.width = `${percent}%`;

    setNodeText(card, ".progress-pct", `${percent}%`);
    let stats = "";
    if (status === "active") {
      if (speed > 0) {
        stats = `${formatSpeed(speed)} · ${formatEta(eta)}`;
      } else {
        stats = `${formatBytes(done)} / ${formatBytes(total)}`;
      }
    } else if (status === "verifying") {
      stats = "正在校验";
    } else if (status === "pending") {
      stats = "准备中";
    } else if (status === "completed") {
      const started = Number(transfer.started_at) || 0;
      const finished = Number(transfer.finished_at) || 0;
      const duration = started && finished && finished >= started ? formatDuration(finished - started) : "";
      const avgSpeed =
        Number(transfer.avg_speed || transfer.speed) ||
        (total > 0 && finished > started ? total / (finished - started) : 0);
      stats = [
        formatBytes(total),
        avgSpeed > 0 ? formatSpeed(avgSpeed) : "",
        duration,
      ].filter(Boolean).join(" · ");
    } else {
      stats = `${formatBytes(done)} / ${formatBytes(total)}`;
    }
    setNodeText(card, ".transfer-stats", stats);

    const errorNode = card.querySelector(".transfer-error");
    if (errorNode) {
      errorNode.textContent = status === "failed" ? error || "传输失败" : "";
      errorNode.hidden = !(status === "failed" && (error || true));
    }

    return card;
  }

  function scheduleUploadProgressRender() {
    if (app.uploadRenderTimer) return;
    app.uploadRenderTimer = window.setTimeout(() => {
      app.uploadRenderTimer = 0;
      renderTransfers(true);
    }, 120);
  }

  function noteUploadProgress(forceSample = false) {
    const upload = app.upload;
    if (!upload) return;
    const now = performance.now();
    if (!upload.samples) upload.samples = [];
    const loaded = Number(upload.completedBytes || 0) + Number(upload.currentLoaded || 0);
    if (forceSample || !app.lastSampleAt || now - app.lastSampleAt >= 120) {
      app.lastSampleAt = now;
      upload.samples.push({ t: now, bytes: loaded });
      while (upload.samples.length > 2 && now - upload.samples[0].t > 4000) {
        upload.samples.shift();
      }
    }
    if (upload.samples.length >= 2) {
      const first = upload.samples[0];
      const last = upload.samples[upload.samples.length - 1];
      const dt = (last.t - first.t) / 1000;
      if (dt > 0.18) {
        const calculated = Math.max(0, (last.bytes - first.bytes) / dt);
        if (calculated > 0) {
          upload.speed = calculated;
          const remaining = Math.max(0, (upload.totalBytes || 0) - loaded);
          upload.eta = remaining > 0 ? remaining / calculated : 0;
        }
      }
    }
    scheduleUploadProgressRender();
  }

  /* ------------------------------------------------------------------------
     12. 渲染 — 文本 / 历史
     ------------------------------------------------------------------------ */
  function renderTexts(force = false) {
    if (!app.state) return;
    const texts = Array.isArray(app.state.texts) ? app.state.texts : [];
    const signature = JSON.stringify({
      ids: texts.map((text) => [text.id, text.clipboard, text.direction]),
      expanded: app.textExpanded,
    });
    if (!force && !setSignature("texts", signature)) {
      /* 仍同步空态，避免状态变化漏更新 */
    } else {
      clearNode(ui.textsList);
      const limit = app.textExpanded ? texts.length : 4;
      texts.slice(0, limit).forEach((text) => {
        const row = cloneTemplate(ui.templates.textItem);
        if (!row) return;
        setNodeText(row, ".text-content", safeText(text.text));
        let kind = text.direction === "in" ? "我发出" : "电脑发来";
        if (text.direction === "in" && text.clipboard) kind += " · 已复制";
        setNodeText(row, ".text-kind", kind);
        setNodeText(row, ".text-time", formatRelative(text.created));
        const copyButton = row.querySelector(".copy-btn");
        if (copyButton) {
          copyButton.addEventListener("click", () => copyText(text.text));
        }
        ui.textsList.appendChild(row);
      });
    }

    const hasTexts = texts.length > 0;
    if (ui.textsCard) ui.textsCard.hidden = !hasTexts;
    if (ui.textsEmpty) ui.textsEmpty.hidden = hasTexts;
    if (ui.textsToggle) {
      const more = texts.length > 4;
      ui.textsToggle.hidden = !more;
      if (more) ui.textsToggle.textContent = app.textExpanded ? "收起" : `展开全部（${texts.length}）`;
    }
  }

  function historyStatusMeta(status) {
    if (status === "completed") return { label: "已完成", className: "is-done" };
    if (status === "failed") return { label: "失败", className: "is-error" };
    if (status === "rejected") return { label: "已拒绝", className: "is-muted" };
    if (status === "cancelled") return { label: "已取消", className: "is-muted" };
    if (status === "active" || status === "verifying") return { label: "进行中", className: "is-active" };
    return { label: "等待中", className: "is-muted" };
  }

  function historyTitle(entry) {
    const files = Array.isArray(entry.files) ? entry.files : [];
    if (files.length === 1) return safeText(files[0].name, "文件传输");
    if (files.length > 1) return `${safeText(files[0].name, "文件")} 等 ${files.length} 个文件`;
    if (entry.text) {
      const firstLine = String(entry.text).split(/\r?\n/).find((line) => line.trim()) || String(entry.text);
      return firstLine.length > 42 ? `${firstLine.slice(0, 42)}…` : firstLine;
    }
    return entry.kind && String(entry.kind).includes("text") ? "文本" : "传输记录";
  }

  function buildHistoryItem(entry) {
    const row = cloneTemplate(ui.templates.historyItem);
    if (!row) return null;
    const meta = historyStatusMeta(entry.status);
    setNodeText(row, ".history-title", historyTitle(entry));
    const peer = entry.peer && entry.peer.alias ? safeText(entry.peer.alias) : "未知设备";
    const via = entry.via === "web" ? "网页" : "局域网";
    const size = Number(entry.total_bytes) > 0 ? ` · ${formatBytes(entry.total_bytes)}` : "";
    setNodeText(row, ".history-sub", `${peer} · ${via}${size}`);
    setNodeText(row, ".history-time", formatClock(entry.finished_at || entry.started_at));
    const stateNode = row.querySelector(".history-state");
    if (stateNode) {
      stateNode.textContent = meta.label;
      stateNode.className = `history-state ${meta.className === "is-done" || meta.className === "is-error" || meta.className === "is-active" ? meta.className : ""}`;
    }
    const dot = row.querySelector(".history-dot");
    if (dot) dot.className = `history-dot ${meta.className}`;
    return row;
  }

  function renderHistory(force = false) {
    if (!app.state) return;
    const entries = Array.isArray(app.state.history) ? app.state.history : [];
    const signature = JSON.stringify(
      entries.map((entry) => [entry.id, entry.status, entry.finished_at, entry.files ? entry.files.length : 0])
    );
    if (!force && !setSignature("history", signature)) return;
    clearNode(ui.historyPreview);
    clearNode(ui.historySheetList);
    entries.slice(0, 3).forEach((entry) => {
      const row = buildHistoryItem(entry);
      if (row) ui.historyPreview.appendChild(row);
    });
    const sheetBody = ui.historySheet.querySelector(".sheet-body");
    const scrollTop = sheetBody ? sheetBody.scrollTop : 0;
    entries.forEach((entry) => {
      const row = buildHistoryItem(entry);
      if (row) ui.historySheetList.appendChild(row);
    });
    if (sheetBody) sheetBody.scrollTop = scrollTop;
    const hasEntries = entries.length > 0;
    if (ui.historyPreview) ui.historyPreview.hidden = !hasEntries;
    if (ui.historyEmpty) ui.historyEmpty.hidden = hasEntries;
    if (ui.historySheetEmpty) ui.historySheetEmpty.hidden = hasEntries;
  }

  /* ------------------------------------------------------------------------
     13. 发送文件 — 选择 / 面板 / 上传
     ------------------------------------------------------------------------ */
  function canStartUpload() {
    if (!app.state || !app.token) {
      showToast("还没有连接到电脑", "error");
      return false;
    }
    if (app.upload && (app.upload.status === "preparing" || app.upload.status === "uploading")) {
      showToast("正在发送文件，请等这次传输完成", "info");
      return false;
    }
    return true;
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []).filter((file) => file && typeof file.size === "number");
    if (!incoming.length) return;
    if (!canStartUpload()) return;
    const existing = new Set(app.selection.map((item) => item.key));
    let added = 0;
    incoming.forEach((file) => {
      const name = safeText(file.name, "未命名文件");
      const relPath = safeText(file.webkitRelativePath || file.name, name) || name;
      const key = `${relPath}|${file.size}|${file.lastModified}`;
      if (existing.has(key)) return;
      existing.add(key);
      app.selection.push({
        id: randomHex32(),
        file,
        name,
        relPath,
        size: Number(file.size) || 0,
        key,
        done: false,
      });
      added += 1;
    });
    if (!added) {
      showToast("这些文件已经在待发送列表里了", "info");
      return;
    }
    renderSendList();
    openSheet("send-sheet", ui.sendFiles);
  }

  function renderSendList() {
    if (!ui.sendList) return;
    clearNode(ui.sendList);
    let total = 0;
    app.selection.forEach((item) => {
      total += item.size;
      const row = cloneTemplate(ui.templates.fileRow);
      if (!row) return;
      setNodeText(row, ".file-row-name", item.name);
      const dir = dirnameOf(item.relPath);
      setNodeText(row, ".file-row-meta", `${dir ? `${dir} · ` : ""}${formatBytes(item.size)}`);
      const remove = row.querySelector(".file-remove");
      if (remove) {
        remove.setAttribute("aria-label", `移除 ${item.name}`);
        remove.addEventListener("click", () => {
          app.selection = app.selection.filter((entry) => entry !== item);
          renderSendList();
          if (!app.selection.length) closeSheet();
        });
      }
      ui.sendList.appendChild(row);
    });
    if (ui.sendCount) ui.sendCount.textContent = String(app.selection.length);
    if (ui.sendTotal) ui.sendTotal.textContent = formatBytes(total);
    if (ui.sendConfirm) {
      ui.sendConfirm.disabled = app.selection.length === 0;
      ui.sendConfirm.textContent =
        app.selection.length > 1 ? `发送 ${app.selection.length} 个文件` : "发送文件";
    }
    if (ui.sendTargetName && app.state && app.state.device) {
      ui.sendTargetName.textContent = safeText(app.state.device.alias, "这台电脑");
    }
  }

  function openSendSheet(trigger) {
    if (!app.selection.length) return;
    renderSendList();
    openSheet("send-sheet", trigger);
  }

  function beginSend() {
    if (!app.selection.length) return;
    if (!canStartUpload()) return;
    const items = app.selection.slice();
    app.selection = [];
    closeSheet({ restoreFocus: false });
    startUpload(items);
  }

  async function startUpload(items) {
    if (!items || !items.length) return;
    if (app.uploadClearTimer) {
      window.clearTimeout(app.uploadClearTimer);
      app.uploadClearTimer = 0;
    }
    const totalBytes = items.reduce((sum, item) => sum + (Number(item.size) || 0), 0);
    app.upload = {
      status: "preparing",
      files: items.map((item) => ({
        id: item.id,
        file: item.file,
        name: item.name,
        relPath: item.relPath,
        size: item.size,
        done: false,
      })),
      fileIds: items.map((item) => item.id),
      totalBytes,
      completedBytes: 0,
      currentLoaded: 0,
      currentIndex: 0,
      currentName: "",
      speed: 0,
      eta: null,
      error: "",
      sessionId: "",
      sessionToken: "",
      startedAt: Date.now(),
      finishedAt: 0,
      samples: [],
    };
    app.lastSampleAt = 0;
    noteUploadProgress(true);
    renderTransfers(true);

    try {
      const payloadFiles = items.map((item) => ({
        id: item.id,
        name: item.name,
        rel_path: item.relPath,
        size: item.size,
      }));
      const request = await api("/api/v1/web/request", {
        method: "POST",
        body: { files: payloadFiles, text: "" },
        timeout: 20000,
      });
      if (!request || !request.session_id) {
        throw new ClientError("电脑没有返回传输会话，请重试。", 0);
      }
      app.upload.sessionId = String(request.session_id);
      app.upload.sessionToken = String(request.session_token || "");
      const tokens = request.tokens && typeof request.tokens === "object" ? request.tokens : {};
      const resume = request.resume && typeof request.resume === "object" ? request.resume : {};

      for (let index = 0; index < items.length; index += 1) {
        if (!app.upload) return;
        const item = items[index];
        const token = safeText(tokens[item.id]);
        if (!token) {
          throw new ClientError("电脑没有返回文件令牌，请重新发送。", 0);
        }
        const uploadItem = app.upload.files[index];
        app.upload.status = "uploading";
        app.upload.currentIndex = index;
        app.upload.currentName = item.name;
        const resumeOffset = clamp(Number(resume[item.id]) || 0, 0, item.size);
        app.upload.currentLoaded = resumeOffset;
        noteUploadProgress(true);
        await uploadOneFile(uploadItem, token, resumeOffset);
        await completeOneFile(uploadItem, token);
        app.upload.completedBytes += item.size;
        app.upload.currentLoaded = 0;
        uploadItem.done = true;
        app.upload.speed = 0;
        app.upload.eta = 0;
        noteUploadProgress(true);
      }

      app.upload.status = "completed";
      app.upload.finishedAt = Date.now();
      app.upload.speed = 0;
      app.upload.eta = 0;
      app.upload.currentLoaded = 0;
      app.upload.completedBytes = totalBytes;
      app.upload.error = "";
      renderTransfers(true);
      const deviceName = app.state && app.state.device ? app.state.device.alias : "电脑";
      const toastText =
        items.length === 1
          ? `已发送 ${items[0].name} 到 ${deviceName}`
          : `已发送 ${items.length} 个文件到 ${deviceName}`;
      showToast(toastText, "success", 4200);
      setSRStatus("文件发送完成");
      app.uploadClearTimer = window.setTimeout(() => {
        if (app.upload && app.upload.status === "completed") {
          app.upload = null;
          app.lastSampleAt = 0;
          renderTransfers(true);
        }
      }, 5000);
    } catch (error) {
      if (!app.upload) return;
      app.upload.status = "failed";
      app.upload.finishedAt = Date.now();
      app.upload.speed = 0;
      app.upload.eta = null;
      app.upload.error = friendlyError(error, "文件没有发送完成，请重试。");
      renderTransfers(true);
      if (error.status !== 401) {
        showToast(`发送失败：${app.upload.error}`, "error", 5200);
      }
      setSRStatus("文件发送失败");
      app.uploadClearTimer = window.setTimeout(() => {
        if (app.upload && app.upload.status === "failed") {
          app.upload = null;
          app.lastSampleAt = 0;
          renderTransfers(true);
        }
      }, 15000);
    }
  }

  function xhrUpload(options) {
    return new Promise((resolve, reject) => {
      const { sessionId, fileId, token, file, offset, onProgress } = options;
      const query = new URLSearchParams({
        session_id: sessionId,
        file_id: fileId,
        token,
        offset: String(offset),
      });
      let xhr;
      try {
        xhr = new XMLHttpRequest();
      } catch (_) {
        reject(new ClientError("当前浏览器无法上传文件。", 0));
        return;
      }
      xhr.open("POST", `/api/v1/transfer/upload?${query.toString()}`, true);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.responseType = "text";
      xhr.upload.onprogress = (event) => {
        if (event && event.lengthComputable) {
          onProgress(Number(event.loaded) || 0, Number(event.total) || 0);
        }
      };
      xhr.onload = () => {
        let data = null;
        try {
          data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
        } catch (_) {
          data = null;
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          if (data && typeof data === "object") {
            resolve(data);
          } else {
            reject(new ClientError("电脑返回了无法识别响应，请重试。", 0));
          }
          return;
        }
        reject(
          new ClientError(
            (data && data.error) || `上传失败（${xhr.status}）`,
            xhr.status,
            data
          )
        );
      };
      xhr.onerror = () => {
        reject(new ClientError("网络中断，正在尝试续传…", 0));
      };
      xhr.onabort = () => {
        reject(new ClientError("上传已中止。", -1));
      };
      try {
        const body = offset > 0 ? file.slice(offset) : file;
        xhr.send(body);
      } catch (_) {
        reject(new ClientError("浏览器无法读取这个文件。", 0));
      }
    });
  }

  async function uploadOneFile(uploadItem, token, initialOffset) {
    const size = Number(uploadItem.size) || 0;
    let offset = clamp(Number(initialOffset) || 0, 0, size);
    let retries = 0;
    while (true) {
      if (!app.upload || app.upload.status !== "uploading") {
        throw new ClientError("传输已中止。", -1);
      }
      if (size > 0 && offset >= size) return;
      try {
        const result = await xhrUpload({
          sessionId: app.upload.sessionId,
          fileId: uploadItem.id,
          token,
          file: uploadItem.file,
          offset,
          onProgress: (loaded) => {
            if (!app.upload) return;
            app.upload.currentLoaded = clamp(offset + loaded, 0, size);
            noteUploadProgress();
          },
        });
        const received = clamp(Number(result.received) || 0, 0, size);
        if (result.complete || (size > 0 && received >= size)) {
          if (app.upload) app.upload.currentLoaded = size;
          noteUploadProgress(true);
          return;
        }
        if (received > offset) offset = received;
        retries += 1;
        if (retries > MAX_FILE_RETRIES) {
          throw new ClientError("文件上传没有完成，请重试。", 0);
        }
        await sleep(400 * retries);
      } catch (error) {
        if (error.status === -1) throw error;
        if ([403, 404, 410, 413, 507].includes(error.status)) throw error;
        retries += 1;
        if (retries > MAX_FILE_RETRIES) throw error;
        await sleep(600 * retries);
        let recovered = offset;
        if (error.data && Number.isFinite(Number(error.data.received))) {
          recovered = Number(error.data.received);
        } else {
          try {
            const query = new URLSearchParams({
              session_id: app.upload.sessionId,
              file_id: uploadItem.id,
              token,
            });
            const status = await api(`/api/v1/transfer/status?${query.toString()}`, {
              auth: false,
              timeout: 10000,
              handle401: false,
            });
            recovered = Number(status.received) || 0;
          } catch (statusError) {
            if ([403, 404].includes(statusError.status)) throw error;
          }
        }
        offset = clamp(recovered, 0, size);
        if (app.upload) app.upload.currentLoaded = offset;
        noteUploadProgress(true);
        if (size > 0 && offset >= size) return;
      }
    }
  }

  async function completeOneFile(uploadItem, token) {
    let lastError = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      if (!app.upload) throw new ClientError("传输已中止。", -1);
      try {
        return await api("/api/v1/transfer/complete", {
          method: "POST",
          timeout: 20000,
          handle401: false,
          body: {
            session_id: app.upload.sessionId,
            file_id: uploadItem.id,
            token,
            sha256: "",
          },
        });
      } catch (error) {
        lastError = error;
        if (error.status === 401 || error.status === 403 || error.status === 404 || error.status === 422) {
          throw error;
        }
        await sleep(700 * (attempt + 1));
      }
    }
    throw lastError || new ClientError("文件校验失败，请重试。", 0);
  }

  /* ------------------------------------------------------------------------
     14. 文本发送
     ------------------------------------------------------------------------ */
  function updateTextCount() {
    if (!ui.textInput || !ui.textCount) return;
    const length = ui.textInput.value.length;
    ui.textCount.textContent = `${length} / ${MAX_TEXT}`;
    if (ui.textSend) ui.textSend.disabled = !ui.textInput.value.trim();
  }

  async function submitText() {
    const text = ui.textInput.value;
    if (!text.trim()) {
      showToast("先写点什么吧", "info", 1800);
      ui.textInput.focus();
      return;
    }
    if (ui.textSend.disabled && ui.textSend.classList.contains("is-loading")) return;
    ui.textSend.classList.add("is-loading");
    ui.textSend.disabled = true;
    try {
      const result = await api("/api/v1/web/text", {
        method: "POST",
        body: { text },
        timeout: 12000,
      });
      ui.textInput.value = "";
      updateTextCount();
      if (result && result.clipboard === false) {
        showToast("已发送，但电脑剪贴板暂时不可用", "info", 3400);
      } else {
        showToast("已发送，电脑已复制到剪贴板", "success", 3000);
      }
      setSRStatus("文本已发送");
    } catch (error) {
      if (error.status !== 401) {
        showToast(friendlyError(error, "文本没有发送成功。"), "error", 4000);
      }
    } finally {
      ui.textSend.classList.remove("is-loading");
      updateTextCount();
    }
  }

  /* ------------------------------------------------------------------------
     15. 设置抽屉
     ------------------------------------------------------------------------ */
  function openSettings(trigger) {
    renderSettings();
    openSheet("settings-sheet", trigger || ui.settingsBtn);
  }

  function renderSettings() {
    const state = app.state;
    if (!state) return;
    const device = state.device || {};
    const settings = state.settings || {};
    const web = state.web || {};
    const deviceAlias = safeText(device.alias, "这台电脑");

    if (ui.settingsWebName) ui.settingsWebName.textContent = safeText(web.name, app.phoneName);
    if (ui.settingsWebMeta) ui.settingsWebMeta.textContent = `已与 ${deviceAlias} 配对`;
    if (ui.settingsDeviceName) ui.settingsDeviceName.textContent = deviceAlias;
    if (ui.settingsAddress) {
      ui.settingsAddress.textContent = `${safeText(device.ip, location.hostname)}:${safeText(device.port, location.port || "47820")}`;
    }
    if (ui.settingsDir) {
      const dir = safeText(settings.download_dir, "—");
      ui.settingsDir.textContent = dir || "—";
      ui.settingsDir.title = dir || "";
    }
    if (ui.copyDir) ui.copyDir.disabled = !settings.download_dir;
    if (ui.settingsPairing) {
      const enabled = !!(settings.web_pairing !== undefined ? settings.web_pairing : state.pairing && state.pairing.enabled);
      ui.settingsPairing.textContent = enabled ? "已启用" : "已关闭";
    }
    if (ui.settingsSessions) {
      const sessions = Array.isArray(state.web_sessions) ? state.web_sessions : [];
      const online = sessions.filter((session) => session && session.online).length;
      ui.settingsSessions.textContent = sessions.length
        ? `${online} 个在线 · 共 ${sessions.length} 个`
        : "—";
    }
    if (ui.settingsVersion) {
      const version = safeText(settings.version || state.version, "—");
      ui.settingsVersion.textContent = version === "—" ? "—" : `v${version}`;
    }
    if (ui.autoAcceptToggle && !app.autoAcceptBusy) {
      const enabled = !!(settings.auto_accept !== undefined ? settings.auto_accept : device.auto_accept);
      ui.autoAcceptToggle.setAttribute("aria-checked", enabled ? "true" : "false");
    }
    if (ui.settingsWebMeta && web.name) {
      ui.settingsWebMeta.title = `${web.name} · ${deviceAlias}`;
    }
    if (ui.httpsToggle && !app.httpsBusy) {
      const tlsEnabled = !!settings.tls_enabled;
      const preferHttps = !!(settings.prefer_https && tlsEnabled);
      ui.httpsToggle.setAttribute("aria-checked", preferHttps ? "true" : "false");
      ui.httpsToggle.disabled = !tlsEnabled;
      ui.httpsToggle.title = tlsEnabled
        ? "开启后二维码和电脑间传输优先使用 HTTPS"
        : (settings.tls_error || "HTTPS 不可用");
    }
    if (ui.settingsScheme) {
      const onHttps = location.protocol === "https:";
      ui.settingsScheme.textContent = onHttps
        ? "HTTPS 已加密"
        : "HTTP 未加密";
    }
    if (ui.openHttps) {
      const tlsEnabled = !!settings.tls_enabled;
      const onHttps = location.protocol === "https:";
      ui.openHttps.disabled = !tlsEnabled;
      ui.openHttps.textContent = onHttps ? "改用 HTTP" : "改用 HTTPS";
      ui.openHttps.title = tlsEnabled
        ? "切换访问协议（需要重新配对一次）"
        : (settings.tls_error || "HTTPS 不可用");
    }
    updateInstallRow();
  }

  async function toggleHttps() {
    if (app.httpsBusy || !app.state || !ui.httpsToggle) return;
    const current = ui.httpsToggle.getAttribute("aria-checked") === "true";
    const next = !current;
    app.httpsBusy = true;
    ui.httpsToggle.setAttribute("aria-checked", next ? "true" : "false");
    ui.httpsToggle.disabled = true;
    try {
      const result = await api("/api/v1/web/settings", {
        method: "POST",
        body: { prefer_https: next },
        timeout: 12000,
      });
      if (result && result.settings) {
        app.state.settings = Object.assign({}, app.state.settings, result.settings);
      }
      showToast(
        next
          ? "已设为 HTTPS 优先，点「改用 HTTPS」切换本页"
          : "已切回 HTTP 优先",
        "success",
        3200
      );
    } catch (error) {
      ui.httpsToggle.setAttribute("aria-checked", current ? "true" : "false");
      if (error.status !== 401) {
        showToast(friendlyError(error, "HTTPS 设置没有保存。"), "error", 3600);
      }
    } finally {
      app.httpsBusy = false;
      ui.httpsToggle.disabled = false;
      renderSettings();
    }
  }

  function openOtherScheme() {
    const state = app.state || {};
    const settings = state.settings || {};
    if (!settings.tls_enabled) {
      showToast(settings.tls_error || "HTTPS 尚未就绪", "error", 3200);
      return;
    }
    const onHttps = location.protocol === "https:";
    let target = onHttps
      ? (state.http_url || state.device && state.device.web_url || "")
      : (state.https_url || state.device && state.device.web_url_https || "");
    if (!target) {
      showToast("没有可用的切换地址", "error", 2800);
      return;
    }
    const pairMatch = String(state.pair_url || "").match(/[?&]pair=([0-9]{6})/);
    if (pairMatch && !/[?&]pair=/.test(target)) {
      target += `?pair=${pairMatch[1]}`;
    }
    showToast(onHttps ? "正在切换到 HTTP…" : "正在切换到 HTTPS（首次需接受证书警告）…", "info", 3000);
    window.setTimeout(() => { window.location.href = target; }, 450);
  }

  async function toggleAutoAccept() {
    if (app.autoAcceptBusy || !app.state) return;
    const current = ui.autoAcceptToggle.getAttribute("aria-checked") === "true";
    const next = !current;
    app.autoAcceptBusy = true;
    ui.autoAcceptToggle.setAttribute("aria-checked", next ? "true" : "false");
    ui.autoAcceptToggle.disabled = true;
    try {
      const result = await api("/api/v1/web/settings", {
        method: "POST",
        body: { auto_accept: next },
        timeout: 12000,
      });
      if (result && result.settings) {
        app.state.settings = Object.assign({}, app.state.settings, result.settings);
      }
      if (result && result.device) {
        app.state.device = Object.assign({}, app.state.device, result.device);
      }
      showToast(next ? "已开启自动接受" : "已关闭自动接受", "success", 2400);
      setSRStatus(next ? "自动接受已开启" : "自动接受已关闭");
    } catch (error) {
      ui.autoAcceptToggle.setAttribute("aria-checked", current ? "true" : "false");
      if (error.status !== 401) showToast(friendlyError(error, "设置没有保存。"), "error", 3600);
    } finally {
      app.autoAcceptBusy = false;
      ui.autoAcceptToggle.disabled = false;
      renderSettings();
    }
  }

  function armDisconnect() {
    const now = Date.now();
    if (app.disconnectArmedUntil && now < app.disconnectArmedUntil) {
      doDisconnect();
      return;
    }
    app.disconnectArmedUntil = now + 4000;
    ui.disconnectBtn.textContent = "再次点击确认断开";
    if (app.disconnectTimer) window.clearTimeout(app.disconnectTimer);
    app.disconnectTimer = window.setTimeout(() => {
      app.disconnectArmedUntil = 0;
      ui.disconnectBtn.textContent = "重新配对";
    }, 4000);
  }

  function doDisconnect() {
    if (app.disconnectTimer) window.clearTimeout(app.disconnectTimer);
    app.disconnectArmedUntil = 0;
    if (ui.disconnectBtn) ui.disconnectBtn.textContent = "重新配对";
    clearSession();
    closeAllSheets(true, false);
    app.hasEnteredApp = false;
    showPairing("已断开连接，请输入电脑上新的配对码。");
  }

  /* ------------------------------------------------------------------------
     16. 抽屉 / 浮层管理
     ------------------------------------------------------------------------ */
  function setAppInert(inert) {
    if (!ui.appView) return;
    try {
      ui.appView.inert = !!inert;
    } catch (_) {
      /* ignore */
    }
  }

  function hideSheetImmediately(sheet) {
    if (!sheet) return;
    sheet.classList.remove("is-open");
    sheet.hidden = true;
    sheet.setAttribute("aria-hidden", "true");
    try {
      sheet.inert = true;
    } catch (_) {
      /* ignore */
    }
  }

  function openSheet(id, trigger) {
    const sheet = typeof id === "string" ? document.getElementById(id) : id;
    if (!sheet) return;
    if (app.activeSheet && app.activeSheet.el === sheet) return;
    if (app.activeSheet) {
      hideSheetImmediately(app.activeSheet.el);
      app.activeSheet = null;
    }
    ui.sheets.forEach((other) => {
      if (other !== sheet) hideSheetImmediately(other);
    });
    app.sheetEpoch += 1;
    const epoch = app.sheetEpoch;
    sheet.hidden = false;
    sheet.setAttribute("aria-hidden", "false");
    try {
      sheet.inert = false;
    } catch (_) {
      /* ignore */
    }
    if (ui.sheetBackdrop) {
      ui.sheetBackdrop.hidden = false;
      ui.sheetBackdrop.setAttribute("aria-hidden", "false");
    }
    document.body.classList.add("sheet-open");
    setAppInert(true);
    app.activeSheet = {
      el: sheet,
      trigger: trigger || document.activeElement,
      epoch,
    };
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (app.activeSheet && app.activeSheet.epoch === epoch) {
          sheet.classList.add("is-open");
          if (ui.sheetBackdrop) ui.sheetBackdrop.classList.add("is-open");
        }
      });
    });
    window.setTimeout(() => {
      if (!app.activeSheet || app.activeSheet.el !== sheet) return;
      const closeButton = sheet.querySelector(".sheet-head .icon-btn");
      if (closeButton) {
        try {
          closeButton.focus({ preventScroll: true });
        } catch (_) {
          closeButton.focus();
        }
      }
    }, 180);
  }

  function closeSheet(options = {}) {
    const active = app.activeSheet;
    if (!active) return;
    const { restoreFocus = true } = options;
    app.activeSheet = null;
    app.sheetEpoch += 1;
    const sheet = active.el;
    sheet.classList.remove("is-open");
    sheet.setAttribute("aria-hidden", "true");
    try {
      sheet.inert = true;
    } catch (_) {
      /* ignore */
    }
    if (ui.sheetBackdrop) ui.sheetBackdrop.classList.remove("is-open");
    document.body.classList.remove("sheet-open");
    setAppInert(false);
    const epoch = app.sheetEpoch;
    window.setTimeout(() => {
      if (app.sheetEpoch !== epoch || app.activeSheet) return;
      sheet.hidden = true;
      if (ui.sheetBackdrop) {
        ui.sheetBackdrop.hidden = true;
        ui.sheetBackdrop.setAttribute("aria-hidden", "true");
      }
    }, 430);
    if (restoreFocus && active.trigger && active.trigger.isConnected) {
      window.setTimeout(() => {
        if (app.activeSheet) return;
        try {
          active.trigger.focus({ preventScroll: true });
        } catch (_) {
          try {
            active.trigger.focus();
          } catch (__) {
            /* ignore */
          }
        }
      }, 30);
    }
  }

  function closeAllSheets(immediate = false, restoreFocus = false) {
    const active = app.activeSheet;
    app.activeSheet = null;
    app.sheetEpoch += 1;
    if (ui.sheets) {
      ui.sheets.forEach((sheet) => {
        if (!sheet) return;
        sheet.classList.remove("is-open");
        sheet.setAttribute("aria-hidden", "true");
        try {
          sheet.inert = true;
        } catch (_) {
          /* ignore */
        }
        if (immediate) sheet.hidden = true;
      });
    }
    if (ui.sheetBackdrop) {
      ui.sheetBackdrop.classList.remove("is-open");
      if (immediate) ui.sheetBackdrop.hidden = true;
    }
    document.body.classList.remove("sheet-open");
    setAppInert(false);
    if (!immediate) {
      const epoch = app.sheetEpoch;
      window.setTimeout(() => {
        if (app.sheetEpoch !== epoch || app.activeSheet) return;
        if (ui.sheets) ui.sheets.forEach((sheet) => (sheet.hidden = true));
        if (ui.sheetBackdrop) ui.sheetBackdrop.hidden = true;
      }, 430);
    }
    if (restoreFocus && active && active.trigger && active.trigger.isConnected) {
      try {
        active.trigger.focus({ preventScroll: true });
      } catch (_) {
        /* ignore */
      }
    }
  }

  function trapSheetFocus(event) {
    if (!app.activeSheet || event.key !== "Tab") return;
    const focusable = Array.from(
      app.activeSheet.el.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter((node) => node.getClientRects().length > 0);
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (!app.activeSheet.el.contains(active)) {
      event.preventDefault();
      first.focus();
      return;
    }
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function onGlobalKeydown(event) {
    if (event.key === "Escape" && app.activeSheet) {
      event.preventDefault();
      closeSheet();
      return;
    }
    trapSheetFocus(event);
  }

  /* ------------------------------------------------------------------------
     17. PWA / 安装
     ------------------------------------------------------------------------ */
  function registerServiceWorker() {
    if (app.swRegistered) return;
    if (!("serviceWorker" in navigator)) return;
    if (!window.isSecureContext) return;
    app.swRegistered = true;
    try {
      navigator.serviceWorker.register("./sw.js", { scope: "./" }).catch(() => {
        app.swRegistered = false;
      });
    } catch (_) {
      app.swRegistered = false;
    }
  }

  function updateInstallRow() {
    if (!ui.installRow) return;
    const installed = isStandalone();
    const supported = !!app.install.event || isIOS();
    ui.installRow.hidden = !(app.view === "app" && !installed && supported);
    if (ui.installBtn) {
      ui.installBtn.textContent = app.install.event ? "添加" : "方法";
    }
  }

  function maybeShowInstallBanner() {
    if (app.view !== "app" || !app.install.event || isStandalone()) return;
    if (app.install.dismissedUntil && Date.now() < app.install.dismissedUntil) return;
    if (app.install.bannerTimer) window.clearTimeout(app.install.bannerTimer);
    app.install.bannerTimer = window.setTimeout(() => {
      if (app.view !== "app" || app.activeSheet || isStandalone()) return;
      if (!app.install.event) return;
      if (app.install.dismissedUntil && Date.now() < app.install.dismissedUntil) return;
      ui.installBanner.hidden = false;
    }, 4200);
  }

  function hideInstallBanner() {
    if (!ui.installBanner) return;
    ui.installBanner.hidden = true;
    if (app.install.bannerTimer) {
      window.clearTimeout(app.install.bannerTimer);
      app.install.bannerTimer = 0;
    }
  }

  async function promptInstall() {
    const prompt = app.install.event;
    if (prompt) {
      hideInstallBanner();
      try {
        await prompt.prompt();
        const choice = prompt.userChoice ? await prompt.userChoice : null;
        if (!choice || choice.outcome !== "accepted") {
          app.install.dismissedUntil = Date.now() + INSTALL_SNOOZE_MS;
          store.set(STORAGE.installDismissed, String(app.install.dismissedUntil));
        }
      } catch (_) {
        /* ignore */
      }
      app.install.event = null;
      updateInstallRow();
      return;
    }
    if (isIOS()) {
      showToast("在 Safari 底部点击「分享」，选择「添加到主屏幕」", "info", 5200);
      return;
    }
    showToast("请使用浏览器菜单中的「添加到主屏幕」", "info", 4200);
  }

  function dismissInstallBanner() {
    hideInstallBanner();
    app.install.dismissedUntil = Date.now() + INSTALL_SNOOZE_MS;
    store.set(STORAGE.installDismissed, String(app.install.dismissedUntil));
  }

  /* ------------------------------------------------------------------------
     18. 事件绑定
     ------------------------------------------------------------------------ */
  function bindEvents() {
    ui.pairForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitPair();
    });
    ui.pairCode.addEventListener("input", () => {
      const clean = normalizeCode(ui.pairCode.value);
      if (ui.pairCode.value !== clean) ui.pairCode.value = clean;
      showPairError("");
    });
    ui.pairName.addEventListener("input", () => {
      showPairError("");
    });

    ui.themeToggle.addEventListener("click", toggleTheme);
    ui.themeChoices.forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.themeChoice === app.theme) return;
        applyTheme(button.dataset.themeChoice);
      });
    });
    ui.connChip.addEventListener("click", manualRefresh);
    ui.settingsBtn.addEventListener("click", () => openSettings(ui.settingsBtn));
    ui.modeButtons.forEach((button) => {
      button.addEventListener("click", () => setSendMode(button.dataset.mode));
    });
    ui.tabButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.tab === "settings") {
          openSettings(button);
          return;
        }
        setTab(button.dataset.tab);
      });
    });
    ui.settingsClose.addEventListener("click", () => closeSheet());
    ui.historyClose.addEventListener("click", () => closeSheet());
    ui.sendClose.addEventListener("click", () => closeSheet());
    ui.sendCancel.addEventListener("click", () => closeSheet());
    ui.sheetBackdrop.addEventListener("click", () => closeSheet());

    ui.openHistory.addEventListener("click", () => {
      renderHistory(true);
      openSheet("history-sheet", ui.openHistory);
    });
    ui.historySheet.addEventListener("click", (event) => {
      if (event.target === ui.historySheet) closeSheet();
    });

    ui.autoAcceptToggle.addEventListener("click", toggleAutoAccept);
    if (ui.httpsToggle) ui.httpsToggle.addEventListener("click", toggleHttps);
    if (ui.openHttps) ui.openHttps.addEventListener("click", openOtherScheme);
    ui.copyDir.addEventListener("click", () => {
      const dir = ui.settingsDir.textContent || "";
      if (dir && dir !== "—") copyText(dir);
    });
    ui.disconnectBtn.addEventListener("click", armDisconnect);

    ui.sendFiles.addEventListener("click", () => {
      if (!canStartUpload()) return;
      ui.fileInput.value = "";
      ui.fileInput.click();
    });
    ui.sendFolder.addEventListener("click", () => {
      if (!canStartUpload()) return;
      ui.folderInput.value = "";
      ui.folderInput.click();
    });
    ui.fileInput.addEventListener("change", () => {
      addFiles(ui.fileInput.files);
      ui.fileInput.value = "";
    });
    ui.folderInput.addEventListener("change", () => {
      addFiles(ui.folderInput.files);
      ui.folderInput.value = "";
    });
    ui.dropzone.addEventListener("click", () => {
      if (!canStartUpload()) return;
      ui.fileInput.value = "";
      ui.fileInput.click();
    });
    ui.dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        ui.dropzone.click();
      }
    });
    ["dragenter", "dragover"].forEach((name) => {
      ui.dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
        ui.dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "dragend"].forEach((name) => {
      ui.dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        event.stopPropagation();
        ui.dropzone.classList.remove("is-dragover");
      });
    });
    ui.dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      ui.dropzone.classList.remove("is-dragover");
      if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
        addFiles(event.dataTransfer.files);
      }
    });
    window.addEventListener("dragover", (event) => {
      if (event.dataTransfer && Array.from(event.dataTransfer.types || []).includes("Files")) {
        event.preventDefault();
      }
    });
    window.addEventListener("drop", (event) => {
      if (ui.dropzone && (event.target === ui.dropzone || ui.dropzone.contains(event.target))) return;
      if (event.dataTransfer && Array.from(event.dataTransfer.types || []).includes("Files")) {
        event.preventDefault();
      }
    });
    ui.sendConfirm.addEventListener("click", beginSend);

    ui.sendText.addEventListener("click", () => {
      setSendMode("text");
      ui.textInput.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => ui.textInput.focus(), 120);
    });
    ui.textForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitText();
    });
    ui.textInput.addEventListener("input", updateTextCount);
    ui.textInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        submitText();
      }
    });
    ui.textsToggle.addEventListener("click", () => {
      app.textExpanded = !app.textExpanded;
      renderTexts(true);
    });
    ui.deviceCopy.addEventListener("click", () => {
      const url = (app.state && app.state.web_url) || location.origin + "/";
      copyText(url);
    });

    ui.installAdd.addEventListener("click", promptInstall);
    ui.installDismiss.addEventListener("click", dismissInstallBanner);
    ui.installBtn.addEventListener("click", promptInstall);

    document.addEventListener("keydown", onGlobalKeydown);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && app.view === "app") {
        if (!app.connected) probeConnection({ quiet: true });
        if (app.renderQueued) scheduleRender();
      }
    });
    window.addEventListener("online", () => {
      app.lastNetworkOnline = true;
      updateConnection();
      if (app.view === "app" && !app.connected) probeConnection({ quiet: true });
    });
    window.addEventListener("offline", () => {
      app.lastNetworkOnline = false;
      app.connected = false;
      updateConnection();
    });
    window.addEventListener("pageshow", (event) => {
      if (event.persisted && app.view === "app" && app.token) {
        probeConnection({ quiet: true });
      }
    });
    window.addEventListener("beforeunload", (event) => {
      if (app.upload && (app.upload.status === "preparing" || app.upload.status === "uploading")) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      app.install.event = event;
      updateInstallRow();
      maybeShowInstallBanner();
    });
    window.addEventListener("appinstalled", () => {
      app.install.event = null;
      hideInstallBanner();
      updateInstallRow();
      showToast("已添加到主屏幕", "success", 2800);
    });
  }

  /* ------------------------------------------------------------------------
     19. 启动
     ------------------------------------------------------------------------ */
  function init() {
    cacheDom();
    ui.sheets.forEach((sheet) => {
      if (!sheet) return;
      sheet.hidden = true;
      sheet.setAttribute("aria-hidden", "true");
      try {
        sheet.inert = true;
      } catch (_) {
        /* ignore */
      }
    });
    if (ui.sheetBackdrop) {
      ui.sheetBackdrop.hidden = true;
      ui.sheetBackdrop.setAttribute("aria-hidden", "true");
    }
    applyTheme(app.theme, { persist: false });
    app.phoneName = normalizePhoneName(app.phoneName);
    ui.pairName.value = app.phoneName;
    updateTextCount();
    updateConnection();
    bindEvents();
    setTab("send", { scroll: false });
    setSendMode("files");
    updateInstallRow();
    window.setTimeout(registerServiceWorker, 800);
    routeBoot();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
