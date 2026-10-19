# -*- coding: utf-8 -*-
"""
build.py —— 把 D:\\mdstudyfile 的笔记编译成静态博客

用法:
    py build.py            # 全量生成
    py build.py --serve    # 生成后起本地预览 (http://127.0.0.1:8000)
    py build.py --check    # 只体检：断图 / 内容过少 / 空壳文件，不写盘

设计原则:
    1. 单一数据源 —— 笔记改完重跑一次即可，不在仓库里手改 HTML
    2. 白名单收录 —— 只发布 SOURCES 列出的目录，私密内容进不了发布链路
    3. 发布前脱敏 —— 真名 / 本机绝对路径 → 占位符 (见 scrub)
"""

import os
import re
import sys
import json
import html
import shutil
import datetime
import subprocess

import markdown
from markdown.extensions.toc import TocExtension
from pygments.formatters import HtmlFormatter
from pypinyin import lazy_pinyin

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = r"D:\mdstudyfile"          # 笔记源
OUT = ROOT                       # 输出 = 本仓库根目录
POSTS_DIR = os.path.join(OUT, "posts")
CAT_DIR = os.path.join(OUT, "category")
ASSETS = os.path.join(OUT, "assets")

# ---------------------------------------------------------------- 站点信息
SITE = {
    "name": "pressure-J",
    "tagline": "网络安全 · 应急响应 · 流量分析",
    "desc": "pressure-J 的技术笔记：应急响应、流量分析、Web 安全、密码学与 Linux。写能复现、能讲清楚的东西。",
    "url": "https://pressure-j.github.io",
    "github": "https://github.com/pressure-J",
    "email": "1489955298@qq.com",
    "build": datetime.date.today().isoformat(),
    # 是否在"关于"页显示真名。默认关：和 scrub() 的脱敏口径保持一致
    "show_realname": False,
    "realname": "徐利杰",
}

# ---------------------------------------------------------------- 收录白名单
# (笔记子目录, 展示名, 分类 slug, 一句话介绍)
SOURCES = [
    ("应急响应杂项", "应急响应", "ir", "日志判读、流量取证、入侵链还原与恶意程序处置"),
    ("web", "Web 安全", "web", "SQL 注入、文件包含/上传、反序列化、SSRF 与绕过手法"),
    ("密码学", "密码学", "crypto", "RSA 攻击家族、流密码、国密算法与格密码入门"),
    ("misc", "Misc", "misc", "流量分析、图片/视频隐写、内存取证与离线速查"),
    ("linux", "Linux", "linux", "基础命令、服务搭建、内核模块与虚拟机网络排查"),
    ("python", "Python", "python", "语法坑、编码、正则、subprocess 与 CTF 数据处理"),
    ("baseknown", "基础", "base", "文件格式、编码、Wireshark 与工具链这些常年要查的"),
]

# 永不发布 —— 这是硬闸门，不是"记得别写"的口头约定
EXCLUDE_DIRS = {
    "CTF备赛",     # 简历、求职作战计划、实习方案：个人规划不该公开
    "agentstudy",  # 学习总结草稿，含课程/项目内部信息
    "漏洞复现",    # 真实高校域名的未修复漏洞报告：公开即等于信息披露
    "kb",          # 离线 RAG 索引
}
EXCLUDE_FILES = {
    "README.md",                                            # 目录索引，与导航重复
    "Untitled.md", "wp001.md", "其他.md", "输入与输出.md",   # 空壳/占位
    "本机安全工具与解释器清单.md",                            # 本机路径清单
    "蓝队实习环境部署与产出规划.md",                          # 求职规划
    "简历作战计划-未来6个月.md",
    "简历-徐利杰-安全运营实习.md",
}

# 旧站已有 URL，保持不失效
SLUG_OVERRIDE = {
    r"应急响应杂项\03-流量分析\Shiro反序列化RCE流量分析WriteUp.md": "shiro-deserialization-traffic",
    r"应急响应杂项\03-流量分析\Webshell上传与加密隧道分析WriteUp.md": "webshell-encrypted-tunnel",
    r"应急响应杂项\02-日志分析\SSH暴力破解与日志分析WriteUp.md": "ssh-bruteforce-log-analysis",
    r"应急响应杂项\01-基础知识\Windows安全日志分析-RDP暴力破解.md": "windows-rdp-bruteforce-log",
    r"web\Web安全-SQL盲注与WAF绕过解题WriteUp.md": "sql-injection-waf-bypass",
    r"应急响应杂项\01-基础知识\Linux日志分析基础.md": "linux-log-analysis-basics",
}

