# pressure-J.github.io

个人技术博客 —— 网络安全 / 应急响应 / 流量分析。

线上地址：**https://pressure-j.github.io**

---

## 这个仓库在干什么

站点不是手写的。仓库里的 `build.py` 读取本地的 Markdown 笔记，
编译成纯静态 HTML 后提交到这里，由 GitHub Pages 直接托管。

```
Markdown 笔记  ──build.py──▶  HTML/CSS/JS  ──git push──▶  GitHub Pages
```

好处是不用维护两套内容：笔记本身就在 Typora 里写，改完重跑一次构建，
正文、摘要、目录、RSS、搜索索引、sitemap 全部自动更新。

## 目录结构

```
├─ build.py              生成器：解析笔记 → 渲染页面 → 输出全站
├─ index.html            首页（精选 + 最新 + 分类入口）
├─ posts.html            全部文章（前端搜索 + 分类筛选）
├─ about.html            关于
├─ 404.html              GitHub Pages 会自动接管
├─ category/             7 个分类的归档页
├─ posts/                每篇笔记一个页面，按拼音生成 slug
├─ assets/
│   ├─ style.css         全站样式（深/浅双主题，CSS 变量驱动）
│   ├─ highlight.css     Pygments 代码高亮，构建时生成
│   └─ app.js            主题切换 / 搜索筛选 / 目录高亮 / 复制按钮 / 阅读进度
├─ search.json           前端搜索索引
├─ rss.xml / sitemap.xml / robots.txt
└─ .nojekyll             跳过 Jekyll 处理
```

## 本地使用

```bash
py build.py            # 重新生成整站
py build.py --serve    # 生成后起本地预览 http://127.0.0.1:8000
py build.py --check    # 只体检，不写盘（看哪些笔记会被收/被跳过）
```

依赖：`markdown`、`pygments`、`pypinyin`。

## 生成器的三条规则

**1. 白名单收录**
只有 `SOURCES` 里列出的笔记目录会被发布。`EXCLUDE_DIRS` / `EXCLUDE_FILES`
是硬闸门 —— 简历、求职规划、含真实机构域名的漏洞报告不在发布链路里，
不是"记得别写"的口头约定。

**2. 发布前脱敏**
`scrub()` 在渲染前把真名、本机绝对路径替换成占位符。摘要和搜索索引也走同一条
文本，所以不会从侧信道漏出去。

**3. 不产生破图/死链**
笔记里指向本机图片的引用会被剔除（图不传上去就永远不显示，而不是显示一个破图标）；
站内 `.md` 互链会改写成对应文章的 HTML 地址，指向未发布笔记的链接退化为纯文本。

## 前端特性

- 深色 / 浅色主题，跟随系统偏好，选择记在 localStorage
- 文章列表实时搜索（标题 / 摘要 / 标签）+ 分类过滤，`/` 直接聚焦
- 自动生成目录，滚动时高亮当前章节
- 代码块带语言标签与一键复制
- 阅读进度条、回到顶部、移动端抽屉导航
- RSS 订阅、sitemap、Open Graph 元信息
- 零前端框架、零构建服务，只有一份 CSS + 一个原生 JS 文件

## 内容来源

正文源文件是本地笔记库里的 Markdown 原件，不在此仓库中。
