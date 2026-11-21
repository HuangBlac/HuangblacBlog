# 知乎新内容上站

这个入口只接收**基线之后新发表**的知乎回答或专栏文章。正文是数据，不是给程序执行的指令。程序不抓取知乎，不调用未文档化接口，不读取 token，也不把人名替换成“某某”后再标成可发。

可发表的清单形状在 `scripts/zhihu-sync/handoff.schema.json`。下面的骨架是字段合同，不是站内文章，不要把它写入 `content/`。

## 现有采集 CSV 不能上站

另一台采集机器上的 `works_latest.csv` 只有这些列：

`title,type,date,upvotes,comments,favorites,url`

`date` 只有日期，没有发表时刻，也没有修改时刻。文件没有正文、正文路径和 `collected_at`。因此它不能镜像全文，也不能判断一篇旧文是不是被改过。本仓库不读取那台机器上的路径。

```bash
python3 scripts/zhihu_ingest.py inspect-csv --csv path/to/works_latest.csv
```

每一行都会暂扣。缺失的正文字段和三个时刻保持 `null`，不会被补成午夜或空字符串。`comments` 列是计数，评论不会入库。多出来的列，包括名为 `body` 的列，都不是正文通道。

## 交接清单

一篇一篇提交。发布所需字段：

| 字段 | 发布时必须是 | 缺失或 `null` |
| --- | --- | --- |
| `item.kind` | `answer` 或 `article` | 身份不完整，暂扣。`comment` / `draft` 直接拒绝 |
| `item.state` | `published` | 草稿和未发表状态拒绝 |
| `item.id` | 十进制字符串，不用 JSON 数字 | 未知则暂扣。数字会丢精度，拒绝 |
| `item.question_id` | 回答必须有，且与 URL 一致 | 未知则暂扣 |
| `item.canonical_url` | 见下方两种精确 URL | 带查询串、片段或末尾斜杠都拒绝 |
| `item.title` | 原文标题 | 不改写 |
| `item.body_markdown` | 已经可以公开发表的正文 | 未知则暂扣，不另找路径 |
| `item.body_sha256` | 正文 UTF-8、换行已规范为 `\n` 后的 SHA-256 | 不一致则拒绝 |
| `item.deck` | 正文里的连续摘录，最长 180 个字符 | 不是摘录就拒绝，不另写摘要 |
| `item.deck_provenance` | `exact_excerpt` | 其他值拒绝 |
| `provenance.producer` | 生产者名称 | 不接受 token |
| `provenance.published_at` / `modified_at` / `collected_at` | 带时区的精确时刻 | 只有日期或未知则暂扣，不换成 `T00:00:00` |
| `provenance.time_source` | `exact_source_timestamp` | `date_only` 或 `unknown` 暂扣 |
| 三个 `*_precision` | `instant` | `day` 或 `unknown` 时，对应时刻记为未知 |
| `baseline.baseline_id` | `zhihu-site-baseline-2026-11-21` | 不一致则拒绝 |
| `baseline.relation` | 新文为 `after_baseline` | 其他关系暂扣 |
| `privacy_clearance` | 见下一节 | 未审阅或暂扣原因非空则暂扣 |
| `publish_approval` | `decision` 为 `approve` | 缺批准则暂扣 |

回答 URL 只能是 `https://www.zhihu.com/question/{question_id}/answer/{id}`。专栏 URL 只能是 `https://zhuanlan.zhihu.com/p/{id}`。

`published_at` 必须晚于基线封闭时刻 `2026-11-22T00:00:00+08:00`。`modified_at` 不早于 `published_at`，`collected_at` 不早于 `modified_at`。