# 首页精选（顺序即展示顺序），不足 3 篇时按日期自动补
PICKS = [
    r"应急响应杂项\03-流量分析\Shiro反序列化RCE流量分析WriteUp.md",
    r"misc\Misc-流量分析-按种类速查.md",
    r"应急响应杂项\02-日志分析\SSH暴力破解与日志分析WriteUp.md",
]

# ---------------------------------------------------------------- 脱敏
_LOCAL_USER = os.path.basename(os.path.expanduser("~"))


def scrub(text):
    """发布前脱敏：真名 → pressure-J，本机绝对路径 → 占位符。
    路径正则用 [\\\\/]+ 吃掉任意层数斜杠，避免转义层数不一致漏替换。"""
    rules = [
        (r"C:[\\/]+Users[\\/]+" + re.escape(_LOCAL_USER), "~/"),
        (r"C:[\\/]+Users[\\/]+[^\\/\s\"'<>|*]+", "~/"),
        (r"D:[\\/]+mdstudyfile", "~/notes"),
        (r"D:[\\/]+python", "~/tools"),
        (r"D:[\\/]+网络安全工具", "~/tools"),
        (r"D:[\\/]+GitHub-Pages", "~/blog"),
        (r"D:[\\/]+[^\\/\s\"'<>|*]+", "~/"),
        (r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'<>|*]+", "~/"),
    ]
    for pat, rep in rules:
        text = re.sub(pat, rep, text)
    if _LOCAL_USER:
        text = text.replace(_LOCAL_USER, SITE["name"])
    return text


# ---------------------------------------------------------------- 解析笔记
def split_frontmatter(raw):
    raw = raw.replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n?", raw, re.S)
    if not m:
        return {}, raw
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line and line[:1] not in " \t-":
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("'\"")
    return fm, raw[m.end():]


def first_h1(body):
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None


def make_summary(body, limit=116):
    """取第一段真正的正文当摘要。判据是"像人话"：CJK 字符足够多，
    这样代码/命令行/表格即便出现在最前面也不会被当成导语。"""
    def cjk(s):
        return len(re.findall(r"[\u4e00-\u9fff]", s))

    def tidy(s):
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
        s = re.sub(r"[*_`]", "", s)
        return re.sub(r"\s{2,}", " ", s).strip()

    para = []
    for line in body.split("\n"):
        s = line.strip()
        if not s or s.startswith(("#", ">", "|", "---", "![", "<")):
            if para:
                break
            continue
        if re.match(r"^([-*+]\s|\d+[.)]\s)", s):   # 列表项不是导语
            if para:
                break
            continue
        if cjk(s) < 6:          # 代码、命令、链接行：跳过
            if para:
                break
            continue
        para.append(s)

    text = tidy(" ".join(para))
    if cjk(text) < 12:          # 兜底：全文找第一句真正像人话的话
        text = ""
        for line in body.split("\n"):
            s = tidy(line)
            s = re.sub(r"^\s*(?:[-*+>]\s*|\d+[.)]\s*|#+\s*)+", "", s)
            if (cjk(s) >= 18
                    and not re.search(r"[=(){}\[\]]|///|\bdef \b|^\w+\(", s)
                    and not s.startswith(("注：", "注意"))):
                text = s
                break
    if cjk(text) < 8:           # 通篇代码的笔记：给一句如实的描述，而不是硬凑
        text = ""
    if len(text) > limit:
        text = text[:limit].rstrip("，,、。 ：:") + "…"
    return text


def slugify(title, used):
    py = " ".join(lazy_pinyin(title))
    s = re.sub(r"[^A-Za-z0-9]+", "-", py).strip("-").lower()[:68].strip("-") or "post"
    base, n = s, 2
    while s in used:
        s = f"{base}-{n}"
        n += 1
    used.add(s)
    return s


def discover():
    posts, used, warnings = [], set(SLUG_OVERRIDE.values()), []
    for dirname, cat_name, cat_slug, cat_desc in SOURCES:
        base = os.path.join(SRC, dirname)
        if not os.path.isdir(base):
            warnings.append(f"目录不存在，跳过：{dirname}")
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
            for fn in sorted(filenames):
                if not fn.lower().endswith(".md") or fn in EXCLUDE_FILES:
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, SRC)
                raw = open(full, encoding="utf-8", errors="ignore").read()
                fm, body = split_frontmatter(raw)
                body = scrub(body)        # 先脱敏，摘要/搜索索引都基于干净文本

                title = fm.get("title") or first_h1(body) or os.path.splitext(fn)[0]
                title = re.sub(r"^#+\s*", "", title)
                title = re.sub(r"\s{2,}", " ", title).strip()

                date = (fm.get("date") or fm.get("created") or "")[:10]
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
                    date = datetime.date.fromtimestamp(os.path.getmtime(full)).isoformat()

                words = len(re.sub(r"\s", "", body))
                if words < 120:          # 空壳文件不发布
                    warnings.append(f"内容过少，跳过：{rel}（{words} 字）")
                    continue

                tags = [t.strip() for t in
                        re.split(r"[,，]", fm.get("tags", "").strip(" []")) if t.strip()]
                tags = [t for t in tags if not re.match(r"^\d\d-", t)][:5]

                imgs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", body)
                broken = [i for i in imgs if not re.match(r"^https?://", i)]

                slug = SLUG_OVERRIDE.get(rel) or slugify(title, used)
                posts.append({
                    "src": full, "rel": rel, "title": title, "date": date,
                    "tags": tags, "words": words, "slug": slug,
                    "cat": cat_name, "cat_slug": cat_slug, "cat_desc": cat_desc,
                    "summary": make_summary(body), "broken": broken, "raw": body,
                })
    posts.sort(key=lambda p: (p["date"], p["words"]), reverse=True)
    return posts, warnings


