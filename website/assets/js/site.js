/* ==========================================================================
   Aster 官网 · 交互与动效
   零依赖，全部原生 API。所有动效都尊重 prefers-reduced-motion。
   ========================================================================== */

(function () {
  "use strict";

  var html = document.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var i18n = window.AsterI18n || { t: function (k) { return k; } };
  var cfg = window.ASTER_CONFIG || {};

  var STORE_THEME = "aster.theme";
  var THEME_MODES = ["dark", "light", "auto"];

  /* ------------------------------------------------------------ 主题 */
  function systemTheme() {
    return window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }

  function applyTheme(mode) {
    if (THEME_MODES.indexOf(mode) === -1) mode = "dark";
    var resolved = mode === "auto" ? systemTheme() : mode;
    html.setAttribute("data-theme-mode", mode);
    html.setAttribute("data-theme", resolved);
    if (!themeFromUrl) {
      try {
        localStorage.setItem(STORE_THEME, mode);
      } catch (err) {
        /* ignore */
      }
    }
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", resolved === "light" ? "#F4F7FB" : "#080D17");
    document.querySelectorAll("[data-theme-btn]").forEach(function (btn) {
      var label = i18n.t("nav.theme") + " · " + i18n.t("theme." + mode);
      btn.setAttribute("aria-label", label);
      btn.setAttribute("title", label);
    });
  }

  var currentMode = html.getAttribute("data-theme-mode") || "dark";
  var themeFromUrl = !!window.__ASTER_THEME_PARAM;
  applyTheme(currentMode);

  document.querySelectorAll("[data-theme-btn]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      themeFromUrl = false;
      currentMode = THEME_MODES[(THEME_MODES.indexOf(currentMode) + 1) % 3];
      applyTheme(currentMode);
    });
  });

  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", function () {
    if (currentMode === "auto") applyTheme("auto");
  });

  document.addEventListener("aster:lang", function () {
    applyTheme(currentMode);
  });

  /* ------------------------------------------------------------ 顶栏 */
  var header = document.querySelector(".site-header");
  var progress = document.querySelector(".scroll-progress");

  function onScroll() {
    var y = window.scrollY || window.pageYOffset;
    if (header) header.classList.toggle("is-scrolled", y > 10);
    if (progress) {
      var max = document.documentElement.scrollHeight - window.innerHeight;
      var pct = max > 0 ? Math.min(100, (y / max) * 100) : 0;
      progress.style.setProperty("--p", pct.toFixed(2) + "%");
    }
  }

  var scrollTick = false;
  window.addEventListener("scroll", function () {
    if (scrollTick) return;
    scrollTick = true;
    requestAnimationFrame(function () {
      onScroll();
      scrollTick = false;
    });
  }, { passive: true });
  onScroll();

  /* -------------------------------------------------------- 移动端菜单 */
  var menuBtn = document.querySelector("[data-menu-btn]");
  var mobileMenu = document.querySelector("[data-mobile-menu]");

  function setMenu(open) {
    if (!menuBtn || !mobileMenu) return;
    menuBtn.classList.toggle("is-open", open);
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    mobileMenu.classList.toggle("is-open", open);
    mobileMenu.setAttribute("aria-hidden", open ? "false" : "true");
    document.body.classList.toggle("menu-open", open);
  }

  if (menuBtn) {
    menuBtn.addEventListener("click", function () {
      setMenu(!menuBtn.classList.contains("is-open"));
    });
  }

  if (mobileMenu) {
    mobileMenu.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () { setMenu(false); });
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setMenu(false);
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth > 980) setMenu(false);
  });

  /* ---------------------------------------------------------- 滚动出现 */
  var revealEls = Array.prototype.slice.call(document.querySelectorAll(".reveal"));

  function activate(el) {
    el.classList.add("is-in");

    var counters = el.querySelectorAll("[data-count]");
    counters.forEach(startCounter);

    var bars = el.querySelectorAll("[data-bar]");
    bars.forEach(function (bar) {
      bar.style.width = bar.getAttribute("data-bar") + "%";
    });
  }

  if ("IntersectionObserver" in window && !reduceMotion.matches) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        activate(entry.target);
        io.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });

    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(activate);
  }

  // 非 .reveal 容器里的计数 / 进度条也处理一次
  window.setTimeout(function () {
    document.querySelectorAll("[data-count]").forEach(function (el) {
      if (el.dataset.done) return;
      if (isInView(el)) startCounter(el);
    });
    document.querySelectorAll("[data-bar]").forEach(function (el) {
      if (isInView(el)) el.style.width = el.getAttribute("data-bar") + "%";
    });
  }, 700);

  function isInView(el) {
    var r = el.getBoundingClientRect();
    return r.top < window.innerHeight * 0.9 && r.bottom > 0;
  }

  /* ------------------------------------------------------------ 计数器 */
  var counterObserver = null;

  function startCounter(el) {
    if (el.dataset.done === "1") return;
    el.dataset.done = "1";
    var target = parseFloat(el.getAttribute("data-count"));
    var decimals = parseInt(el.getAttribute("data-decimals") || "1", 10);
    if (isNaN(target)) return;

    if (reduceMotion.matches) {
      el.textContent = target.toFixed(decimals);
      return;
    }

    var start = performance.now();
    var duration = 1500;

    function frame(now) {
      var p = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - p, 4);
      el.textContent = (target * eased).toFixed(decimals);
      if (p < 1) requestAnimationFrame(frame);
      else el.textContent = target.toFixed(decimals);
    }
    el.textContent = "0";
    requestAnimationFrame(frame);
  }

  if ("IntersectionObserver" in window) {
    counterObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        startCounter(entry.target);
        counterObserver.unobserve(entry.target);
      });
    }, { threshold: 0.4 });
    document.querySelectorAll("[data-count]").forEach(function (el) {
      counterObserver.observe(el);
    });
  }

  /* -------------------------------------------------------- 卡片光斑 */
  document.querySelectorAll("[data-spot]").forEach(function (card) {
    card.addEventListener("pointermove", function (e) {
      var r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width) * 100 + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height) * 100 + "%");
    });
  });

  /* -------------------------------------------------------- 磁吸按钮 */
  if (!reduceMotion.matches && window.matchMedia("(pointer: fine)").matches) {
    document.querySelectorAll("[data-magnet]").forEach(function (btn) {
      btn.addEventListener("pointermove", function (e) {
        var r = btn.getBoundingClientRect();
        var x = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
        var y = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
        btn.style.transform =
          "translate(" + (x * 5).toFixed(2) + "px," + (y * 4).toFixed(2) + "px)";
      });
      btn.addEventListener("pointerleave", function () {
        btn.style.transform = "";
      });
    });
  }

  /* -------------------------------------------------------- 手机倾斜 */
  var phone = document.querySelector("[data-tilt]");
  if (phone && !reduceMotion.matches && window.matchMedia("(pointer: fine)").matches) {
    phone.addEventListener("pointermove", function (e) {
      var r = phone.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5;
      var y = (e.clientY - r.top) / r.height - 0.5;
      phone.style.transform =
        "perspective(1000px) rotateY(" + (x * 8).toFixed(2) + "deg) rotateX(" +
        (-y * 8).toFixed(2) + "deg)";
    });
    phone.addEventListener("pointerleave", function () {
      phone.style.transform = "";
    });
  }

  /* ------------------------------------------------------- 视差（Hero） */
  var stage = document.querySelector("[data-parallax-stage]");
  if (stage && !reduceMotion.matches) {
    var ticking = false;
    window.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        var y = Math.min(window.scrollY, 800);
        stage.style.transform = "translate3d(0," + (y * 0.045).toFixed(2) + "px,0)";
        ticking = false;
      });
    }, { passive: true });
  }

  /* ---------------------------------------------------------- 跑马灯 */
  var marqueeTrack = document.querySelector(".marquee__track");
  if (marqueeTrack) {
    var group = marqueeTrack.querySelector(".marquee__group");
    if (group) {
      var clone = group.cloneNode(true);
      clone.setAttribute("aria-hidden", "true");
      marqueeTrack.appendChild(clone);
    }
  }

  /* --------------------------------------------------------- 界面切换 */
  function wireSwitcher(rootSelector, itemSelector, imgSelector, captionSelector) {
    var root = document.querySelector(rootSelector);
    if (!root) return;
    var img = document.querySelector(imgSelector);
    var caption = captionSelector ? document.querySelector(captionSelector) : null;
    var items = Array.prototype.slice.call(root.querySelectorAll(itemSelector));

    items.forEach(function (item) {
      item.addEventListener("click", function () {
        var src = item.getAttribute("data-src");
        if (!src || !img || img.getAttribute("src") === src) return;

        items.forEach(function (i) {
          i.classList.toggle("is-active", i === item);
          i.setAttribute("aria-pressed", i === item ? "true" : "false");
        });

        var captionKey = item.getAttribute("data-caption");
        if (caption && captionKey && i18n.t) {
          caption.textContent = i18n.t(captionKey);
          caption.setAttribute("data-i18n", captionKey);
        }

        img.parentElement.classList.add("is-switching");
        var preload = new Image();
        preload.onload = preload.onerror = function () {
          img.src = src;
          window.setTimeout(function () {
            img.parentElement.classList.remove("is-switching");
          }, 60);
        };
        preload.src = src;
      });
    });
  }

  wireSwitcher("[data-gallery-tabs]", ".gallery-tabs button", "[data-gallery-img]", "[data-gallery-caption]");
  wireSwitcher("[data-thumbs]", ".thumb", "[data-gallery-img]", "[data-gallery-caption]");
  wireSwitcher("[data-phone-tabs]", ".phone-tabs button", "[data-phone-img]", null);

  /* ----------------------------------------------------------- 复制 */
  function legacyCopy(text) {
    return new Promise(function (resolve, reject) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.top = "-1000px";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(ta);
        ok ? resolve() : reject(new Error("copy failed"));
      } catch (err) {
        reject(err);
      }
    });
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () {
        return legacyCopy(text);
      });
    }
    return legacyCopy(text);
  }

  function flashCopied(btn, ok) {
    if (!btn) return;
    var original = btn.getAttribute("data-label") || btn.textContent.trim();
    btn.setAttribute("data-label", original);
    btn.textContent = ok ? i18n.t("dl.copied") : original;
    btn.classList.toggle("is-copied", ok);
    window.setTimeout(function () {
      btn.textContent = original;
      btn.classList.remove("is-copied");
    }, 1600);
  }

  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var sel = btn.getAttribute("data-copy");
      var value = btn.getAttribute("data-copy-value") || "";
      if (sel) {
        var target = document.querySelector(sel);
        value = target ? (target.getAttribute("data-raw") || target.textContent) : "";
      }
      value = value.trim();
      if (!value) return;
      copyText(value).then(function () {
        flashCopied(btn, true);
      }).catch(function () {
        flashCopied(btn, false);
      });
    });
  });

  /* --------------------------------------------------- 下载页渲染 */
  var sumsPromise = null;

  function resolveUrl(file) {
    if (file.url) return file.url;
    var base = cfg.base || "";
    if (!base) return "";
    return base.replace(/\/?$/, "/") + file.name;
  }

  function loadSums() {
    if (sumsPromise) return sumsPromise;

    var files = cfg.files || {};
    var hasAnyUrl = !!cfg.base || Object.keys(files).some(function (key) {
      return !!(files[key] && files[key].url);
    });
    // 没有启用任何下载时不必请求，避免控制台出现无意义的 404
    if (!cfg.sumsUrl || !hasAnyUrl) return Promise.resolve({});

    sumsPromise = fetch(cfg.sumsUrl, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      })
      .then(function (text) {
        var map = {};
        text.split(/\r?\n/).forEach(function (line) {
          var m = line.trim().match(/^([a-fA-F0-9]{64})\s+\*?(.+)$/);
          if (m) map[m[2].trim()] = m[1].toLowerCase();
        });
        return map;
      })
      .catch(function () { return {}; });
    return sumsPromise;
  }

  var hashCache = null; // 仅供调试时查看

  function renderDownloads() {
    if (!document.querySelector("[data-file]")) return;

    loadSums().then(function (sums) {
      hashCache = sums;
      var anyPending = false;

      document.querySelectorAll("[data-file]").forEach(function (card) {
        var key = card.getAttribute("data-file");
        var file = cfg.files && cfg.files[key];
        if (!file) return;

        var url = resolveUrl(file);
        var isPending = !url;
        if (isPending) anyPending = true;

        var btn = card.querySelector("[data-download]");
        var label = card.querySelector("[data-dl-label]");
        var note = card.querySelector("[data-pending-note]");

        if (btn) {
          btn.classList.toggle("is-pending", isPending);
          if (isPending) {
            btn.setAttribute("aria-disabled", "true");
            btn.removeAttribute("href");
            btn.removeAttribute("download");
          } else {
            btn.removeAttribute("aria-disabled");
            btn.setAttribute("href", url);
            btn.setAttribute("download", file.name);
          }
        }
        if (label) label.textContent = i18n.t(isPending ? "dl.pending" : "dl.download");
        if (note) note.hidden = !isPending;

        var nameEl = card.querySelector("[data-file-name]");
        if (nameEl) nameEl.textContent = file.name;
        var sizeEl = card.querySelector("[data-file-size]");
        if (sizeEl) sizeEl.textContent = file.size || "—";

        var hashEl = card.querySelector("[data-hash]");
        var copyBtn = card.querySelector("[data-copy-hash]");
        var hash = (file.sha256 || (sums && sums[file.name]) || "").toLowerCase();
        if (hashEl) {
          if (hash) {
            hashEl.textContent = hash.slice(0, 16) + "…" + hash.slice(-8);
            hashEl.setAttribute("data-raw", hash);
            hashEl.removeAttribute("data-i18n");
            if (copyBtn) {
              copyBtn.hidden = false;
              copyBtn.setAttribute("data-copy-value", hash);
            }
          } else {
            hashEl.textContent = i18n.t("dl.hashPending");
            hashEl.removeAttribute("data-raw");
            if (copyBtn) copyBtn.hidden = true;
          }
        }
      });

      var notice = document.querySelector("[data-pending-notice]");
      if (notice) notice.hidden = !anyPending;
    });
  }

  document.addEventListener("aster:lang", renderDownloads);
  renderDownloads();

  /* ------------------------------------------------------- 当前栏目 */
  var navLinks = Array.prototype.slice.call(document.querySelectorAll(".nav-links a[href^='#']"));
  var sections = navLinks
    .map(function (a) { return document.querySelector(a.getAttribute("href")); })
    .filter(Boolean);

  if ("IntersectionObserver" in window && sections.length) {
    var navObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var id = "#" + entry.target.id;
        navLinks.forEach(function (a) {
          a.classList.toggle("is-active", a.getAttribute("href") === id);
        });
      });
    }, { rootMargin: "-42% 0px -52% 0px", threshold: 0 });

    sections.forEach(function (s) { navObserver.observe(s); });
  }

  /* ------------------------------------------------------- 键盘细节 */
  document.querySelectorAll("[data-download], .btn--primary").forEach(function (el) {
    el.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        if (el.classList.contains("is-pending")) e.preventDefault();
      }
    });
  });

  /* 版本号占位替换 */
  document.querySelectorAll("[data-version]").forEach(function (el) {
    el.textContent = cfg.versionLabel || cfg.version || "2.0.0";
  });
})();
