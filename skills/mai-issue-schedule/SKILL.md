---
name: mai-issue-schedule
description: |
  问题统一编排层。拉取名下 IPD 问题单（待办/未关闭/全部三种范围），按优先级/模块/状态等
  维度过滤查询，关联 fix-db 输出 fix MR 链接与处理进度。统一展示待处理与已处理问题。
  触发词："我还有哪些问题"、"问题待办"、"查询问题单"、"查 Critical 问题"、"问题编排"、"schedule"。
---

# 问题统一编排 (mai-issue-schedule)

统一查看名下 IPD 问题单与处理进度：待办问题来自 IPD（未关闭），已 fix 问题通过 fix-db 关联 MR 链接。

## 范围术语（查询的第一个参数）

| 术语 | 含义 | IPD filters |
|------|------|-------------|
| `待办`（默认） | 名下未关闭问题 | `issueAssigneeId=我` + `issueStatus NOT_IN [Closed, Verified]` + `deleted=0` |
| `未关闭` / `活动` | 未关闭问题（可指定指派人，默认全部） | `issueStatus NOT_IN [Closed, Verified]` + `deleted=0` |
| `全部` | 所有问题 | `deleted=0` |

## 过滤维度（可组合）

| 维度 | 参数 | 对应 filter |
|------|------|------------|
| 严重等级 | `--priority` | `issuePriority`: Critical / Blocker / Major / Minor / Trivial |
| 测试模块 | `--module` | `issueTestComponent`（LIKE） |
| 研发模块 | `--rd-module` | `exHandleAction`（LIKE） |
| 状态 | `--status` | `issueStatus`: OPEN / In Progress / Resolved / Reopened / Verified / Closed |
| 指派人 | `--assignee` | `issueAssigneeId`（默认当前用户） |

## 触发方式

- "我还有哪些问题待处理" → 待办（默认范围）
- "查 Critical 问题" / "问题模块是相册的" → 待办 + 维度
- "查所有未关闭问题" / "查全部问题" → 未关闭 / 全部
- "ISS-xxx 的 MR" → 单问题详情 + fix-db MR 关联

## 前置

环境门禁（复用 `mai-env-doctor` / `setup.py`）：`mi-adt` MCP 配置存在（脚本直连其 API）、`mai-issue-query.py` 可用。WF_ROOT 定位：`python3 wf_root.py --check`（见 mai-env-doctor）。

> **为什么不直接调 mi-adt 工具**：`M_issueQuery` 返回每条问题 300+ 全字段（含工具 schema 说明），单次响应 200KB+，会撑爆上下文且输出截断。因此查询由 **`mai-issue-query.py` 脚本直连 mi-adt HTTP API** 完成，LLM 只拿到精简结果。

## 工作流程

### Step 1: 确定查询范围与维度

按用户的自然语言确定：
- 范围：`待办`（默认）/ `未关闭` / `全部`
- 维度：优先级 / 模块 / 状态 / 指派人（可组合）

### Step 2: 脚本查询（直接调 mi-adt API,零上下文消耗）

运行查询脚本（WF_ROOT 定位见 mai-env-doctor）：

```bash
python <WF_ROOT>/mai-issue-query.py <范围> [维度...]

# 示例
python <WF_ROOT>/mai-issue-query.py 待办                    # 名下待办
python <WF_ROOT>/mai-issue-query.py 待办 --priority Critical # 待办+Critical
python <WF_ROOT>/mai-issue-query.py 待办 --module 互联互通    # 待办+模块
python <WF_ROOT>/mai-issue-query.py 全部 --json              # 全部(机器可读)
```

脚本行为：
- 从 `~/.claude.json`/opencode 配置读取 mi-adt url/token（不硬编码）
- 分页拉取全量 → 只提取 issId/title/priority/status/component/changeId
- 关联 fix-db（MR 链接 + 回流 + 处理进度）
- 直接输出精简表格

**脚本不可用时 fallback**：调用 `mi-adt` `M_issueQuery`（pageSize 20 分页），但必须用工具输出**保存文件**解析（从第一个 `{` 用 `raw_decode`,忽略截断尾与 schema 说明），禁止读完整响应。

### Step 3: 输出统一表格

脚本已输出 `## 问题编排 (<范围> 共 N 条)` 表格，直接展示给用户。补充说明：
- 待办列表只含未 fix 问题；已 fix（状态流转 Resolved/Closed）的问题不在待办
- fix-db 有记录的问题显示处理进度；无记录为未登记

### 已处理问题查询（不在待办中）

用户查已 fix 问题的 MR/IPD 关联：
```bash
python <WF_ROOT>/fix-db.py query <issId>     # 按问题查
python <WF_ROOT>/fix-db.py list --mr !<n>     # 按 MR 查关联问题
```

## 输出维度说明

- 问题单名 = `issId` + `issueTitle`
- fix MR = fix-db 关联的 MR 链接（可点击）
- 处理进度 = fix-db 状态机（analyzing/conclusion_uploaded/fixing/implementing/mr_created/merged/closed）

## 个人偏好配置

- `userName`: IPD 用户名（默认 pengyaozong）
- `mr_base_url`: MR 链接前缀（默认 `https://git.n.xiaomi.com/ai-framework/osbot`）

## 错误处理

- **mi-adt 查询失败**: `mai-env-doctor` / `setup.py check` 定位 MCP 问题,重试一次
- **分页截断**: pageSize 50,结果多时分页续查
- **fix-db 未装**: 提示运行 `python <WF_ROOT>/fix-db.py` 或检查仓库位置

## 依赖

- 环境: `mai-env-doctor` / `setup.py` - 环境门禁
- MCP: `mi-adt` - IPD 问题查询
- 数据库: `fix-db.py` - MR/IPD 关联与进度
