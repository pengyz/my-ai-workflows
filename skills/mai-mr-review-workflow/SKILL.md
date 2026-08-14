---
name: mai-mr-review-workflow
description: 完整的 MR review 工作流：代码审查 → 多轮验证 → 自动化测试 → 问题修复 → 关联 IPD → 生成 MR 描述 → 提交
---

# MR Review 工作流

个人工作流，用于完整的 MR review 和提交流程，包括多轮验证和 IPD 关联。

## 触发方式

- "准备提交 MR"
- "完成 MR review"
- "/mai-mr-review-workflow"
- "review 完成后提交 MR"

## 工作流程

### Step 0: 环境门禁（轻量，不重复全量检查）

环境检查已由 `setup.py` 在安装时一次性完成。运行时只做轻量门禁：

1. 定位仓库根并读状态文件（环境变量 `MY_AI_WORKFLOWS` > 软链接反查 > 默认位置兜底）：

   **Linux/macOS (bash)**：
   ```bash
   WF_ROOT="${MY_AI_WORKFLOWS:-}"
   if [ -z "$WF_ROOT" ]; then
     for d in "$HOME/.config/opencode/skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$PWD/.agents/skills" "$PWD/.claude/skills"; do
       L="$(readlink -f "$d/mai-mr-review-workflow" 2>/dev/null || true)"
       if [ -n "$L" ] && [ -f "$L/SKILL.md" ]; then
         WF_ROOT="$(cd "$(dirname "$L")/.." && pwd)"
         break
       fi
     done
   fi
   WF_ROOT="${WF_ROOT:-$HOME/my-ai-workflows}"
   cat "$WF_ROOT/.env-status.json" 2>/dev/null || echo "MISSING"
   ```

   **Windows (PowerShell)**：
   ```powershell
   $WF_ROOT = $env:MY_AI_WORKFLOWS
   if (-not $WF_ROOT) {
     foreach ($d in @("$HOME\.config\opencode\skills", "$HOME\.claude\skills", "$HOME\.codex\skills", "$PWD\.agents\skills", "$PWD\.claude\skills")) {
       $item = Get-Item "$d\mai-mr-review-workflow" -ErrorAction SilentlyContinue
       if ($item -and $item.Target) {
         $WF_ROOT = Split-Path (Split-Path $item.Target)
         break
       }
     }
   }
   if (-not $WF_ROOT) { $WF_ROOT = "$HOME\my-ai-workflows" }
   if (Test-Path "$WF_ROOT\.env-status.json") { Get-Content "$WF_ROOT\.env-status.json" } else { "MISSING" }
   ```
2. 判定（不做任何工具探测）：
   - `required_ok=true` 且 `checked_at` 未超过 `ttl_days` → 直接继续 Step 1
   - 文件不存在 / `required_ok=false` / 已过期 → 提示用户：`请先运行 <WF_ROOT>/setup.py check (Unix 也可用 <WF_ROOT>/setup.sh check) 完成一次性环境配置`，用户确认后继续
3. 运行中任何依赖调用失败 → 按"错误处理"章节启发式处理：报错 + 修复指引 + 提示 setup.py，不现场做全量检查

**本工作流必需依赖**：`glab` CLI（创建 MR）、osbot 项目环境、项目 skills（`osbot-review` / `osbot-eval` / `osbot-mr-preflight`）
**可选依赖**：`mi-adt` MCP（不关联 IPD 可跳过）、`osbot-trace-viz`（无 trace 门禁可跳过）

### Step 1: 代码审查

调用项目的代码审查 skill：

```
/osbot-review
```

等待审查完成，获取审查报告：
- 路径：`.claude/reviews/<yymmdd>-review-<target>/REPORT.md`
- 检查 findings 数量和严重程度
- 记录需要修复的问题

如果有 findings：
- 展示给用户
- 询问是否立即修复
- 修复后重新运行审查

### Step 2: 分析变更范围和门禁要求

获取当前分支的变更：

```bash
# 获取变更文件列表
git diff --name-only origin/main...HEAD

# 获取 commit 列表
git log origin/main..HEAD --oneline --no-merges

# 获取 diff 统计
git diff origin/main...HEAD --stat
```

