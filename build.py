# -*- coding: utf-8 -*-
"""
build.py —— 把 D:\\mdstudyfile 的笔记转成静态博客
用法: py build.py
"""
import os, re, shutil, html, json, datetime
import markdown
from pygments.formatters import HtmlFormatter

SRC = r"D:\mdstudyfile"
OUT = r"D:\GitHub-Pages"
POSTS = os.path.join(OUT, "posts")

# 选定的文章: (源文件相对路径, 输出slug, 标题, 分类, 日期, 摘要)
ARTICLES = [
    (r"应急响应杂项\03-流量分析\Shiro反序列化RCE流量分析WriteUp.md",
     "shiro-deserialization-traffic",
     "Shiro RememberMe 反序列化 RCE 流量分析",
     "应急响应",
     "2026-07-10",
     "从抓包流量中定位 Shiro 默认密钥攻击：指纹识别（rememberMe=deleteMe）、AES-CBC 解密 Cookie、Java 序列化魔数识别，到通过 CAFEBABE 字节码提取恶意类名。"),

    (r"应急响应杂项\03-流量分析\Webshell上传与加密隧道分析WriteUp.md",
     "webshell-encrypted-tunnel",
     "Webshell 上传与加密隧道流量分析",
     "应急响应",
     "2026-07-08",
     "还原一条完整的入侵链：端口扫描 → Web 路径探活 → 上传 Webshell → 加载 PHP 后门框架 → 添加后门用户，以及如何从加密流量中识别隧道特征。"),

    (r"应急响应杂项\02-日志分析\SSH暴力破解与日志分析WriteUp.md",
     "ssh-bruteforce-log-analysis",
     "SSH 暴力破解与日志分析",
     "应急响应",
     "2026-07-08",
     "认证日志 + 防火墙日志 + 审计日志三源关联：定位真实攻击 IP、识别混淆执行的恶意命令、还原下载的脚本与授予的执行权限。"),

    (r"应急响应杂项\01-基础知识\Windows安全日志分析-RDP暴力破解.md",
     "windows-rdp-bruteforce-log",
     "Windows 安全日志分析：RDP 暴力破解识别",
     "应急响应",
     "2026-07-08",
     "事件 ID 与 LogonType 速查，XML 日志的 Excel / Power Query / PowerShell 三种分析路径，如何用 IP 分组统计从 177 条失败记录中锁定攻击源。"),

    (r"web\Web安全-SQL盲注与WAF绕过解题WriteUp.md",
     "sql-injection-waf-bypass",
     "SQL 盲注与 WAF 黑名单绕过",
     "Web 安全",
     "2026-07-15",
     "WAF 黑名单绕过的手法拆解：用制表符替代空格、用异或替代 and/or、分析黑名单的子串匹配逻辑，以及布尔盲注的二分探测方法。"),

    (r"应急响应杂项\01-基础知识\Linux日志分析基础.md",
     "linux-log-analysis-basics",
     "Linux 日志分析基础",
     "应急响应",
     "2026-07-08",
     "应急响应中 Linux 侧的核心日志位置与判读方法：auth.log / secure 的认证记录、Web 访问日志的异常特征、以及快速筛出可疑行为的方法。"),
]

# ---------------- 站点信息 ----------------
SITE = {
    "title": "pressure-J 的技术笔记",
    "author": "pressure-J",
    "desc": "网络安全 · 应急响应 · 流量分析 · 密码学",
    "github": "https://github.com/pressure-J",
}

# 发布前脱敏：不写死真名，运行时从本机用户名推导，避免仓库里泄露个人信息
_LOCAL_USER = os.path.basename(os.path.expanduser("~"))


def scrub(text):
    """发布前脱敏：真名 → pressure-J，本机绝对路径 → 占位符。
    用正则匹配任意数量的反斜杠/正斜杠，避免转义层数不一致导致漏替换。"""
    BS = r"[\\/]+"
    rules = [
        (rf"C:{BS}Users{BS}" + re.escape(_LOCAL_USER), "<工作目录>"),
        (rf"D:{BS}python", "<工具目录>"),
        (rf"D:{BS}mdstudyfile", "<笔记目录>"),
        (rf"D:{BS}网络安全工具", "<工具目录>"),
        (rf"D:{BS}GitHub-Pages", "<站点目录>"),
    ]
    for pat, rep in rules:
        text = re.sub(pat, rep, text)
    if _LOCAL_USER:
        text = text.replace(_LOCAL_USER, "pressure-J")
    return text

