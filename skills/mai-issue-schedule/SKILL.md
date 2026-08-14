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

环境门禁（复用 `mai-env-doctor` / `setup.py`）：`mi-adt` MCP 可用（查询）、fix-db 可用。

## 工作流程

### Step 1: 确定查询范围与维度

按用户的自然语言确定：
- 范围：`待办`（默认）/ `未关闭` / `全部`
- 维度：优先级 / 模块 / 状态 / 指派人（可组合）

### Step 2: 构造 mi-adt 查询

调用 `M_issueQuery`（或 `M_getIssueInfoDataList`），filters 按范围术语 + 维度组装，例如：

**待办 + Critical + 模块=相册**：
```json
{
  "filters": [
    {"key": "issueAssigneeId", "operator": "EQ", "value": ["<userName>"]},
    {"key": "issueStatus", "operator": "NOT_IN", "value": ["Closed", "Verified"]},
    {"key": "issuePriority", "operator": "EQ", "value": ["Critical"]},
    {"key": "issueTestComponent", "operator": "LIKE", "value": ["相册"]},
    {"key": "deleted", "operator": "EQ", "value": ["0"]}
  ],
  "pageInfo": {"pageNum": 1, "pageSize": 50},
  "sorts": [{"key": "issuePriority", "value": "asc"}]
}
```

**全部**：去掉 assignee 与 status 过滤，仅 `deleted=0`。

> userName 默认取偏好配置（如 pengyaozong），可用 `--assignee` 覆盖。

### Step 3: 关联 fix-db（MR 链接）

对查询结果的**每个 issId**，关联本地修复数据库：

```bash
python <WF_ROOT>/fix-db.py query <issId>
```

关联规则：
- fix-db 有 `mr: !<n>` → 拼 MR 链接 `https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/<n>`
- `merge_status=merged` 或状态 merged → 标注 `已合入`
- `backport_mr` 有值 → 追加回流 MR 链接
- 无记录 → 该问题尚未登记（未开始处理）

### Step 4: 输出统一表格

```markdown
## 名下问题编排 (<范围> 共 N 条)

| issId | 标题 | 优先级 | 模块 | 状态 | fix MR | 处理进度 |
|-------|------|--------|------|------|--------|---------|
| ISS-xxx | <标题> | Critical | 相册 | In Progress | [!123](https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/123) | fixing |
| ISS-yyy | <标题> | Major | 设置 | OPEN | - | 未开始 |

说明：
- 待办列表只含未 fix 问题；已 fix（状态流转 Resolved/Closed）的问题不在待办，需用 `fix-db list` 或按 issId 查询。
```

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
