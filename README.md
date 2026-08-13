# HuangBlacBlog

“小黑的晓店”是黄晓黑的个人博客与项目索引，围绕四类内容组织：工作、习作、炒作、创作。

- 目标公开地址：<https://huangblac.com/>
- GitHub Pages 回退地址：<https://huangblac.github.io/HuangblacBlog/>
- 技术形态：原生 HTML、CSS、JavaScript，保留 `file://` 直接打开能力
- 发布方式：推送 `main` 后由 GitHub Actions 构建并部署到 GitHub Pages

首页展示代表工作、进行中的习作、公共写作、游戏项目和分阶段创作目录。页脚的隐藏入口通往六步点击谜题；完成谜题后可以进入“闭店以后”页面，阅读建站理由与更新计划。

## 本地预览

```powershell
python -m http.server 4173 --bind 127.0.0.1
```

访问 <http://127.0.0.1:4173/>。也可以直接双击 `index.html`，但本地服务器更接近 GitHub Pages 的访问方式。

## 文章维护

`content/article-catalog.json` 是全部公开文章元数据的唯一来源，正文位于 `content/`：

- 公共写作与创作数量都由目录实时决定，不在代码或文档中写死；
- 创作按完结短篇、草稿、灵感三个阶段组织；
- 创作条目必须显式填写 `stage`，不根据标题猜测完成度。

修改目录或 Markdown 正文后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-article-data.ps1
```

同步命令生成浏览器直接载入的 `article-catalog.js` 和 `article-data.js`。不要手工编辑这两个生成文件。生成器会统一换行和 JSON 转义，保证 Windows PowerShell 与 GitHub 的 Linux PowerShell 得到相同结果。

新增文章时，只需增加 Markdown 正文、在统一目录中登记元数据，再运行同步和统一验证脚本。构建输出中的文章总数与各阶段数量会随目录自动变化。

工作、习作和游戏项目卡片仍直接维护在 `index.html`。右侧“当前关注”的公开默认值和首页精选更新时间维护在 `site-data.js`；浏览器里的本地编辑只影响当前设备。

同步脚本负责重写文章浏览器数据，Docker 验证只检查它们是否已同步，不会自动修复。因此文章维护顺序固定为：修改目录或正文 → 运行 `sync-article-data.ps1` → 运行 `verify-site.ps1` 或 `verify-site-in-docker.ps1` → 提交。

## 测试与构建

每轮修改后统一运行一个入口：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-site.ps1
```

该脚本固定执行文章目录异常测试、静态构建和发布产物验证。它会验证：

- slug、顺序、栏目、阶段和正文路径合法且唯一；
- 每份公开 Markdown 都已登记，两个生成文件与目录同步；
- JavaScript 语法正确；
- 每篇文章都生成 `/article/<slug>/` 静态页面，并包含分享、canonical 与 Article JSON-LD 元数据；
- `sitemap.xml` 覆盖首页和全部正式文章 URL，公开目录不暴露 Markdown 源文件路径；
- `dist/` 只包含发布所需文件；
- 发布产物不含本名、本地路径、凭据、聊天导出信息或失效站内链接。

需要在与 GitHub 接近的固定 Linux 环境中复核时运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-site-in-docker.ps1
```

Docker 脚本使用 `Dockerfile.ci` 中固定摘要的 PowerShell 7.4 基础镜像，以及带官方 SHA-256 校验的 Node.js 24.19.0，并在容器中调用同一个 `verify-site.ps1`。每轮都会执行 `docker build`，但未变化的镜像层会由 Docker 自动复用；不会静默使用与当前 Dockerfile 不一致的旧镜像。

构建输出只允许使用项目根目录下的 `dist` 或 `dist-*`，避免误传目录时覆盖正文或源码。Linux 主机运行 Docker 包装时，容器会使用当前用户身份写入产物，避免留下 root 所有的文件。

## 发布与排错

`.github/workflows/pages.yml` 调用 `scripts/verify-site-in-docker.ps1`，Docker 再调用唯一入口 `scripts/verify-site.ps1`。因此本地 Docker 与线上 CI 使用同一容器环境和同一检查顺序。工作流在 PR 和非 `main` 手动任务上只构建验证，只有 `main` 可以上传并部署。线上仍显示旧版时，先查看仓库的 Actions：GitHub Pages 会在新任务失败时继续保留上一次成功版本。

本项目曾因 Windows 的 CRLF 与 Linux 的 LF、以及 PowerShell 5.1/7 的 JSON 格式差异导致部署失败。文章生成器已经统一这些差异；修改生成逻辑时必须同时在 Windows 与 Linux PowerShell 下验证。

自定义域名部署说明见 [`docs/deployment.md`](docs/deployment.md)。当前发布仍由 GitHub Pages 托管；阿里云只负责 `huangblac.com` 的 DNS。只有仓库 Settings → Pages 中的自定义域名检查通过并启用 HTTPS 后，才把 `https://huangblac.com/` 视为正式入口；GitHub Pages 地址保留作回退入口。

## 主要文件

- `index.html`、`styles.css`、`script.js`：首页结构、视觉和交互。
- `site-data.js`：公开的“当前关注”默认值与首页精选更新时间。
- `article.html`、`article.css`、`article.js`：统一文章阅读模板和 `file://` 兼容入口；构建时生成正式静态文章 URL。
- `content/article-catalog.json`：文章元数据唯一来源。
- `content/`：公共写作与创作 Markdown 正文。
- `article-catalog.js`、`article-data.js`：同步生成的浏览器数据。
- `caidan.html`、`caidan.js`：隐藏入口谜题。
- `after-hours.html`：建站理由与更新计划。
- `404.html`、`robots.txt`：站点错误页与抓取规则；`sitemap.xml` 在构建时生成。
- `assets/favicon-32.png`、`assets/apple-touch-icon.png`：浏览器与设备图标。
- `scripts/`：目录同步、异常测试、构建和发布产物验证。
- `Dockerfile.ci`：固定 PowerShell 与 Node.js 版本的 Linux 构建环境。
- `docs/个人博客-站点地图.md`：真实页面、入口和数据流。
- `docs/项目盘点.md`：网站实际展示项目的公开口径。
- `docs/四类内容的意义.md`：四分法的精炼设计依据。

## 发布边界

- 公开仓库与部署产物都不得包含本地绝对路径、私密正文、访问凭据或未确认的项目状态。
- 创作区只收录已确认公开的非成人内容；草稿和灵感默认折叠并明确标注完成阶段。
- 不引入后台、账号、评论、数据库或 CMS，除非真实维护需求已经超过静态方案。
- 自定义域名已进入 GitHub Pages 配置流程；DNS 已配置时仍需等待证书检查完成，并在 Pages 设置中启用 HTTPS。