CSS = """
:root {
  --bg: #0d1117; --bg2: #161b22; --border: #30363d;
  --fg: #e6edf3; --fg2: #8b949e; --accent: #58a6ff; --accent2: #7ee787;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  line-height: 1.75; font-size: 16px;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 820px; margin: 0 auto; padding: 0 24px; }

/* 头部 */
header {
  border-bottom: 1px solid var(--border); background: rgba(13,17,23,.85);
  backdrop-filter: blur(8px); position: sticky; top: 0; z-index: 10;
}
header .wrap { display: flex; align-items: center; justify-content: space-between; height: 64px; }
.logo { font-weight: 700; font-size: 17px; color: var(--fg); }
.logo span { color: var(--accent2); }
nav a { margin-left: 26px; color: var(--fg2); font-size: 15px; }
nav a:hover, nav a.on { color: var(--fg); text-decoration: none; }

/* 首屏 */
.hero { padding: 88px 0 64px; }
.hero h1 { font-size: 40px; line-height: 1.3; margin-bottom: 18px; letter-spacing: -.5px; }
.hero h1 em { font-style: normal; color: var(--accent); }
.hero .sub { font-size: 17px; color: var(--fg2); max-width: 640px; }
.tags { margin-top: 26px; }
.tag {
  display: inline-block; padding: 4px 13px; margin: 0 8px 8px 0;
  border: 1px solid var(--border); border-radius: 999px;
  font-size: 13px; color: var(--fg2); background: var(--bg2);
}

/* 卡片列表 */
.sec-title {
  font-size: 13px; text-transform: uppercase; letter-spacing: 1.2px;
  color: var(--fg2); margin: 56px 0 20px; padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
article.card {
  padding: 20px 0; border-bottom: 1px solid var(--border);
}
article.card:last-child { border-bottom: none; }
article.card h3 { font-size: 19px; margin-bottom: 7px; font-weight: 600; }
article.card h3 a { color: var(--fg); }
article.card h3 a:hover { color: var(--accent); text-decoration: none; }
article.card p { color: var(--fg2); font-size: 14.5px; }
.meta { font-size: 13px; color: var(--fg2); margin-top: 9px; }
.meta .cat {
  color: var(--accent2); background: rgba(126,231,135,.1);
  padding: 2px 9px; border-radius: 4px; margin-right: 10px;
}

/* 文章正文 */
.post-head { padding: 56px 0 32px; border-bottom: 1px solid var(--border); }
.post-head h1 { font-size: 32px; line-height: 1.35; margin-bottom: 14px; }
.content { padding: 40px 0 80px; }
.content h1 { font-size: 26px; margin: 40px 0 16px; }
.content h2 {
  font-size: 22px; margin: 40px 0 16px; padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.content h3 { font-size: 18px; margin: 30px 0 12px; }
.content h4 { font-size: 16px; margin: 24px 0 10px; color: var(--fg2); }
.content p { margin: 15px 0; }
.content ul, .content ol { margin: 15px 0 15px 26px; }
.content li { margin: 7px 0; }
.content blockquote {
  border-left: 3px solid var(--accent); background: var(--bg2);
  padding: 12px 18px; margin: 20px 0; color: var(--fg2); border-radius: 0 6px 6px 0;
}
.content code {
  background: rgba(110,118,129,.25); padding: 2px 6px; border-radius: 4px;
  font-family: "Cascadia Code", Consolas, Monaco, monospace; font-size: 14px;
  color: #ffa657;
}
.content pre {
  background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px; overflow-x: auto; margin: 20px 0; line-height: 1.6;
}
.content pre code { background: none; padding: 0; color: var(--fg); font-size: 13.5px; }
.table-wrap { overflow-x: auto; margin: 20px 0; }
.content table {
  border-collapse: collapse; width: 100%; font-size: 14.5px;
  display: table;
}
.content th, .content td { border: 1px solid var(--border); padding: 9px 13px; text-align: left; }
.content th { background: #1c2230; font-weight: 600; color: #fff; }
.content tr:nth-child(even) td { background: rgba(22,27,34,.6); }
.content img { max-width: 100%; border-radius: 6px; }
.content hr { border: none; border-top: 1px solid var(--border); margin: 36px 0; }
.content a { border-bottom: 1px solid rgba(88,166,255,.3); }

/* 代码高亮 */
.highlight { background: var(--bg2) !important; }
%PYGMENTS%

/* 页脚 */
footer {
  border-top: 1px solid var(--border); padding: 32px 0; margin-top: 40px;
  color: var(--fg2); font-size: 14px;
}
footer .wrap { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px; }

@media (max-width: 640px) {
  .hero h1 { font-size: 29px; }
  .hero { padding: 52px 0 40px; }
  nav a { margin-left: 16px; font-size: 14px; }
  .post-head h1 { font-size: 24px; }
}
"""

HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="stylesheet" href="{root}style.css">
</head>
<body>
<header>
  <div class="wrap">
    <a class="logo" href="{root}index.html">{author}<span>.</span></a>
    <nav>
      <a href="{root}index.html"{n1}>首页</a>
      <a href="{root}posts.html"{n2}>文章</a>
      <a href="https://github.com/pressure-J"{n3}>GitHub</a>
    </nav>
  </div>
