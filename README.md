# HuangBlacBlog

“小黑的晓店”是黄晓黑的个人博客与项目索引，围绕四类内容组织：工作、习作、炒作、创作。

当前首页采用内容优先的双栏结构：左侧直接呈现代表文章与项目摘要，右侧说明身份、当前关注和浏览方式。页面优先帮助陌生访客快速理解站点与作者，同时保留作者自己的状态入口。

## 本地预览

```powershell
python -m http.server 4173 --bind 127.0.0.1
```

访问 `http://127.0.0.1:4173/`。

## 测试与构建

运行完整的本地构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-site.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\validate-site.ps1
```

构建会检查统一文章目录列出的 Markdown 正文与两个网页数据文件是否同步，并检查全部 JavaScript 语法。生成的 `dist/` 只包含网页运行文件；校验会阻止本名、本地路径、凭据、对话导出信息、源码文档和失效的站内链接进入部署产物。

GitHub Actions 会在每次 PR 和 `main` 推送时执行相同的测试与构建。PR 只验证，不发布；`main` 通过全部检查后自动部署到 GitHub Pages。

## 编辑当前关注

本地预览时，“当前关注”卡片会显示“本地编辑”按钮，可以增删、改名和调整顺序。保存结果会留在当前浏览器中，刷新页面后仍然有效。

公开访客默认看不到编辑入口。如需在非本地域名打开编辑模式，可在网址末尾加入 `?edit=1`。这种编辑仍然只影响当前浏览器；需要更新所有访客看到的公开默认值时，请修改 `site-data.js` 中的 `currentFocus`。

## 编辑站内文章

“炒作”栏目中的完整原文保存在 `content/`。修改 Markdown 原稿后，运行下面的命令，把正文同步到支持直接双击打开的网页数据文件：

```powershell
.\scripts\sync-article-data.ps1
```

文章标题、简介、阶段、系列和外部来源统一由 `content/article-catalog.json` 管理。同步命令会生成浏览器直接读取的 `article-catalog.js` 与 `article-data.js`；不要手工编辑这两个生成文件。

## 主要文件

- `index.html`：内容流、个人侧栏与四类内容入口。
- `styles.css`：视觉与响应式样式。
- `script.js`：栏目定位与“当前关注”本地编辑交互。
- `site-data.js`：可独立维护的公开默认内容，例如“当前关注”。
- `article.html`、`article.css`：站内长文阅读页面。
- `article.js`：根据统一目录呈现文章、来源链接和系列导航。
- `article-catalog.js`、`article-data.js`：同步生成的目录与正文网页数据。
- `content/article-catalog.json`：全部公开文章元数据的唯一来源。
- `content/`：站内文章的 Markdown 原稿，包含 `content/creative/` 中的娱乐创作正文。
- `scripts/sync-article-data.ps1`：校验统一目录并同步两个网页数据文件。

## 当前边界

- 首版优先呈现工作与习作，炒作承担知乎引流。
- 创作作为次级或隐藏入口，不公开未确认的正文与设定。
- 网站内容采用外链优先策略，不批量搬运旧内容。
- 未经明确确认，不部署、不购买域名、不公开私有仓库或本地路径。
