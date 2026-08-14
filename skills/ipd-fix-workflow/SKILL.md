---
name: ipd-fix-workflow
description: IPD 问题修复完整工作流：获取问题信息 → 分析定位 → 修复代码 → 编译验证 → 测试 → 提交 → 更新 IPD 状态
---

# IPD 问题修复工作流

个人工作流，用于完整的 IPD 问题修复流程。

## 触发方式

- "修复 IPD 问题 ISS-xxx"
- "处理 IPD ISS-xxx"
- "/ipd-fix-workflow ISS-xxx"

## 工作流程

### Step 0: 环境门禁（轻量，不重复全量检查）

环境检查已由 `setup.py` 在安装时一次性完成。运行时只做轻量门禁：

1. 定位仓库根并读状态文件（环境变量 `MY_AI_WORKFLOWS` > 软链接反查 > 默认位置兜底）：

   **Linux/macOS (bash)**：
   ```bash
   WF_ROOT="${MY_AI_WORKFLOWS:-}"
   if [ -z "$WF_ROOT" ]; then
     for d in "$HOME/.config/opencode/skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$PWD/.agents/skills" "$PWD/.claude/skills"; do
       L="$(readlink -f "$d/ipd-fix-workflow" 2>/dev/null || true)"
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
       $item = Get-Item "$d\ipd-fix-workflow" -ErrorAction SilentlyContinue
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

**本工作流必需依赖**：`mi-adt` MCP（查询/更新问题单）、osbot 项目环境（编译）
**可选依赖**：`osbot-eval`（测试；不跑测试可跳过）

### Step 1: 获取 IPD 问题信息

使用 MCP `mi-adt` 工具获取问题详情：

```
调用 mcp__mi-adt__M_issueQuery，传入参数：
{
  "filters": [
    {"key": "issId", "operator": "EQ", "value": ["ISS-xxx"]}
  ],
  "pageInfo": {"pageNum": 1, "pageSize": 1}
}
```

提取关键信息：
- issueTitle: 问题标题
- issueDescription: 问题描述
- issuePriority: 严重等级
- issueStatus: 当前状态
- issueAssigneeId: 经办人
- exHandleAction: 研发模块
- issueTestComponent: 测试模块

展示给用户确认。

### Step 2: 下载并全量分析日志（基于日志定位根因的原则）

**原则 1：必须基于日志定位根因**
- 不能仅凭问题描述猜测
- 所有结论必须有日志证据支撑
- 日志证据必须包含：文件名、行号、时间戳、具体内容

**原则 2：日志全量分析，不只关注问题现象**
- 一份日志可能包含**多个问题**
- 问题之间可能有**因果关系**
- 全量分析能发现：
  - 问题的前置条件
  - 隐藏的根因
  - 其他潜在问题
  - 成功/失败的对比样本

**原则 3：日志与代码相互印证，闭合证据链**
- 日志 → 找到代码位置
- 代码 → 理解为什么产生这条日志
- 形成闭环：日志证据 → 代码逻辑 → 触发条件 → 根因结论

---

**2.1 下载附件**

从 `attachmentJson` 提取所有日志文件：
```bash
# 解析 attachmentJson
# 下载所有相关文件（bugreport、osbot logs、PC logs、截图等）
for fdsId in <提取的fdsId列表>; do
  curl -o "$filename" "https://cnbj1.fds.api.xiaomi.com/misc-plm/$fdsId"
done

# 解压到工作目录
unzip *.zip -d /tmp/logs/
```

**2.2 日志全量扫描（发现所有信息）**

**① 时间范围确认**：
- 确定日志的起止时间
- 确认是否覆盖问题发生时间段
- 如果不覆盖，标记出来

**② 关键事件提取**：

搜索所有可能相关的事件（不只是问题现象）：
```bash
# 用户交互
grep -r "query received\|user input\|session start" /tmp/logs/

# 系统状态变化
grep -r "network change\|login\|logout\|reconnect" /tmp/logs/

# 错误和异常
grep -r "error\|exception\|timeout\|failed\|crash" /tmp/logs/

# 性能指标
grep -r "duration\|elapsed\|latency" /tmp/logs/

