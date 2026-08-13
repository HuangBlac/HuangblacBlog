# 史官数据契约

`events.jsonl` 是事实源，每行一个 UTF-8 JSON 对象。`<项目名>传.md` 是可重建的阅读稿，不要手工维护两份事实。

## 项目清单

每个项目固定保存在 `.shi-guan/projects/<project_id>/manifest.json`。

- `schema_version`：当前固定为 `1`。
- `project_id`：人工确认的稳定小写标识；项目改名或移动时不改变。
- `project_name`：传记标题和文件名所用的公开名称。
- `remote`：Git 远端 URL，仅用于身份校验；不保存本地绝对路径。
- `remote_fingerprint`：规范化远端 URL 的 SHA-256。
- `visibility`：`private` 或 `public`。
- `chronicle_file`：生成的 `<项目名>传.md` 文件名。
- `project_summary`：可选的一句话项目说明。

`state.json` 只保存 Git 增量扫描状态。`last_commit` 必须是已经写入正式事件的最新 Git SHA，`last_event_id` 指向承载该 SHA 的事件。没有传入 `--cursor` 的非 Git 事件不会改变这两个字段；运行 `scan` 也不能推进游标。

若进程恰在事件事实源落盘后、状态落盘前中断，使用同一事件和同一 `--cursor` 重试。脚本只会在该事件位于事实源末尾，且状态仍指向此前事件或初始空状态时恢复游标。写锁异常残留时，先确认没有史官进程运行，再人工删除对应 `.write.lock` 或 `.registry.lock`；脚本不会按时间猜测锁已失效。

## 事件

必填字段：

| 字段 | 规则 |
| --- | --- |
| `schema_version` | 固定为 `1` |
| `event_id` | 项目内唯一，稳定且只含小写字母、数字、点、下划线、连字符 |
| `project_id` | 必须与项目清单一致 |
| `occurred_on` | `YYYY-MM-DD` |
| `title` | 事实性短标题 |
| `summary` | 不虚构动机或因果的一段概述 |
| `facts` | 至少一项；每项含 `statement` 和非空 `evidence_ids` |
| `evidence` | 至少一项；每项含 `id`、`type`、`ref`、`label` |
| `tags` | 至少一个、不重复；供跨项目检索 |
| `visibility` | `private` 或 `public` |
| `zhihu_angles` | 可以为空；这里只写选题角度，不写新事实 |
| `supersedes` | 被本事件替代的旧事件 ID 数组 |
| `retracts` | 被本事件撤回的旧事件 ID 数组 |

可选字段 `commentary` 专门保存评论：

```json
{
  "label": "太史公曰",
  "text": "评价正文",
  "based_on": ["event-id"],
  "visibility": "private"
}
```

评论必须有证据边界，不得写入 `facts`。不要从提交时间先后自动推出因果、动机、人格或成败。

## 证据

允许的 `type`：

- `git_commit`
- `repo_file`
- `public_url`
- `user_statement`
- `issue`
- `pull_request`
- `release`

Git 证据 ID 使用 `git:<完整 SHA>`。一份证据只能进入一个事件；多个提交属于同一变化时，聚合成一个事件并保留全部证据。相同 `event_id` 和相同内容重复追加是 no-op；相同 ID 内容不同则拒绝。纠错使用 `supersedes` 或 `retracts`，不覆盖旧史料。

任何事件、项目清单和评论都不得包含本地绝对路径、密钥、聊天元数据或未经确认可保存的私密材料。`public_url` 只接受不含凭据和敏感查询参数的 HTTPS 地址。公开项目只能写入 `public` 事件与 `public` 评论。

## 检索事实包

写知乎文章前按关键词或标签运行 `search`。默认只返回仍然有效的事件；只有研究修订史时才加 `--include-inactive`。把搜索结果作为事实包交给 `huang-writing zhihu`，写作结果不能反向修改事件库。