# ---------------------------------------------------------------- Markdown
def build_markdown(posts):
    """两趟：先建 slug 映射，再渲染，让站内 .md 互链能改写成正确的 HTML 链接"""
    md_map = {}
    for p in posts:
        md_map[os.path.normcase(p["rel"])] = p
        md_map[os.path.normcase(os.path.basename(p["rel"]))] = p

    def rewrite(text, current):
        def repl(m):
            target = m.group(1).strip()
            clean = target.split("#")[0]
            hit = (md_map.get(os.path.normcase(clean))
                   or md_map.get(os.path.normcase(
                       os.path.join(os.path.dirname(current["rel"]), clean))))
            if hit:
                return f"](../posts/{hit['slug']}.html)"
            return "]("            # 指向未发布笔记：退化为纯文本，不留死链

        return re.sub(r"\]\(([^)\s]+\.md(?:#[^)]*)?)\)", repl, text)

    for p in posts:
        body = p["raw"]

        # 按 fenced code 切段：只在代码块外面做标题处理，否则 shell/Python 的
        # "# 注释" 会被当成 markdown 标题改掉。
        chunks = re.split(r"(?m)^(```.*?$)", body)
        outside = True
        removed_h1 = False
        for i, ch in enumerate(chunks):
            if ch.startswith("```"):
                outside = not outside
                continue
            if not outside:
                continue
            if not removed_h1:
                # 首个 H1 与页面标题重复，去掉（允许前面有空行）
                ch, n = re.subn(r"(?m)^\s*#\s+\S.*?(?:\n|$)", "", ch, count=1)
                removed_h1 = bool(n)
            # 剩余的一级标题降为二级，保证每页只有一个 h1
            ch = re.sub(r"(?m)^#\s+(?=\S)", "## ", ch)
            chunks[i] = ch
        body = "".join(chunks)
        body = scrub(body)
        body = rewrite(body, p)
        body = re.sub(r"!\[[^\]]*\]\((?!https?://)[^)]+\)\n?", "", body)  # 剔除本地图片

        html_out, toc_tokens, ncodes = render(body)
        p["html"] = html_out
        p["toc"] = extract_toc(toc_tokens)
        p["minutes"] = max(1, round(p["words"] / 380))
        p["codes"] = ncodes


def extract_toc(tokens, out=None):
    out = [] if out is None else out
    for t in tokens:
        if t["level"] <= 3:
            out.append({"id": t["id"], "name": t["name"], "level": t["level"]})
        extract_toc(t.get("children", []), out)
    return out


def render(body):
    """渲染 markdown。语言标签从源码里预先摘出来，按出现顺序回填到代码块上
    —— Pygments 的 HtmlFormatter 不会把语言写进输出。"""
    langs = []
    for m in re.finditer(r"(?m)^```(\w*)", body):
        langs.append(m.group(1) or "text")

    md = markdown.Markdown(extensions=[
        "fenced_code", "codehilite", "tables", "attr_list", "sane_lists", "nl2br",
        TocExtension(toc_depth="2-3", anchorlink=False),
    ], extension_configs={
        "codehilite": {"css_class": "highlight", "guess_lang": False, "linenums": False},
    })
    raw = md.convert(body)
    html_out, idx = [], 0
    parts = raw.split('<div class="highlight"><pre>')
    html_out.append(parts[0])
    for seg in parts[1:]:
        lang = langs[idx] if idx < len(langs) else "text"
        idx += 1
        html_out.append(f'<div class="code-block" data-lang="{lang}">'
                        f'<button class="copy-btn" type="button">复制</button>'
                        f'<div class="highlight"><pre>{seg}')
    h = "".join(html_out)
    h = h.replace("</pre></div>", "</pre></div></div>")
    h = h.replace("<table>", '<div class="table-wrap"><table>')
    h = h.replace("</table>", "</table></div>")
    return h, md.toc_tokens, idx