**判断 Trace 门禁**：

变更命中以下路径需要 trace 证据：
- `**/agent/**`
- `**/tools/**`
- `**/llm/**`
- `**/assets/agents/**`
- `**/assets/prompts/**`
- `**/assets/tool_overlays.json`

如果命中，提示用户：
```
需要 Trace 证据。请运行 /osbot-trace-viz 获取 trace，
或稍后在 MR 描述中手动添加。
```

**判断 Eval Case 门禁**：

以下情况必须补 case：
- 修复了 Agent 行为类问题
- 新增用户意图支持
- 修改工具选择/路由/consent/fallback 规则

分析 commit message 和变更内容，判断并告知用户。

### Step 3: 自动化测试执行

**3.1 检查最近的 eval 结果**：

```bash
# 获取最后一次 commit 的时间
LAST_COMMIT_TIME=$(git log -1 --format=%ci HEAD)

# 查找该时间之后的 eval 结果
ls -dt eval/results/*/eval-summary.json 2>/dev/null | head -1
```

如果找到最近的 eval 结果（在最后一次 commit 之后）：
- 直接使用该结果
- 提取 total/passed/failed 统计

**3.2 如果没有最近结果，询问用户**：

```
没有找到最近的 eval 结果，请选择：
1) 运行冒烟测试（快速，5-10分钟）
2) 运行全量测试（完整，30-60分钟）
3) 按 pattern 过滤测试（指定范围）
4) 跳过测试（需要说明原因）
```

根据用户选择：
```bash
# 选项 1: 冒烟测试
/osbot-eval --smoke

# 选项 2: 全量测试
/osbot-eval

# 选项 3: 按 pattern
/osbot-eval --filter "<pattern>"
```

记录测试结果。

**3.3 测试失败处理**：

如果有失败的 case：
- 展示失败的 case 列表
- 分析失败原因（是否因本次修改引入）
- 询问用户是否需要修复

修复后重新运行测试。

### Step 4: 关联 IPD（如果适用）

询问用户是否关联 IPD 问题：

```
此 MR 是否关联 IPD 问题？
1) 是 - 输入 Issue 编号
2) 否 - 跳过
```

**如果关联 IPD**：

获取 IPD 问题信息：
```
调用 mcp__mi-adt__M_issueQuery，传入参数：
{
  "filters": [
    {"key": "issId", "operator": "EQ", "value": ["ISS-xxx"]}
  ],
  "pageInfo": {"pageNum": 1, "pageSize": 1}
}
```

验证问题状态和指派人，确认是否合适关联。

### Step 5: 生成 MR 描述

调用项目的 MR preflight skill：

```
/osbot-mr-preflight
```

该 skill 会生成符合规范的 MR 描述，包括：
- 改动摘要
- 改动详情
- Self-Eval 结果（包含 Step 3 的测试结果）
- Trace 证据（如果有）

**如果关联了 IPD**，在生成的描述中添加：

```markdown
## 关联 Issue

Closes ISS-xxx

**问题标题**: <标题>
**问题描述**: <简短说明>
```

### Step 6: 编译验证

最后一次完整编译验证（路径以 mai-env-doctor Step 0 探测到的实际 osbot 路径为准）：

```bash
cd <mai-env-doctor 探测到的 osbot 路径>
./scripts/package-ui.sh sidekick-ui
```

确保编译通过。

### Step 7: 创建 MR

使用 `glab` CLI 创建 MR：

```bash
# 确保当前分支已 push
git push -u origin HEAD

# 创建 MR
glab mr create \
  --title "<type>: <简短描述>" \
  --description "<Step 5 生成的完整描述>" \
  --label "<根据类型设置>" \
  --assignee "@me" \
  --target-branch main
```

MR 标题格式：
- `fix: ...` - Bug 修复
- `feat: ...` - 新功能
- `refactor: ...` - 重构
- `perf: ...` - 性能优化

获取 MR URL 并展示。

### Step 8: 更新 IPD（如果关联）

如果 Step 4 关联了 IPD，更新问题状态：

