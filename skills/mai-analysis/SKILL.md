---
name: mai-analysis
description: |
  IPD 根因分析 + 结论上传。获取问题单 → 下载并全量分析日志 → 根因定位 →
  三道子 agent 独立审查门禁（A1 根因定性复核 / A2 日志信息利用率 / A3 IPD 评论核查）
  全部通过后上传根因结论到 IPD 评论 + 本地留档，产出供 mai-fix-workflow 使用的完整结论。
  触发词："分析 IPD 问题"、"根因分析"、"日志分析"、"定界"、"结论上传"、"分析 ISS-xxx"。
  注意：本 skill 只做分析定谳，修复由 mai-fix-workflow 负责（需先有本 skill 的完整结论）。
---

# IPD 根因分析 + 结论上传

分析问题单并给出**可被修复工作流直接使用的完整结论**。核心原则：

1. **必须基于日志定位根因**，所有结论有日志+代码证据支撑，不凭描述猜测
2. **日志全量分析**，不只关注问题现象：一份日志可能多个问题、多个根因
3. **关键结论必须经子 agent 独立审查**：三道门禁 A1/A2/A3，全部通过才可上传结论
4. 审查不过 → 打回重做对应阶段；用户可显式豁免（记录豁免原因）

## 触发方式

- "分析 IPD 问题 ISS-xxx"
- "根因分析 ISS-xxx"
- "/mai-analysis ISS-xxx"

## 前置

环境门禁（复用 `mai-env-doctor` / `setup.py`）：`mi-adt` MCP 可用（查询/评论）、osbot 项目路径可用（对照代码）。

## 工作流程

### Step 1: 获取 IPD 问题信息

调用 `mi-adt` `M_issueQuery`（filters: issId EQ），提取：issueTitle / issueDescription / issuePriority / issueStatus / issueAssigneeId / exHandleAction / issueTestComponent / attachmentJson。

同时拉取问题单**全部评论**（`M_pageOverallComment` / `M_getCommentList`）——供 Step 3 门禁 A3 核查。

**1.0 已有定性结论检查（LLM 判定，有则跳过分析）**：

阅读该单**全部信息**——issueDescription、全部评论、exReasonAnalysis、exNextPlan、rootCause、issueRootReason、changeId——由 **LLM 综合判定**是否已有**有效**的根因定性结论：

| 判定 | 依据 |
|------|------|
| ✅ 已有有效定性 | 明确根因 + 有证据/分析支撑 + **未被推翻**（无 QA 质疑/无重新打开/无反驳评论） |
| ❌ 无定性 | 无任何根因分析 |
| ❌ 定性无效 | QA 已推翻 / 评论质疑 / 被后续讨论否定 / 只有猜测无证据 / 结论存疑待定 |

> 注意：字段有值 ≠ 有效。用户不一定按规则更新（exReasonAnalysis 可能为空或模糊），且即使有根因，QA 可能已推翻——**必须 LLM 读评论判断"当前是否仍成立"**，不能机械匹配字段。

**判定 ✅ 已有有效定性 → 不分析**：
- 展示已有定性结论内容给用户
- 返回该单的 **IPD 链接**（`https://ipd.mioffice.cn/.../item/<id>`）供用户确认
- **跳过后续分析/审查/上传**，标记状态 `skip: 已有有效结论`
- 若用户仍要求重新分析（对结论存疑），才进入 Step 2

**判定 ❌（无定性 / 定性无效）→ 继续分析**，进入 Step 2。

**1.1 查询修复数据库状态**（定位 WF_ROOT 见环境门禁）：
```bash
python <WF_ROOT>/fix-db.py query <issId>
```
- 已有记录（analyzing/conclusion_uploaded/fixing/mr_created/merged）→ 展示历史状态,若已有结论则提示用户是否重复分析;若已 merged/closed 提示问题可能已修复
- 无记录 → 登记本次分析（拿到 issueTitle 后）：
  ```bash
  python <WF_ROOT>/fix-db.py add <issId> --title "<issueTitle>" --status analyzing
  ```

展示给用户确认。

### Step 2: 日志下载与全量分析

**2.1 下载附件**：从 `attachmentJson` 提取所有 fdsId，下载全部日志/截图到工作目录（`/tmp/ipd-<issId>/`），解压 zip。

**2.2 日志全量扫描**：

① **时间范围确认**：日志起止时间是否覆盖问题发生时段（不覆盖则标记并考虑补拉）
② **关键事件提取**：搜索所有相关事件（不只问题现象）——用户交互、系统状态变化、错误异常、性能指标、业务逻辑（tool call/agent decision/search/transfer）
③ **完整时间线**：按时间顺序排列所有关键事件 `HH:MM:SS.mmm [Component] 事件 [file:line]`
④ **Session/Query 统计**：多少个 session、每个 session 多少个 query、各自结果（成功/失败/超时）
⑤ **问题现象定位**：在时间线中标记 QA 反馈的问题点
⑥ **成功/失败样本对比**：同一份日志中是否有成功类似操作？对比差异
⑦ **异常模式识别**：频繁重试、异常延迟、资源耗尽、状态不一致、消息丢失

**2.3 问题定界（多端日志交叉验证）**：
- Android 端 / PC(Mac) 端 / 网络中间层逐端检查（请求发出？参数正确？响应收到？错误处理触发？）
- 定界结论模板：主责（明确的端）+ 多端证据链 + 次责/协同问题