# ---------------------------------------------------------------- 模板
def esc(s):
    return html.escape(str(s), quote=True)


def page(*, title, desc, body, active="", root="", canonical="", body_class=""):
    full = f"{title} · {SITE['name']}" if title != SITE["name"] else f"{SITE['name']} — {SITE['tagline']}"
    nav = [("index.html", "首页", "home"), ("posts.html", "文章", "posts"),
           ("category/index.html", "分类", "cat"), ("about.html", "关于", "about")]
    navhtml = "".join(
        f'<a href="{root}{href}"{" class=\"on\"" if key == active else ""}>{label}</a>'
        for href, label, key in nav)
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(full)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="{esc(SITE['name'])}">
<meta name="color-scheme" content="dark light">
<link rel="canonical" href="{esc(SITE['url'] + canonical)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(full)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:site_name" content="{esc(SITE['name'])}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/rss+xml" title="{esc(SITE['name'])}" href="{root}rss.xml">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🛡</text></svg>">
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="stylesheet" href="{root}assets/highlight.css">
<script>
(function() {{
  try {{
    var t = localStorage.getItem('theme');
    if (!t) t = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
  }} catch (e) {{}}
}})();
</script>
</head>
<body class="{body_class}">
<div class="progress-bar" id="progress"></div>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{root}index.html">
      <span class="brand-mark">$</span><span class="brand-name">{esc(SITE['name'])}</span><span class="brand-caret">_</span>
    </a>
    <nav class="site-nav" id="site-nav">{navhtml}</nav>
    <div class="header-tools">
      <a class="icon-btn" href="{root}posts.html#search" aria-label="搜索">
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>
      </a>
      <button class="icon-btn" id="theme-toggle" type="button" aria-label="切换主题">
        <svg class="i-sun" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.4"/><path d="M12 2.2v2.2M12 19.6v2.2M2.2 12h2.2M19.6 12h2.2M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M19.1 4.9l-1.6 1.6M6.5 17.5l-1.6 1.6"/></svg>
        <svg class="i-moon" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M21 12.9A8.6 8.6 0 1 1 11.1 3a6.6 6.6 0 0 0 9.9 9.9z"/></svg>
      </button>
      <button class="icon-btn menu-btn" id="menu-btn" type="button" aria-label="菜单" aria-expanded="false">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
      </button>
    </div>
  </div>
</header>
{body}
<footer class="site-footer">
  <div class="wrap footer-inner">
    <div class="footer-col footer-about">
      <div class="footer-brand">{esc(SITE['name'])}<span class="brand-caret">_</span></div>
      <p>{esc(SITE['tagline'])}<br>写能复现、能讲清楚的东西。</p>
    </div>
    <div class="footer-col">
      <div class="footer-title">导航</div>
      <a href="{root}index.html">首页</a>
      <a href="{root}posts.html">全部文章</a>
      <a href="{root}category/index.html">分类</a>
      <a href="{root}about.html">关于</a>
    </div>
    <div class="footer-col">
      <div class="footer-title">在别处</div>
      <a href="{SITE['github']}" target="_blank" rel="noopener">GitHub</a>
      <a href="mailto:{SITE['email']}">Email</a>
      <a href="{root}rss.xml">RSS</a>
    </div>
  </div>
  <div class="wrap footer-bottom">
    <span>© {datetime.date.today().year} {esc(SITE['name'])}</span>
    <span class="footer-build">Build {SITE['build']} · Python + Markdown</span>
  </div>
</footer>
<button class="to-top" id="to-top" type="button" aria-label="回到顶部">
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
</button>
<script src="{root}assets/app.js" defer></script>
</body>
</html>"""


def chips(p):
    return "".join(f'<span class="chip">{esc(t)}</span>' for t in p["tags"][:3])


def card(p, root=""):
    desc = (f'  <p class="card-desc">{esc(p["summary"])}</p>\n'
            if p["summary"] else "")
    return f"""<article class="post-card" data-cat="{p['cat_slug']}"
     data-hay="{esc((p['title'] + ' ' + p['summary'] + ' ' + ' '.join(p['tags'])).lower())}">
  <div class="card-top">
    <a class="cat-badge cat-{p['cat_slug']}" href="{root}category/{p['cat_slug']}.html">{esc(p['cat'])}</a>
    <time datetime="{p['date']}">{p['date']}</time>
  </div>
  <h3><a href="{root}posts/{p['slug']}.html">{esc(p['title'])}</a></h3>
{desc}  <div class="card-foot">
    <div class="chips">{chips(p)}</div>
    <span class="reading">{p['minutes']} min · {p['words']} 字</span>
  </div>
