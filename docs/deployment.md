# 自定义域名部署

## 托管边界

网站内容仍由 GitHub Pages 托管，阿里云只负责 `huangblac.com` 的域名和 DNS。推送 `main` 后，现有 GitHub Actions 继续负责验证、构建和发布；不需要阿里云 ECS、Nginx 或单独的常驻服务器。

正式入口：<https://huangblac.com/>

回退入口：<https://huangblac.github.io/HuangblacBlog/>

## 阿里云 DNS 记录

在“云解析 DNS → 权威域名解析 → `huangblac.com` → 解析设置”中添加以下记录，解析线路保持“默认”：

| 主机记录 | 类型 | 记录值 |
| --- | --- | --- |
| `@` | `A` | `185.199.108.153` |
| `@` | `A` | `185.199.109.153` |
| `@` | `A` | `185.199.110.153` |
| `@` | `A` | `185.199.111.153` |
| `www` | `CNAME` | `huangblac.github.io` |

`@` 代表裸域 `huangblac.com`。`www` 的 CNAME 只能写域名，不能写 `https://`、仓库路径或裸域。保留邮箱使用的 MX/TXT 记录；删除同一主机记录下会冲突的旧 A、AAAA、CNAME 或停车页记录。暂不添加 IPv6 AAAA，除非确认需要并能同时维护 GitHub Pages 提供的四条 IPv6 地址。

## GitHub Pages 设置

1. 在 GitHub 个人设置的 Pages / Domains 中添加 `huangblac.com`，按 GitHub 给出的主机记录和值在阿里云添加 TXT 验证记录，并长期保留。
2. 在仓库 Settings → Pages → Custom domain 填写 `huangblac.com`。
3. 等待 Custom domain 旁出现绿色检查标记；DNS 解析成功不等于 HTTPS 证书已经签发。
4. 证书可用后勾选 Enforce HTTPS，并测试裸域、`www`、HTTP→HTTPS、文章深链接和手机端资源。

当前工作流是自定义 GitHub Actions 发布，仓库不需要手工添加 `CNAME` 文件。

## 排错顺序

- `DNS Check in Progress`：先确认上表记录和 TXT 验证记录已公开，再等待 DNS 缓存刷新；不要反复修改 DNS。
- 保存自定义域名后数分钟仍未完成：在仓库 Pages 中移除并重新添加一次自定义域名，以重新触发证书申请。
- 超过 24 小时仍未完成：检查阿里云是否存在冲突记录、CAA 是否阻止 `letsencrypt.org`，并查看对应提交的 Actions 是否成功。
- 正式域名异常时：先使用 GitHub Pages 回退入口确认发布版本，再恢复 DNS 记录；不要在 DNS 仍指向 GitHub Pages 时先解绑自定义域名。

## 发布前隐私检查

公开文章和 `dist/` 不得包含未确认公开的本地绝对路径、设备信息、正文、凭据或聊天导出信息。文章中的虚构文本、错位地址和叙事道具不应被自动当作真实环境信息；只有确认其确实暴露真实本地环境时，才需要改写或移除。
