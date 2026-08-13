---
name: shi-guan
description: 为固定软件、研究、写作或创作项目建立并持续维护可核验的“项目名传.md”，从 neat-freak 盘点结果、Git 提交、项目文档和用户确认材料中筛选重要事件，去重后写入 HuangBlacBlog/seed，并按标签检索知乎案例；总结和成稿调用 huang-writing zhihu，可加入与事实分离的“太史公曰”。用户说“史官”“建传”“记入项目传”“把这次改动记下来”“从项目传找案例”“总结这个项目阶段”或完成固定项目的重要阶段时使用。
---

# 史官

维护项目经历，不维护当前项目真相。先让 `neat-freak` 盘点并校正当前文档，再把值得长期保留的变化写成有证据的事件。

以下命令里的 `<shi-guan-dir>` 指本 Skill 的目录。不要假定调用者正站在 Skill 目录中。

## 固定位置

- 在当前工作区或已知项目根中定位 `HuangBlacBlog`，把素材根目录固定为 `<HuangBlacBlog-root>/seed`。找不到该项目时停止写入，不另建同名目录。
- 把人读正本写为 `seed/<项目名>传.md`。
- 把项目清单、游标和事件事实源写入 `seed/.shi-guan/projects/<project_id>/`。
- 不在传记或事件中保存本地绝对路径；上面的固定路径只属于本 Skill 的运行约定。

## 先选择动作

1. 首次接触固定项目或用户说“建传”时，执行“注册与初传”。
2. 用户说“记一笔”“阶段完成”“收尾”或 `neat-freak` 刚完成盘点时，执行“增量纪事”。
3. 用户写知乎文章需要案例时，执行“案例检索与写作”。
4. 用户要求纠正旧记载时，执行“修史”，不要覆盖既有事件。

## 注册与初传

1. 确认 Git 根目录、公开名称、稳定 `project_id` 和 `origin`。路径不是身份；远端指纹是校验项。
2. 默认把 `seed` 当作私有素材库。未经用户明确确认，事件使用 `private`，不要提交、发布或部署这些文件。
3. 初始化项目：

```powershell
python -X utf8 <shi-guan-dir>/scripts/chronicle.py init --seed <seed> --project-id <id> --project-name <name> --remote <origin> --visibility private --summary <summary>
```

4. 运行 `scan` 读取 Git 历史。扫描只生成候选，不推进游标。
5. 把相关提交聚合成事件。纯格式化、远端初始化、无净变化的合并、临时修补和没有长期意义的机械改动默认不入传。
6. 每个事实引用明确证据。Git 历史只能证明发生了什么，不能证明作者动机、投入时长或全部代码归属。
7. 逐条执行 `append`。只有承载本批最后一笔提交的事件才传 `--cursor`；成功后才推进 Git 扫描状态。纯用户确认或文档证据事件可以不传游标。

## 增量纪事

1. 先读取项目的 `manifest.json`、`state.json` 和现有传记。
2. 若用户要求阶段总结，先完整执行 `neat-freak`；只使用其核验结果，不把它删除的过期事实重新写回项目文档。
3. 运行：

```powershell
python -X utf8 <shi-guan-dir>/scripts/chronicle.py scan --seed <seed> --project-id <id> --repo <repo-root>
```

4. 将候选合并为少量事件。一个事件至少满足一项：改变用户可见能力、改变长期结构或规则、留下可复用的失败与解决办法、形成可公开成果、改变项目阶段。
5. 按 [references/data-contract.md](references/data-contract.md) 建立事件 JSON，随后追加：

```powershell
python -X utf8 <shi-guan-dir>/scripts/chronicle.py append --seed <seed> --project-id <id> --event <event.json> --cursor <last-commit>
```

6. 追加后运行 `validate`。相同事件再次运行应返回 `UNCHANGED`；同一 Git 证据不能换一个事件 ID 重复进入。
7. 不自动记录未提交修改。它们只能作为“待确认观察”展示给用户，正式入传须等稳定证据或用户明确自述。

## 太史公曰

- 把它写入独立的 `commentary` 字段，明确属于评价。
- 评论只依据列出的事件，不推断人格、隐秘动机或道德品质。
- 默认两三句，指出项目当前最值得肯定的一点与一个尚存限制；材料不足时可以不写。
- 使用 `huang-writing zhihu` 的现实材料边界和个人节奏润色，但不得让修辞生成新事实。

## 案例检索与知乎写作

1. 按问题关键词和标签检索：

```powershell
python -X utf8 <shi-guan-dir>/scripts/chronicle.py search --seed <seed> --query <关键词> --tag <标签>
```

2. 从结果中选择能实际推进文章的一至五个事件。保持 commit、公开链接和用户自述的来源身份，不把推断写成亲历。
3. 把选中事件组成事实包，再完整调用 `huang-writing zhihu`。遵守它对 `human-writing`、材料数量、现实核验、修订和长稿检查的全部要求。
4. 项目传可以供文章取材，文章中的修辞和判断不能反向更新项目传。用户要求保存文章时另行使用明确路径，发布始终需要单独授权。

## 修史

- 新事实修正旧事实时，新建事件并用 `supersedes` 引用旧事件。
- 原事件不再成立时，新建撤回事件并用 `retracts` 引用旧事件。
- 保留旧事件供审计，渲染稿会明确标注状态。
- 不直接编辑 `events.jsonl`；使用脚本写入并运行验证。

## 完成检查

```powershell
python -X utf8 <shi-guan-dir>/scripts/chronicle.py validate --seed <seed> --project-id <id>
python -X utf8 -m unittest discover -s <shi-guan-dir>/tests -v
```

确认没有本地绝对路径、敏感信息、重复事件、未知证据引用或未声明的事实。最后简洁告诉用户新增了哪些事件、传记路径和游标位置。