</article>"""


def feature_card(p):
    desc = (f'  <p>{esc(p["summary"])}</p>\n' if p["summary"] else "")
    return f"""<a class="feature" href="posts/{p['slug']}.html">
  <div class="feature-glow"></div>
  <div class="card-top">
    <span class="cat-badge cat-{p['cat_slug']}">{esc(p['cat'])}</span>
    <time>{p['date']}</time>
  </div>
  <h3>{esc(p['title'])}</h3>
{desc}  <span class="feature-more">阅读全文 <span aria-hidden="true">→</span></span>
</a>"""


def cat_card(name, slug, desc, count, root=""):
    return f"""<a class="cat-card" href="{root}{slug}.html">
  <div class="cat-card-top">
    <span class="cat-badge cat-{slug}">{esc(name)}</span>
    <span class="cat-count">{count} 篇</span>
  </div>
  <p>{esc(desc)}</p>
  <span class="cat-more">浏览 <span aria-hidden="true">→</span></span>
</a>"""


# ---------------------------------------------------------------- 生成
def build():
    t0 = datetime.datetime.now()
    posts, warnings = discover()
    build_markdown(posts)

    for d in (POSTS_DIR, CAT_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    os.makedirs(ASSETS, exist_ok=True)

    by_cat = {}
    for p in posts:
        by_cat.setdefault(p["cat_slug"], []).append(p)
    cats = [(name, slug, desc) for _, name, slug, desc in SOURCES if slug in by_cat]

    total_words = sum(p["words"] for p in posts)
    total_min = sum(p["minutes"] for p in posts)

    # ---------- 文章页
    for i, p in enumerate(posts):
        prev_p = posts[i + 1] if i + 1 < len(posts) else None
        next_p = posts[i - 1] if i > 0 else None

        toc_html = ""
        if len(p["toc"]) >= 3:
            items = "".join(
                f'<a href="#{t["id"]}" class="toc-lv{t["level"]}">{esc(t["name"])}</a>'
                for t in p["toc"])
            toc_html = f"""<aside class="toc" id="toc">
  <div class="toc-title">目录</div>
  <nav>{items}</nav>
</aside>"""

        pn = ""
        if prev_p or next_p:
            left = (f'<a class="pn-item prev" href="{prev_p["slug"]}.html">'
                    f'<span>← 上一篇</span><strong>{esc(prev_p["title"])}</strong></a>'
                    if prev_p else '<span class="pn-empty"></span>')
            right = (f'<a class="pn-item next" href="{next_p["slug"]}.html">'
                     f'<span>下一篇 →</span><strong>{esc(next_p["title"])}</strong></a>'
                     if next_p else '<span class="pn-empty"></span>')
            pn = f'<div class="post-nav">{left}{right}</div>'

        tag_html = "".join(f'<span class="chip">{esc(t)}</span>' for t in p["tags"])

        body = f"""<main class="wrap post-layout">
  <div class="post-main">
    <nav class="breadcrumb">
      <a href="../index.html">首页</a><span>/</span>
      <a href="../category/{p['cat_slug']}.html">{esc(p['cat'])}</a>
    </nav>
    <article class="post">
      <header class="post-header">
        <h1>{esc(p['title'])}</h1>
        <div class="post-meta">
          <span class="cat-badge cat-{p['cat_slug']}">{esc(p['cat'])}</span>
          <time datetime="{p['date']}">{p['date']}</time>
          <span>{p['words']} 字</span>
          <span>约 {p['minutes']} 分钟</span>
        </div>
        {f'<div class="chips post-tags">{tag_html}</div>' if tag_html else ''}
      </header>
      <div class="content">{p['html']}</div>
      {pn}
      <div class="post-end">
        <a href="../posts.html">← 返回文章列表</a>
        <a href="{SITE['github']}" target="_blank" rel="noopener">在 GitHub 上找我</a>
      </div>
    </article>
  </div>
  {toc_html}