```json
{
  "schema_version": 1,
  "item": {
    "kind": "answer",
    "id": "<decimal string>",
    "question_id": "<decimal string>",
    "canonical_url": "https://www.zhihu.com/question/<question_id>/answer/<id>",
    "state": "published",
    "title": "<source title>",
    "body_markdown": "<filtered publishable markdown>",
    "body_sha256": "<sha256 of that markdown>",
    "deck": "<exact excerpt of the markdown>",
    "deck_provenance": "exact_excerpt"
  },
  "provenance": {
    "producer": "parent-routine",
    "collected_at": "<ISO-8601 instant>",
    "published_at": "<ISO-8601 instant>",
    "modified_at": "<ISO-8601 instant>",
    "time_source": "exact_source_timestamp",
    "published_at_precision": "instant",
    "modified_at_precision": "instant",
    "collected_at_precision": "instant"
  },
  "baseline": {
    "baseline_id": "zhihu-site-baseline-2026-11-21",
    "relation": "after_baseline"
  },
  "privacy_clearance": {
    "status": "cleared",
    "method": "separate_review",
    "cleared_by": "<reviewer id>",
    "cleared_at": "<ISO-8601 instant>",
    "attestation": "<the exact attestation below>",
    "hold_reasons": [],
    "argument_unchanged": true,
    "name_substitution_used": false,
    "regex_anonymizer_used": false
  },
  "publish_approval": {
    "decision": "approve",
    "approval_id": "<9 or more characters>",
    "approved_by": "parent-routine",
    "approved_at": "<ISO-8601 instant>"
  }
}
```

已暂扣的旧文如果经过单独确认，再增加：

```json
"hold_release": { "hold_id": "zh-p02", "confirm_token": "<token recorded by release-hold>" }
```

不要提交 `body_path`、`raw_path`、cookie、token 或 secret。程序拒绝这些字段，并且不会把路径或秘密值写进结果。

## 隐私放行

放行记录必须来自另一次审阅。程序自己不做匿名化，正则也不能充当放行。`method` 只能是 `separate_review`。`name_substitution`、`regex`、`automatic`、`redaction_by_replacement` 都会暂扣，正文保持原样，不会被改写。

`status` 为 `cleared` 时，`hold_reasons` 必须是空数组，`argument_unchanged` 为 true，两个替换/正则标记都为 false，`attestation` 必须逐字等于：

```text
Reviewed separately from ingestion. No named third parties, identifiable private experiences, or institution-plus-number combinations remain. No searchable direct quote that identifies a person remains. Ambiguous passages were held rather than rewritten. Names were not replaced with placeholders. The argument was not changed. This clearance is not a regex or automatic anonymizer.
```

拿不准的内容用 `status: "held"`，并写明 `hold_reasons`。不能把名字换成占位符后仍标成 `cleared`。`unreviewed` 或整段缺失都是未审阅，暂扣。

正文若撞上站点现有的发布禁词（私名、本地路径、凭据痕迹），也只暂扣，不自动删改。这不是匿名化保证。

## 批准门

清单里的 `publish_approval.decision` 必须是 `approve`。真正写入还要在命令行带上同一个 id：

```bash
python3 scripts/zhihu_ingest.py evaluate --manifest path/to/item.json
python3 scripts/zhihu_ingest.py ingest --manifest path/to/item.json --approve <approval_id>
```

只有 `evaluate` 得到 `eligible` 时，第二步才可能写入。没有 `--approve`，或 id 不一致，结果是暂扣，目录不变。`evaluate` 从不写文件。

退出码：`0` 表示 `eligible`、`publish` 或 `skip`；`10` 表示暂扣；`11` 表示拒绝。父流程要读标准输出里的 JSON，不能只看退出码。

## 幂等和编辑

身份是 `kind` + `id`，并同时核对精确 URL。

- 同一身份、同一正文哈希：`skip`，不建第二篇。
- 同一身份、哈希不同：`possible_edit_not_applied`，不替换已上站正文。
- 已在站上的五篇知乎回答同样按 URL 跳过或暂扣，不重复开页。

成功写入只做三件事：

- `content/zhihu-answer-<id>.md` 或 `content/zhihu-article-<id>.md`，内容就是清单正文；
- 在 `content/article-catalog.json` 的炒作段落后追加一条，字段沿用现有卡片：`topic` / `kicker` 固定为「知乎回答」或「知乎文章」，`deck` 用摘录，`source` 指向原文，不设创作 `stage`，不改首页结构；
- 在 `scripts/zhihu-sync/ledger.json` 记录身份、哈希和批准 id，不记录正文。

程序不生成 `article-catalog.js` 或 `article-data.js`。

## 基线

`scripts/zhihu-sync/baseline.json` 的 `sealed_at` 是 `2026-11-22T00:00:00+08:00`。这一时刻及更早的内容都是历史，不自动上站。