```
调用 mcp__mi-adt__M_updateSingleIssue，传入参数：
{
  "issId": "ISS-xxx",
  "dataMap": {
    "issueStatus": "Resolved",
    "exNextPlan": "已提交 MR !<mr-number>，待 review"
  }
}
```

**添加富文本评论关联 MR**：

```bash
# 构造富文本内容
content=$(jq -nc --arg mr_url "$MR_URL" --arg mr_num "$MR_NUM" --arg passed "$PASSED" --arg total "$TOTAL" '[
  {"type":"text","text":"<b>【MR 已提交】</b>"},
  {"type":"hardBreak"},
  {"type":"text","text":("MR: " + $mr_url)},
  {"type":"hardBreak"},
  {"type":"hardBreak"},
  {"type":"text","text":"<b>Self-Eval 结果</b>"},
  {"type":"hardBreak"},
  {"type":"text","text":"✓ Code Review: 通过"},
  {"type":"hardBreak"},
  {"type":"text","text":("✓ 测试: " + $passed + "/" + $total + " passed")},
  {"type":"hardBreak"},
  {"type":"text","text":"✓ 编译: 通过"}
]')

# 调用 MCP
调用 mcp__mi-adt__M_saveComment，传入参数：
{
  "userName": "pengyaozong",
  "issId": "ISS-xxx",
  "content": "$content"
}
```

富文本格式详见：`<WF_ROOT>/docs/ipd-rich-text-format.md`（WF_ROOT 见 Step 0 定位）

### Step 9: 生成完成报告

输出 MR 提交总结：

```markdown
# MR 已创建

**MR**: <MR-URL>
**标题**: <title>
**分支**: <branch> → main

## Review 结果
- Code Review: ✓ <findings 数量>
- 编译验证: ✓ 通过
- 测试结果: ✓ <passed>/<total>
- Trace 证据: ✓/✗

## 关联 Issue
- IPD: ISS-xxx ✓ 已更新

## 后续步骤
1. 等待 Code Review
2. 根据 review 意见修改
3. Merge 后验证
```

## 多轮验证逻辑

工作流支持多轮迭代：

1. **Code Review 有问题** → 修复 → 重新 review
2. **测试失败** → 修复 → 重新测试
3. **编译失败** → 修复 → 重新编译

每轮迭代都会记录，最终报告包含所有轮次信息。

## 个人偏好配置

可根据个人习惯调整：
- 默认测试策略（冒烟 vs 全量）
- 是否自动关联 IPD
- MR label 选择
- 是否需要 assignee 和 reviewer

## 错误处理

**环境启发规则**：任何依赖调用失败时，先判断是否环境问题（glab 未认证、MCP 未配置、路径不对）。是 → 提示修复指引 + 运行 `setup.py check` 定位（路径按 Step 0 定位结果），修复后重试一次；瞬时错误直接重试一次，不重复尝试第三次。

- **环境类错误（CLI/MCP/项目路径）**: 运行 `setup.py check` 获取检查表与修复指引；运行时深度诊断（如 MCP 连通性）可调用 `mai-env-doctor` skill
- **Code Review 失败**: 检查变更范围，确保规则文件存在
- **测试失败**: 分析失败原因，区分新引入 vs 已存在问题
- **MR 创建失败**: 若为 glab 环境问题按上条（`glab auth status` 验证）；否则检查 token 权限，重试一次
- **IPD 更新失败**: 若为 MCP 环境问题按上条；否则确认问题编号和权限

## 依赖

- 环境: `setup.py` (Unix 便捷入口 setup.sh) - 一次性环境检查与安装（Step 0 门禁依据，仓库根定位见 Step 0）
- Skill: `mai-env-doctor` - 运行时深度诊断（可选，出错时用）
- 项目 skill: `osbot-review` - 代码审查
- 项目 skill: `osbot-mr-preflight` - MR 描述生成
- 项目 skill: `osbot-eval` - 测试用例执行
- 项目 skill: `osbot-trace-viz` - Trace 证据（可选）
- MCP: `mi-adt` - IPD 问题追踪系统（可选）
- CLI: `glab` - GitLab MR 创建