</main>"""
        open(os.path.join(POSTS_DIR, p["slug"] + ".html"), "w", encoding="utf-8").write(page(
            title=p["title"], desc=p["summary"] or f"{p['title']} — {SITE['name']} 的技术笔记",
            body=body, active="posts", root="../",
            canonical=f"/posts/{p['slug']}.html", body_class="has-toc"))

    # ---------- 首页
    picks = []
    for relpath in PICKS:
        hit = next((p for p in posts if p["rel"] == relpath), None)
        if hit and hit not in picks:
            picks.append(hit)
    for p in posts:
        if len(picks) >= 3:
            break
        if p not in picks:
            picks.append(p)
    picks = picks[:3]
    latest = [p for p in posts if p not in picks][:8]

    body = f"""<main>
  <section class="hero">
    <div class="wrap hero-inner">
      <div class="hero-badge"><span class="dot"></span>持续记录中 · 已发布 {len(posts)} 篇</div>
      <h1>把踩过的坑，<br>写成<em>能复现</em>的东西。</h1>
      <p class="hero-sub">
        网络空间安全在读。这里放应急响应的实战复盘、流量取证的思路、Web 漏洞的原理拆解，
        以及密码学和 Linux 那些常年要翻的笔记。<br>
        不写流水账——只写能讲清楚、别人照着能跑通的过程。
      </p>
      <div class="hero-actions">
        <a class="btn btn-primary" href="posts.html">浏览全部文章<span aria-hidden="true">→</span></a>
        <a class="btn btn-ghost" href="{SITE['github']}" target="_blank" rel="noopener">GitHub</a>
      </div>
      <dl class="hero-stats">
        <div><dt>{len(posts)}</dt><dd>篇文章</dd></div>
        <div><dt>{len(cats)}</dt><dd>个方向</dd></div>
        <div><dt>{total_words // 1000}k</dt><dd>字笔记</dd></div>
        <div><dt>{total_min // 60}h</dt><dd>累计阅读</dd></div>
      </dl>
    </div>
  </section>

  <section class="wrap section">
    <div class="section-head">
      <h2>精选阅读</h2>
      <a class="section-link" href="posts.html">全部文章 →</a>
    </div>
    <div class="features">{"".join(feature_card(p) for p in picks)}</div>
  </section>

  <section class="wrap section">
    <div class="section-head">
      <h2>最新更新</h2>
      <a class="section-link" href="rss.xml">RSS 订阅 →</a>
    </div>
    <div class="post-list">{"".join(card(p) for p in latest)}</div>
  </section>

  <section class="wrap section">
    <div class="section-head"><h2>按方向浏览</h2></div>
    <div class="cat-grid">
      {"".join(cat_card(n, s, d, len(by_cat[s]), "category/") for n, s, d in cats)}
    </div>
  </section>
</main>"""
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(page(
        title=SITE["name"], desc=SITE["desc"], body=body, active="home", canonical="/"))

    # ---------- 全部文章
    body = f"""<main class="wrap section">
  <header class="page-head">
    <h1>全部文章</h1>
    <p>共 {len(posts)} 篇 · 按日期倒序</p>
  </header>
  <div class="filter-bar" id="search">
    <div class="search-box">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>
      <input type="search" id="search-input" placeholder="搜索标题、摘要、标签…（按 / 聚焦）" autocomplete="off" aria-label="搜索文章">
      <kbd>/</kbd>
    </div>
    <div class="cat-tabs">
      <button class="tab on" data-filter="all">全部<span>{len(posts)}</span></button>
      {"".join(f'<button class="tab" data-filter="{s}">{esc(n)}<span>{len(by_cat[s])}</span></button>' for n, s, _ in cats)}
    </div>
  </div>
  <p class="result-hint" id="result-hint" hidden></p>
  <div class="post-list" id="post-list">{"".join(card(p) for p in posts)}</div>
  <p class="empty-hint" id="empty-hint" hidden>没有匹配的文章，换个关键词试试。</p>
</main>"""
    open(os.path.join(OUT, "posts.html"), "w", encoding="utf-8").write(page(
        title="全部文章", desc=f"{SITE['name']} 的全部技术笔记，共 {len(posts)} 篇。",
        body=body, active="posts", canonical="/posts.html"))

    # ---------- 分类总览
    body = f"""<main class="wrap section">
  <header class="page-head">
    <h1>分类</h1>
    <p>{len(cats)} 个方向 · {len(posts)} 篇文章</p>
  </header>
  <div class="cat-grid">
    {"".join(cat_card(n, s, d, len(by_cat[s])) for n, s, d in cats)}
  </div>
</main>"""
    open(os.path.join(CAT_DIR, "index.html"), "w", encoding="utf-8").write(page(
        title="分类", desc="按方向浏览全部技术笔记。", body=body, active="cat",
        root="../", canonical="/category/"))

    # ---------- 各分类页
    for name, slug, desc in cats:
        plist = by_cat[slug]
        body = f"""<main class="wrap section">
  <nav class="breadcrumb"><a href="../index.html">首页</a><span>/</span>分类</nav>
  <header class="page-head page-head-cat">
    <h1><span class="cat-badge cat-{slug}">{esc(name)}</span> {len(plist)} 篇</h1>
    <p>{esc(desc)}</p>
  </header>
  <div class="post-list">{"".join(card(p, root="../") for p in plist)}</div>
</main>"""
        open(os.path.join(CAT_DIR, slug + ".html"), "w", encoding="utf-8").write(page(
            title=name, desc=desc, body=body, active="cat", root="../",
            canonical=f"/category/{slug}.html"))

    # ---------- 关于
    body = f"""<main class="wrap section narrow">
  <header class="page-head">
    <h1>关于</h1>
  </header>
  <div class="content about">
    <p class="about-lead">{SITE['realname'] if SITE['show_realname'] else SITE['name']} · 网络空间安全本科生，方向是<strong>防御侧</strong>。</p>
    <p>
      我在江西财经大学读网络空间安全。日常主要泡在三件事上：应急响应的实战复盘、CTF 的
      Web / Misc 题目，以及把学到的原理写成能跑通的笔记。
    </p>
    <p>
      这个博客是我的知识库出口。写在这里的东西有两个标准：<strong>能复现</strong>（照着步骤能重跑一遍）
      和<strong>能讲清</strong>（每个动作为什么这么做，而不只是命令）。写不清楚的，说明我还没真的懂。
    </p>

    <h2>在做的事</h2>
    <ul class="timeline">
      <li>
        <div class="tl-dot"></div>
        <div>
          <strong>应急响应 / 流量取证</strong>
          <p>日志三源关联（认证 + 防火墙 + 审计）、Shiro 反序列化流量还原、Webshell 加密隧道识别。
          目标是把一次入侵链完整讲出来，而不是零散地报几个结论。</p>
        </div>
      </li>
      <li>
        <div class="tl-dot"></div>
        <div>
          <strong>eduSRC 漏洞挖掘</strong>
          <p>面向教育行业的 SRC 提交，关注越权、逻辑漏洞与常见组件问题。每个提交都配可复现步骤与截图证据。</p>
        </div>
      </li>
      <li>
        <div class="tl-dot"></div>
        <div>
          <strong>CTF Agent 工程</strong>
          <p>用 Python + FastAPI + LLM 做的自动化解题框架，负责 Agent 核心与 Crypto 工具链，
          把解题思路沉淀成可调用的工具。</p>
        </div>
      </li>
    </ul>

    <h2>技术栈</h2>
    <div class="stack">
      <div class="stack-row"><span class="stack-key">安全</span><div class="chips">
        <span class="chip">应急响应</span><span class="chip">Wireshark / tshark</span>
        <span class="chip">日志分析</span><span class="chip">Burp Suite</span><span class="chip">sqlmap</span>
      </div></div>
      <div class="stack-row"><span class="stack-key">密码</span><div class="chips">
        <span class="chip">RSA 攻击家族</span><span class="chip">国密 SM2/SM3/SM4</span>
        <span class="chip">PyCryptodome</span>
      </div></div>
      <div class="stack-row"><span class="stack-key">开发</span><div class="chips">
        <span class="chip">Python</span><span class="chip">FastAPI</span>
        <span class="chip">C / 汇编入门</span><span class="chip">Linux</span><span class="chip">Git</span>
      </div></div>
      <div class="stack-row"><span class="stack-key">环境</span><div class="chips">
        <span class="chip">Kali / VMware</span><span class="chip">WSL</span>
        <span class="chip">Windows 安全日志</span>
      </div></div>
    </div>

    <h2>联系方式</h2>
    <p>
      GitHub：<a href="{SITE['github']}" target="_blank" rel="noopener">github.com/pressure-J</a><br>
      Email：<a href="mailto:{SITE['email']}">{SITE['email']}</a><br>
      RSS：<a href="rss.xml">订阅更新</a>
    </p>
    <blockquote>
      这个站点由仓库里的 <code>build.py</code> 从 Markdown 笔记直接编译而来，没有前端框架、
      没有构建服务，正文源文件就是笔记原件。
    </blockquote>
  </div>
</main>"""
    open(os.path.join(OUT, "about.html"), "w", encoding="utf-8").write(page(
        title="关于", desc=f"关于 {SITE['name']}：网络空间安全在读，方向是防御侧。",
        body=body, active="about", canonical="/about.html"))

    # ---------- 404（GitHub Pages 会自动使用根目录 404.html）
    body = """<main class="wrap section err-page">
  <div class="err-code">404</div>
  <h1>这个页面不存在</h1>
  <p>可能链接过期了，或者那篇文章还没写完。</p>
  <div class="hero-actions">
    <a class="btn btn-primary" href="/index.html">回首页</a>
    <a class="btn btn-ghost" href="/posts.html">看全部文章</a>
  </div>
</main>"""
    open(os.path.join(OUT, "404.html"), "w", encoding="utf-8").write(page(
        title="404", desc="页面不存在。", body=body, canonical="/404.html"))

    # ---------- 搜索索引
    index = [{"t": p["title"], "u": f"posts/{p['slug']}.html", "c": p["cat"],
              "s": p["cat_slug"], "d": p["date"], "x": p["summary"],
              "g": " ".join(p["tags"])} for p in posts]
    open(os.path.join(OUT, "search.json"), "w", encoding="utf-8").write(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    # ---------- RSS
    def rfc822(d):
        return datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0800")

    items = "".join(f"""  <item>
    <title>{esc(p['title'])}</title>
    <link>{SITE['url']}/posts/{p['slug']}.html</link>
    <guid isPermaLink="true">{SITE['url']}/posts/{p['slug']}.html</guid>
    <pubDate>{rfc822(p['date'])}</pubDate>
    <category>{esc(p['cat'])}</category>
    <description>{esc(p['summary'] or p['title'])}</description>
  </item>
""" for p in posts[:20])
    open(os.path.join(OUT, "rss.xml"), "w", encoding="utf-8").write(f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{esc(SITE['name'])} — {esc(SITE['tagline'])}</title>
  <link>{SITE['url']}/</link>
  <description>{esc(SITE['desc'])}</description>
  <language>zh-CN</language>
  <lastBuildDate>{rfc822(SITE['build'])}</lastBuildDate>
  <atom:link href="{SITE['url']}/rss.xml" rel="self" type="application/rss+xml"/>
{items}</channel>
</rss>
""")

    # ---------- sitemap / robots / .nojekyll
    urls = [("", "1.0"), ("posts.html", "0.9"), ("category/index.html", "0.7"),
            ("about.html", "0.6")]
    urls += [(f"category/{s}.html", "0.6") for _, s, _ in cats]
    urls += [(f"posts/{p['slug']}.html", "0.8") for p in posts]
    sm = "".join(f'  <url><loc>{SITE["url"]}/{u}</loc>'
                 f'<lastmod>{SITE["build"]}</lastmod><priority>{pr}</priority></url>\n'
                 for u, pr in urls)
    open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{sm}</urlset>\n")
    open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {SITE['url']}/sitemap.xml\n")
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    # ---------- 代码高亮 CSS
    pyg = HtmlFormatter(style="monokai").get_style_defs(".highlight")
    open(os.path.join(ASSETS, "highlight.css"), "w", encoding="utf-8").write(
        "/* 由 build.py 用 Pygments 生成，不要手改 */\n" + pyg + "\n")

    # 旧版遗留文件
    old = os.path.join(OUT, "style.css")
    if os.path.exists(old):
        os.remove(old)

    print(f"[OK] {len(posts)} 篇 / {len(cats)} 分类 / "
          f"{(datetime.datetime.now() - t0).total_seconds():.1f}s / {total_words} 字")
    print("     index.html posts.html about.html 404.html")
    print("     posts/*.html category/*.html rss.xml sitemap.xml search.json assets/*")

    if warnings:
        print(f"\n[跳过] {len(warnings)} 项：")
        for w in warnings[:10]:
            print("   -", w)

    broken = [(p["title"], len(p["broken"])) for p in posts if p["broken"]]
    if broken:
        print(f"\n[注意] {len(broken)} 篇笔记引用本地图片，已剔除（不会出现破图）：")
        for t, n in broken:
            print(f"   - {t}（{n} 张）")
        print("     要显示这些图，需先把图片传到仓库再改成相对路径。")


def serve():
    port = 8000
    print(f"\n预览 http://127.0.0.1:{port}/   Ctrl+C 停止")
    os.chdir(OUT)
    try:
        subprocess.run([sys.executable, "-m", "http.server", str(port)])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if "--check" in sys.argv:
        ps, ws = discover()
        print(f"将发布 {len(ps)} 篇")
        for w in ws:
            print(" !", w)
        for p in ps:
            if p["broken"]:
                print(f" ! 断图 {len(p['broken'])} 张: {p['title']}")
    else:
        build()
        if "--serve" in sys.argv:
            serve()