# 业务逻辑
grep -r "tool call\|agent decision\|search\|transfer" /tmp/logs/
```

**③ 构建完整时间线**：

按时间顺序排列所有关键事件：
```
HH:MM:SS.mmm [Component] 事件描述 [file:line]
HH:MM:SS.mmm [Component] 事件描述 [file:line]
...
```

**④ 识别所有 session/query**：

- 统计日志中有**多少个 session**
- 每个 session 包含**多少个 query**
- 每个 query 的结果（成功/失败/超时/部分成功）

**⑤ 问题现象定位**：

在时间线中标记：
- 哪一个 session 是 QA 反馈的问题
- 问题的具体时间点
- 问题的表现（从日志看到的现象）

**⑥ 成功/失败样本对比**：

在同一份日志中寻找：
- 是否有成功的类似操作？
- 如果有，对比差异（参数、环境、时序）
- 如果没有，说明问题的必现性

**⑦ 异常模式识别**：

查找异常模式：
- 频繁的重试
- 异常的延迟
- 资源耗尽
- 状态不一致
- 消息丢失

**2.3 问题定界（多端日志交叉验证）**

**原则**：主责判断必须基于多端日志的交叉验证

**Android 端日志分析**：
- 路径：`/tmp/logs/osbot/` 或 bugreport 中的相关日志
- 检查点：
  - Agent 解析是否正确？
  - Tool 调用参数是否正确？
  - 网络请求是否发出？（带时间戳）
  - 响应是否收到？（带内容）
  - 异常处理是否触发？

**PC/Mac 端日志分析**：
- 代码路径：`../miclaw_desktop/`
- 日志路径：通常在附件中或需要单独获取
- 检查点：
  - 是否收到请求？（时间戳对齐）
  - 请求参数是否正确？
  - 处理逻辑是否执行？
  - 返回结果是什么？
  - 是否有错误日志？

**网络/中间层日志分析**：
- MiLink、MiTalk、网络层日志
- 检查点：
  - 连接状态
  - 消息传递
  - 超时配置
  - 重试机制

**定界方法**：

1. **请求发出但无响应** → 可能是网络或对端问题
2. **请求参数错误** → 发起端问题
3. **响应超时** → 需要看对端是否有日志
4. **响应错误** → 对端问题
5. **本地处理异常** → 本地问题

**定界结论模板**：
```
主责：[明确的端，不能模糊]

证据链：
1. Android 日志 [file:line] HH:MM:SS.mmm - 发出请求，参数：...
2. PC 日志 [file:line] HH:MM:SS.mmm - 未收到请求 / 收到但处理失败 / ...
3. 结论：主责在 [X端]，因为 [具体原因]

次责/协同问题（如有）：
- [端] - [问题描述] - [改进建议]
```

**2.4 根因定位（证据链闭合）**

**原则**：证据链必须闭合，不能有逻辑跳跃

**证据链结构**：
```
现象 → 直接原因 → 深层原因 → 根因
 ↓       ↓          ↓         ↓
日志A → 日志B+代码X → 日志C+代码Y → 设计缺陷/配置问题/...
```

**步骤**：

① **从现象出发**（日志中看到的最终表现）
```
现象：用户看到"正在调用工具"超过 5 分钟
日志证据：[file:line] HH:MM:SS - 显示"正在调用工具"
```

② **追溯直接原因**（什么导致这个现象）
```
直接原因：Tool 调用超时
日志证据：[file:line] HH:MM:SS - timeout after 300s
代码证据：ToolExecutor.kt:123 - DEFAULT_TIMEOUT = 300_000
```

③ **追溯深层原因**（为什么会超时）
```
深层原因：PC 端搜索耗时过长
PC 日志证据：[file:line] HH:MM:SS - 搜索耗时 350s
代码证据：SearchEngine.cpp:456 - 遍历算法复杂度 O(n)
```

④ **定位根因**（为什么设计/配置不合理）
```
根因：超时配置未考虑三方 PC 大文件量场景
设计问题：固定超时，无动态调整或增量返回机制
```

⑤ **验证闭合性**
- 每一步都有日志+代码双重证据
- 逻辑链条完整，无跳跃
- 能解释所有观察到的现象

**2.5 分析报告输出（结构化、可验证）**

生成完整的分析报告（作为后续评论的基础）：

```markdown
# IPD 根因分析报告

**问题单**: ISS-xxx
**日志时间范围**: YYYY-MM-DD HH:MM:SS ~ HH:MM:SS
**分析时间**: YYYY-MM-DD HH:MM:SS

## 1. 日志概览

- 日志文件：X 个（列出文件名和大小）
- 时间跨度：Y 分钟
- Session 总数：Z 个
- 问题 session：第 N 个

## 2. 全量事件时间线

[列出所有关键事件，不只是问题相关]

```
15:00:01.234 [Agent] Session start
15:00:05.456 [Network] MiLink connected
15:01:23.789 [Agent] Query 1: "xxx" - SUCCESS
15:02:45.012 [Agent] Query 2: "yyy" - TIMEOUT  ← 问题 query
15:03:10.345 [Network] MiLink reconnect
...
```

## 3. Session 统计与对比

| Session | Query | 结果 | 耗时 | 备注 |
|---------|-------|------|------|------|
| 1 | "查找文档" | 成功 | 2.3s | 正常 |
| 2 | "搜索压缩文件" | 超时 | 300s+ | **问题 query** |
| 3 | "发送文件" | 成功 | 1.5s | 正常 |