</header>
"""

FOOT = """
<footer>
  <div class="wrap">
    <div>&copy; 2026 {author} · 网络安全方向</div>
    <div><a href="https://github.com/pressure-J">GitHub</a></div>
  </div>
</footer>
</body>
</html>
"""


def md2html(text):
    md = markdown.Markdown(extensions=[
        "fenced_code", "codehilite", "tables", "toc", "attr_list", "sane_lists",
    ], extension_configs={
        "codehilite": {"css_class": "highlight", "guess_lang": False, "linenums": False},
    })
    return md.convert(text)


def strip_front(text):
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.S)
    return text[m.end():] if m else text


def build():
    if os.path.isdir(POSTS):
        shutil.rmtree(POSTS)
    os.makedirs(POSTS, exist_ok=True)

    # 1. 生成文章页
    ok = []
    for rel, slug, title, cat, date, summary in ARTICLES:
        path = os.path.join(SRC, rel)
        if not os.path.exists(path):
            print(f"  [跳过] 找不到 {rel}")
            continue
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        body = md2html(scrub(strip_front(raw)))
        page = HEAD.format(title=title, desc=summary, root="../",
                           author=SITE["author"], n1="", n2="", n3="") + f"""
<div class="wrap">
  <div class="post-head">
    <h1>{title}</h1>
    <div class="meta"><span class="cat">{cat}</span>{date}</div>
  </div>
  <div class="content">
{body}
  </div>
</div>
""" + FOOT.format(author=SITE["author"])
        with open(os.path.join(POSTS, slug + ".html"), "w", encoding="utf-8") as f:
            f.write(page)
        ok.append((slug, title, cat, date, summary))
        print(f"  [OK] {slug}.html")

    # 2. 文章列表页
    cards = ""
    for slug, title, cat, date, summary in ok:
        cards += f"""  <article class="card">
    <h3><a href="posts/{slug}.html">{title}</a></h3>
    <p>{summary}</p>
    <div class="meta"><span class="cat">{cat}</span>{date}</div>
  </article>
"""
    posts_page = HEAD.format(title=f"文章 · {SITE['title']}", desc=SITE["desc"],
                             root="", author=SITE["author"], n1="", n2=' class="on"', n3="") + f"""
<div class="wrap">
  <div class="hero" style="padding-bottom:0">
    <h1>技术文章</h1>
    <p class="sub">共 {len(ok)} 篇 · 应急响应 / 流量分析 / Web 安全</p>
  </div>
  <div class="sec-title">全部文章</div>
{cards}
</div>
""" + FOOT.format(author=SITE["author"])
    with open(os.path.join(OUT, "posts.html"), "w", encoding="utf-8") as f:
        f.write(posts_page)

    # 3. 首页
    top = ""
    for slug, title, cat, date, summary in ok[:4]:
        top += f"""  <article class="card">
    <h3><a href="posts/{slug}.html">{title}</a></h3>
    <p>{summary}</p>
    <div class="meta"><span class="cat">{cat}</span>{date}</div>
  </article>
"""
    index = HEAD.format(title=SITE["title"], desc=SITE["desc"],
                        root="", author=SITE["author"], n1=' class="on"', n2="", n3="") + f"""
<div class="wrap">
  <div class="hero">
    <h1>网络安全方向在读，<br>专注<em>应急响应</em>与<em>流量分析</em>。</h1>
    <p class="sub">
      这里是 {SITE['author']} 的技术笔记。记录日志分析、流量取证、Web 漏洞原理与密码学工具开发中
      踩过的坑和想清楚的事——不写流水账，只写能复现、能讲清的过程。
    </p>
    <div class="tags">
      <span class="tag">应急响应</span>
      <span class="tag">流量分析</span>
      <span class="tag">日志溯源</span>
      <span class="tag">Web 安全</span>
      <span class="tag">密码学</span>
      <span class="tag">Python</span>
    </div>
  </div>
  <div class="sec-title">近期文章</div>
{top}
  <div style="margin:26px 0 60px"><a href="posts.html">查看全部 {len(ok)} 篇文章 &rarr;</a></div>
</div>
""" + FOOT.format(author=SITE["author"])
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)

    # 4. 样式
    pyg = HtmlFormatter(style="monokai").get_style_defs(".highlight")
    css = CSS.replace("%PYGMENTS%", pyg)
    with open(os.path.join(OUT, "style.css"), "w", encoding="utf-8") as f:
        f.write(css)

    print(f"\n完成：{len(ok)} 篇文章 + index.html + posts.html + style.css")


if __name__ == "__main__":
    build()
