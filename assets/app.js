/* pressure-J 博客交互：零依赖，纯原生 JS */
(function () {
  'use strict';

  /* ---------- 主题切换 ---------- */
  var root = document.documentElement;
  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
    });
  }

  /* ---------- 移动端菜单 ---------- */
  var menuBtn = document.getElementById('menu-btn');
  var nav = document.getElementById('site-nav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  /* ---------- 阅读进度条 ---------- */
  var bar = document.getElementById('progress');
  var toTop = document.getElementById('to-top');
  if (bar || toTop) {
    var ticking = false;
    var onScroll = function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        var h = document.documentElement;
        var max = h.scrollHeight - h.clientHeight;
        var y = window.scrollY || h.scrollTop;
        if (bar) bar.style.width = (max > 0 ? (y / max) * 100 : 0) + '%';
        if (toTop) toTop.classList.toggle('show', y > 500);
        ticking = false;
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }
  if (toTop) {
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ---------- 代码块复制 ---------- */
  document.querySelectorAll('.code-block').forEach(function (block) {
    var btn = block.querySelector('.copy-btn');
    var code = block.querySelector('code');
    if (!btn || !code) return;
    btn.addEventListener('click', function () {
      var text = code.innerText;
      var done = function () {
        btn.textContent = '已复制';
        btn.classList.add('done');
        setTimeout(function () {
          btn.textContent = '复制';
          btn.classList.remove('done');
        }, 1600);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done).catch(fallback);
      } else {
        fallback();
      }
      function fallback() {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
  });

  /* ---------- 文章页：目录高亮 ---------- */
  var toc = document.getElementById('toc');
  if (toc) {
    var links = Array.prototype.slice.call(toc.querySelectorAll('a'));
    var heads = links.map(function (a) {
      var id = decodeURIComponent(a.getAttribute('href').slice(1));
      return document.getElementById(id);
    }).filter(Boolean);

    if (heads.length) {
      var updateToc = function () {
        var idx = 0;
        var top = window.scrollY + 110;
        for (var i = 0; i < heads.length; i++) {
          if (heads[i].offsetTop <= top) idx = i;
        }
        links.forEach(function (a, i) {
          a.classList.toggle('active', i === idx);
        });
      };
      window.addEventListener('scroll', updateToc, { passive: true });
      updateToc();
    }
  }

  /* ---------- 文章列表：搜索 + 分类筛选 ---------- */
  var input = document.getElementById('search-input');
  var list = document.getElementById('post-list');
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));
  var empty = document.getElementById('empty-hint');
  var hint = document.getElementById('result-hint');

  if (input && list) {
    var cards = Array.prototype.slice.call(list.querySelectorAll('.post-card'));
    var activeCat = 'all';
    var base = cards.map(function (c) {
      return { el: c, hay: (c.getAttribute('data-hay') || '').toLowerCase(), cat: c.getAttribute('data-cat') };
    });

    var apply = function () {
      var q = input.value.trim().toLowerCase();
      var terms = q ? q.split(/\s+/) : [];
      var shown = 0;
      base.forEach(function (item) {
        var catOk = activeCat === 'all' || item.cat === activeCat;
        var qOk = terms.every(function (t) { return item.hay.indexOf(t) !== -1; });
        var on = catOk && qOk;
        item.el.hidden = !on;
        if (on) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
      if (hint) {
        if (q || activeCat !== 'all') {
          hint.hidden = false;
          hint.textContent = '匹配到 ' + shown + ' 篇' + (q ? '（关键词：' + input.value.trim() + '）' : '');
        } else {
          hint.hidden = true;
        }
      }
    };

    input.addEventListener('input', apply);
    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        tabs.forEach(function (x) { x.classList.remove('on'); });
        t.classList.add('on');
        activeCat = t.getAttribute('data-filter') || 'all';
        apply();
      });
    });

    /* 按 / 聚焦搜索框 */
    document.addEventListener('keydown', function (e) {
      if (e.key === '/' && document.activeElement !== input &&
          !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
        e.preventDefault();
        input.focus();
        input.select();
      }
      if (e.key === 'Escape' && document.activeElement === input) {
        input.value = '';
        apply();
        input.blur();
      }
    });

    /* 从页头搜索图标跳转过来时自动聚焦 */
    if (location.hash === '#search') {
      setTimeout(function () { input.focus(); }, 120);
    }
    apply();
  }
})();