**成功与失败对比**：
- 成功的 query：参数/环境/时序的特点
- 失败的 query：差异点在哪里

## 4. 问题定界

**主责**: [明确的端]

**多端日志交叉验证**:
1. Android 端：
   - [file:line] HH:MM:SS - 发起请求
   - [file:line] HH:MM:SS - 等待超时
2. PC 端：
   - [file:line] HH:MM:SS - 收到请求
   - [file:line] HH:MM:SS - 搜索进行中
   - [file:line] HH:MM:SS - 搜索完成但未返回
3. 网络层：
   - [file:line] HH:MM:SS - 连接正常

**结论**：主责在 [X端]，因为 [具体原因]

## 5. 根因定位

**证据链**：
```
现象：用户看到超时
  ↓ [日志A] HH:MM:SS ...
直接原因：Tool 调用 300s 超时
  ↓ [代码X] ToolExecutor.kt:123 DEFAULT_TIMEOUT = 300_000
深层原因：PC 搜索耗时 > 300s
  ↓ [PC日志] HH:MM:SS 搜索 10000+ 文件
  ↓ [代码Y] SearchEngine.cpp:456 O(n) 遍历
根因：固定超时配置，未考虑大文件量场景
```

**证据链闭合性验证**: ✓
- 每一步都有日志+代码证据
- 逻辑完整，可解释所有现象

## 6. 其他发现

[在全量分析中发现的其他问题]

- 潜在问题 1：...
- 性能瓶颈：...
- 改进建议：...

## 7. 修复方案建议

[基于根因提出的修复方案]
```

与用户讨论分析结果，确认根因后进入修复阶段。

### Step 3: 制定修复方案

基于 Step 2 的根因分析，制定修复方案。

**3.1 方案设计原则**：
- 针对根因，不是症状
- 考虑边界情况
- 避免引入新问题
- 保持向后兼容

**3.2 方案评估**：

提出 2-3 个候选方案，对比分析：

| 方案 | 优点 | 缺点 | 风险 | 推荐度 |
|------|------|------|------|--------|
| 方案A | ... | ... | ... | ⭐⭐⭐ |
| 方案B | ... | ... | ... | ⭐⭐ |

**3.3 推荐方案**：

详细说明推荐方案：
- 修改内容：哪些文件、哪些逻辑
- 修改原因：为什么这样改能解决问题
- 影响范围：会影响哪些功能
- 测试计划：如何验证修复

与用户确认方案后，进入修复阶段。

### Step 4: 修复代码

根据确认的方案修复代码：
- 使用 Edit/Write 工具修改文件
- 遵循项目规范（资源使用、日志脱敏等）
- 添加必要的注释说明修复原因
- 如果是 PC/Mac 端问题，修改 `../miclaw_desktop/` 中的代码

**修复代码的要求**：
1. **增加日志埋点**：关键路径添加日志，方便后续排查
2. **错误处理**：添加异常捕获和降级逻辑
3. **参数校验**：增加边界检查
4. **性能考虑**：避免引入性能问题

### Step 5: 编译验证

使用项目标准编译命令（路径以 env-doctor Step 0 探测到的实际 osbot 路径为准）：

```bash
cd <env-doctor 探测到的 osbot 路径>
./scripts/package-ui.sh sidekick-ui
```

检查编译输出，如果失败：
- 查看错误信息
- 参考 `docs/03-开发指南/故障排除/编译错误.md`
- 修复后重新编译

### Step 5: 运行测试

根据问题类型选择测试策略：

**5.1 如果需要补充 eval case**（行为变更）：
```bash
# 创建或更新 eval case
# 文件路径：eval/cases/<category>/<issue-id>.yaml
```

**5.2 运行相关测试**：
```bash
# 调用 osbot-eval skill
/osbot-eval --filter "<相关测试pattern>"
```

**5.3 冒烟测试**（最小验证）：
```bash
/osbot-eval --smoke
```

记录测试结果，确保 passed。

### Step 6: 提交代码

遵循项目 commit 规范：

```bash
git add <修改的文件>
git commit -s -m "fix: <简短描述> (Issue ISS-xxx)"
```

Commit message 格式要求：
- 类型: `fix`（修复bug）、`feat`（新功能）等
- 无 scope 括号
- 必须包含 `-s` (Signed-off-by)
- 引用 Issue 编号

### Step 7: 更新 IPD 状态

使用 MCP `mi-adt` 更新问题状态和进展：

```
调用 mcp__mi-adt__M_updateSingleIssue，传入参数：
{
  "issId": "ISS-xxx",
  "dataMap": {
    "issueStatus": "Resolved",  # 或 "In Progress"
    "exNextPlan": "已修复，commit: <commit-hash>，待验证"
  }
}
```

**添加根因分析评论**：

```bash
# 构造 HTML 格式的评论内容
content=$(cat <<'EOF'
<p><b>【根因定谳 + 修复已提交】</b></p>
<p><b>结论</b>：<一句话根因结论></p>
<p><b>根因（实证）</b></p>
<p>日志证据：<br>
<code>HH:MM:SS.mmm Component: 关键日志</code><br>
<code>HH:MM:SS.mmm Component: 错误信息</code></p>
<p>代码证据：<br>
定位到 <code>File.kt:123</code><br>
逻辑说明</p>
<p><b>问题定界</b></p>
<p>主责：<b>Android/PC/MiLink</b><br>
依据：<br>
1. 日志证据<br>
2. 代码证据<br>
3. 对端日志</p>
<p><b>修复方案</b></p>
<p>1. 修复点1<br>
2. 修复点2</p>
<p><b>验证结果</b></p>
<p>✓ 编译通过<br>
✓ 测试通过</p>
<p>MR: <url><br>
Commit: <code><hash></code></p>
EOF
)