**2.4 根因定位（证据链闭合）**：
- 证据链结构：现象 → 直接原因 → 深层原因 → 根因,每一跳都要 `日志证据 [file:line] + 代码证据 File.kt:123`
- 验证闭合性：每步双重证据、逻辑无跳跃、能解释所有观察到的现象

**2.5 分析报告输出**：
```markdown
# IPD 根因分析报告 (<issId>)
- 日志时间范围 / 分析时间
- 1. 日志概览（文件数/时间跨度/Session 数）
- 2. 全量事件时间线
- 3. Session 统计与成功/失败对比
- 4. 问题定界（主责 + 多端证据链）
- 5. 根因定位（证据链 + 闭合性验证）
- 6. 其他发现（潜在问题/性能瓶颈/改进建议）
- 7. 修复方案建议（针对根因）
```

### Step 3: 三道审查门禁（子 agent 独立复核）

> **机制**：每道门禁启动一个**独立子 agent**（无主 agent 上下文，仅给材料路径），按模板审查并产出落盘报告。主 agent 不参与判断。审查不过 → 主 agent 按报告修改对应阶段 → 重新提交审查；直到通过或用户豁免（豁免需记录原因）。

**门禁 A1 — 根因定性复核**

子 agent 审查材料：分析报告 + 日志目录 + 相关代码路径。检查：
- 证据链闭合度：现象→直接原因→深层原因→根因,每一跳是否有日志+代码双重证据、有无逻辑跳跃
- 根因对抗性审查：提出 ≥2 个替代根因假设,验证原根因能否排除它们
- 标记"证据不足却下结论"处

输出落盘 `.claude/ipd-conclusions/<issId>-review-A1.md`：逐项检查 + 替代假设列表 + 闭合度评分 + 结论（通过/打回+修改点清单）。

**门禁 A2 — 日志信息利用率审查**

子 agent 审查材料：日志目录 + 分析报告 + attachmentJson 清单。检查：
- 日志是否全量利用（是否漏掉其他 session/事件/成功样本）
- 一份日志分析出了几个问题？是否有多个独立根因？
- 信息不充分时：IPD 问题单是否还有其他日志附件未下载？是否需要补拉交叉验证？

输出落盘 `.claude/ipd-conclusions/<issId>-review-A2.md`：日志利用清单 + 问题数量清单 + 补拉建议 + 结论。

**门禁 A3 — IPD 评论核查**

子 agent 审查材料：问题单全部评论（Step 1 拉取）+ 分析报告。检查：
- 自己的评论、其他人的评论是否都参考过？关键信息（测试步骤/复现条件/历史分析尝试）是否纳入？
- 评论结论与本次分析的矛盾点是否已处理？

输出落盘 `.claude/ipd-conclusions/<issId>-review-A3.md`：评论核查清单（每条状态）+ 矛盾处理 + 结论。

### Step 4: 结论上传与留档

三门禁全过（或用户豁免并记录）后：

**4.1 本地留档** `.claude/ipd-conclusions/<issId>.md`：
```markdown
# IPD 分析结论 <issId>
- 结论（一句话根因定谳）
- 根因证据链（日志+代码 file:line）
- 问题定界（主责）
- 问题清单（本日志分析出的全部问题，可能多个根因）
- 修复方案建议
- 审查记录: A1 ✓(评分) / A2 ✓ / A3 ✓（或豁免原因）
- 关联文件: 分析报告 / 审查报告路径
```

**4.2 更新修复数据库**：
```bash
python <WF_ROOT>/fix-db.py update <issId> --status conclusion_uploaded -f conclusion="<一句话根因>" -t "根因定谳上传 IPD"
```

**4.3 上传根因评论到 IPD**（`M_saveComment`,HTML 格式）：
```
【根因定谳 + 分析结论】结论一句话 / 根因实证(日志+代码证据) / 问题定界(主责) /
问题清单(全部问题) / 修复方案建议 / 审查通过记录
```
HTML 格式要点：整个分析作为单个 text 节点、`<p>` 分段、`<br>` 换行、`<b>` 粗体、`<code>` 代码。

**4.4 告知用户**：结论已上传 + 本地留档路径 + 可进入 `mai-fix-workflow` 开始修复。

## 输出

- 结论文件: `.claude/ipd-conclusions/<issId>.md`
- 审查报告: `.claude/ipd-conclusions/<issId>-review-{A1,A2,A3}.md`
- IPD 根因评论已上传

## 与 mai-fix-workflow 的关系

`mai-fix-workflow`（修复）**强制要求**本 skill 的完整结论（IPD 评论 + 本地文件双查），无结论拒绝开始。因此本 skill 必须完成 Step 3 全部审查 + Step 4 上传留档。

## 错误处理

- **IPD 查询失败**: `setup.py check` / mai-env-doctor 定位 MCP 问题,重试一次
- **日志下载失败**: 检查 fdsId 有效性,逐个重试
- **审查打回**: 按审查报告修改后重新提交,不豁免则必须通过
- **上传失败**: 检查 M_ saveComment 参数（HTML 单 text 节点）,重试

## 依赖

- 环境: `mai-env-doctor` / `setup.py` - 环境门禁
- 数据库: `fix-db.py` - 修复数据库（Step 1 查询登记,Step 4 写结论）
- MCP: `mi-adt` - 查询/评论
- 子 agent: 三道审查门禁（独立复核）
- 本地目录: `.claude/ipd-conclusions/` - 结论与审查报告留档