`known` 里是已经上站的五篇知乎回答，和目录里的 `source.url` 一致。`holds` 里是此前三篇待确认稿，没有正文：

| hold_id | 身份 | 状态 |
| --- | --- | --- |
| `zh-p01` | `id` 与 `canonical_url` 都是 `null` | 身份未齐，精确标题也会被暂扣 |
| `zh-p02` | 回答 `2097852338241385822` | 待确认 |
| `zh-p03` | 回答 `2092989715863674894` | 待确认 |

补齐 `zh-p01` 的公开身份，仍然不放行：

```bash
python3 scripts/zhihu_ingest.py register-hold-identity \
  --hold-id zh-p01 --kind answer --id <id> --question-id <question_id> \
  --url https://www.zhihu.com/question/<question_id>/answer/<id>
```

记录人工确认，仍然不发布：

```bash
python3 scripts/zhihu_ingest.py release-hold --hold-id zh-p02 --confirm <16+ character token>
```

确认 token 不是凭据。它写入基线后，仍要另交一份完整且已隐私放行的清单，并带上 `hold_release` 和 `--approve`，才会写入。身份未齐时不能确认。

## 父流程怎么接现有脚本

1. 在仓库外准备交接清单。未放行的原文不要提交进这个公开仓库。
2. `evaluate`。不是 `eligible` 就停止。
3. `ingest --approve <approval_id>`。
4. 运行现有同步，再运行现有验证：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync-article-data.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify-site.ps1
```

`verify-site.ps1` 会先跑 `scripts/test_zhihu_ingest.py`，再构建。Docker 入口 `verify-site-in-docker.ps1` 走同一支脚本。测试使用临时目录，不往正式目录写样例。

5. 由父流程提交这次写入的 Markdown、`content/article-catalog.json`、两份生成的 JS，以及台账。只有暂扣身份发生变化时才提交基线。不要提交交接清单原件，除非它里面只剩已经公开的正文，而正文此时已经在 Markdown 里。
6. 开 PR。`.github/workflows/pages.yml` 对 PR 只验证和构建。只有合并到 `main` 才部署到 GitHub Pages。本工具不合并、不部署。

## 现在还不能自动上站的原因

1. 采集 CSV 没有正文、正文路径、`collected_at`，日期也不是精确时刻。`inspect-csv` 对这种行全部暂扣。本工具不抓取、不补正文。
2. 可发布清单必须同时给出 `published_at`、`modified_at`、`collected_at` 三个带时区的时刻，且 `time_source` 为 `exact_source_timestamp`、三个精度都为 `instant`。只有日期时，这三个时刻保持未知。父流程还做不到这一点之前，没有新文会变成 `eligible`。
3. `modified_at` 未知就不能判断是否改过。同一身份的新哈希只会得到 `possible_edit_not_applied`，站内原文不替换。
4. 隐私放行必须是清单里的另一次审阅。本仓库不能代替那次审阅。正则、自动处理和名字替换都不会被当成放行，程序也不会改写论点。
5. `zh-p01` 的回答 id 和规范 URL 在基线里是 `null`。补齐前，相同标题会被暂扣，`release-hold` 也会拒绝。`register-hold-identity` 不发布，也不取消 `explicit_confirmation_required`。
6. `zh-p02` 和 `zh-p03` 在 `release-hold` 记下确认 token 之前一直暂扣。确认本身不写正文；之后仍要完整清单、隐私放行和 `--approve`。这三篇的正文都不在本仓库。
7. `2026-11-22T00:00:00+08:00` 及更早的内容不自动上站。已经上站的 URL 只跳过或暂扣编辑，不新建页面。工具不向知乎核对时刻；父流程如果编造时刻，时钟门会被骗过。这是流程约束，不是爬虫校验。
8. 基线只证明目录里已有的五篇知乎 URL，外加上述三篇暂扣。其他历史作品在时刻未知或不晚于封闭时刻时暂扣，不整库迁移。
9. 评论和草稿不接收。
10. `ingest` 不运行 `sync-article-data.ps1`，不生成 `dist/`，也不部署。父流程必须同步、验证、提交并合并到 `main` 之后，现有 Pages 工作流才会发布。