# 调用 MCP 添加评论
调用 mcp__mi-adt__M_saveComment，传入参数：
{
  "userName": "pengyaozong",
  "issId": "ISS-xxx",
  "content": "$content"
}
```

**格式要点**：
- `content` 字段传 HTML 字符串（不是 JSON 数组）
- `<p>...</p>` - 段落
- `<br>` - 段内换行
- `<b>...</b>` - 粗体
- `<code>...</code>` - 代码

详细格式见：`<WF_ROOT>/docs/ipd-rich-text-format.md`（WF_ROOT 见 Step 0 定位）
{
  "userName": "pengyaozong",
  "issId": "ISS-xxx",
  "content": "$content"
}
```

**格式要点**（关键！）：

1. **整个分析作为一个 text 节点**
   ```json
   [{"type": "text", "text": "<p>...</p><p>...</p>"}]
   ```
   不是：
   ```json
   [
     {"type": "text", "text": "<p>...</p>"},
     {"type": "hardBreak"},  // ❌ 错误
     {"type": "text", "text": "<p>...</p>"}
   ]
   ```

2. **使用 `<p>` 分段，`<br>` 换行**
   - `<p>...</p>` - 段落
   - `<br>` - 段落内换行
   - 不使用 `hardBreak` 节点

3. **HTML 标签**
   - `<b>标题</b>` - 粗体
   - `<code>代码</code>` - 代码片段
   - `<p>段落</p>` - 段落

4. **专业分析的标准结构**
   - 结论前置（一句话）
   - 根因实证（日志+代码）
   - 问题定界（明确主责）
   - 修复方案
   - 验证结果

详细格式说明见：`<WF_ROOT>/docs/ipd-rich-text-format.md`（WF_ROOT 见 Step 0 定位）

### Step 8: 生成修复报告

输出修复总结：

```markdown
# IPD 问题修复完成

**问题单**: ISS-xxx
**标题**: <标题>
**优先级**: <等级>

## 修复内容
- 定位模块：...
- 修改文件：...
- 修复逻辑：...

## 验证结果
- 编译: ✓ 通过
- 测试: ✓ xx/xx passed
- Eval case: ✓ 已补充/已通过

## 提交信息
- Commit: <hash>
- Branch: <branch>

## IPD 更新
- 状态: Resolved
- 进展: 已更新
```

## 错误处理

**环境启发规则**：任何依赖调用失败时，先判断是否环境问题（MCP 未配置/失效、路径不对）。是 → 提示修复指引 + 运行 `setup.py check` 定位（路径按 Step 0 定位结果），修复后重试一次；瞬时错误直接重试一次，不重复尝试第三次。

- **环境类错误（MCP/项目路径）**: 运行 `setup.py check` 获取检查表与修复指引；运行时深度诊断（如 MCP 连通性）可调用 `env-doctor` skill
- **IPD 查询失败**: 若为 MCP 环境问题按上条；否则确认问题编号正确，重试一次
- **编译失败**: 参考故障排除文档，修复后重新执行
- **测试失败**: 分析失败原因，修复后重新测试
- **提交失败**: 检查 commit hook，确保格式正确

## 个人偏好配置

可根据个人习惯调整：
- 编译命令（如果需要其他 build variant）
- 测试策略（全量测试 vs 冒烟测试）
- IPD 状态更新时机（修复后立即更新 vs 测试通过后更新）

## 依赖

- 环境: `setup.py` (Unix 便捷入口 setup.sh) - 一次性环境检查与安装（Step 0 门禁依据，仓库根定位见 Step 0）
- Skill: `env-doctor` - 运行时深度诊断（可选，出错时用）
- MCP: `mi-adt` - IPD 问题追踪系统
- 项目 skill: `osbot-eval` - 测试用例执行
- Git 配置: commit hook 已安装
