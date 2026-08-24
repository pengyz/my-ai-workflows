---
name: mai-env-doctor
description: |
  my-ai-workflows 运行时环境深度诊断。检查 mi-adt MCP 连通性（setup.py 无法覆盖的项）、
  glab CLI、osbot 项目环境、项目 skills、符号链接，输出 ✅/⚠️/❌ 检查表并给出修复动作。
  工作流运行时依赖调用失败时用它定位，也可单独触发。安装期环境检查请用 setup.py check。
  触发词："环境检查"、"检查环境"、"doctor"、"环境诊断"、"环境自检"。
---

# 环境诊断 (mai-env-doctor)

**安装期检查**：一次性环境检查与安装请运行 `setup.py check`（Python 跨平台实现，含状态文件写入）。
**本 skill 定位**：运行时深度诊断——尤其覆盖 setup.py 做不到的项（MCP 连通性实测），以及工作流运行中依赖调用失败时的定位。工作流不强制每次调用本 skill。

## 调用时机

- 工作流运行时某依赖调用失败（MCP 报错、glab 报错、编译路径不对）→ 用本 skill 定位根因
- 用户主动要求诊断："环境检查"、"doctor"
- 仓库根定位：`python3 wf_root.py`（环境变量 `MY_AI_WORKFLOWS` > 软链接反查 > `$HOME/my-ai-workflows` 兜底，与工作流 Step 0 相同）

## 执行流程

按 A→E 顺序逐项检查，收集结果，最后输出统一检查表。

### A. MCP 工具：mi-adt（IPD 问题库）— 连通性实测

setup.py 只能查配置文件存在性，**连通性必须由本项实测**。

**检查方法**：
1. 查看当前会话可用工具列表，是否包含 `mi-adt` 相关工具（如 `M_issueQuery` / `M_issueQueryByViewKey`）。工具名前缀因 harness 而异：
   - Claude Code：`mcp__mi-adt__M_issueQuery`
   - OpenCode：`mi-adt_M_issueQuery`
2. 若工具存在，做一次连通性探测：调用 `M_issueQuery`，`pageInfo={pageNum:1, pageSize:1}`，不带 filters。返回（含 0 条）= 连通；报错 = 断开。

**判定**：
- 工具不存在 → ❌ 必需缺失
- 工具存在但探测报错 → ❌ 配置错误（token/URL 失效）

**修复指引**：
1. 工具不存在 → 加载 `ipd-mcp-setup` skill（osbot 项目 `.agents/skills/ipd-mcp-setup`），或参考文档 https://mi.feishu.cn/wiki/WOJEw38DaicBlVknasjccb7nnDc
2. 配置位置（按当前 harness）：
   - Claude Code：`~/.claude.json` 的 `mcpServers.mi-adt`
   - OpenCode：`~/.config/opencode/opencode.json` 的 `mcp."mi-adt"`
   - 其他 harness：查对应 MCP 配置文件
3. token 失效时重新申请：https://ipd.mioffice.cn/generate-mcp-token
4. 修改配置后需重启 harness 会话，再重新运行本检查；修复完成后建议重跑 `setup.py check` 刷新状态文件

### B. CLI 工具：glab（GitLab）

**检查方法**：

**Linux/macOS (bash)**：
```bash
which glab            # 是否存在
glab auth status      # 是否已认证
```

**Windows (PowerShell)**：
```powershell
Get-Command glab -ErrorAction SilentlyContinue   # 是否存在
glab auth status                                   # 是否已认证
```

**判定**：
- 命令不存在 → ❌ 未安装
- `glab auth status` 失败或显示未认证 → ❌ 未认证

**修复指引**：

```bash
# 未安装（macOS）
brew install glab
# Windows
winget install GitLab.GLab
# 其他平台：https://gitlab.com/gitlab-org/cli#installation

# 未认证（交互式登录）
glab auth login
# 或使用已有 token
glab auth login --token <GITLAB_TOKEN>
```

修复后重跑 `setup.py check` 刷新状态文件。

### C. 项目环境（osbot 仓库）

**检查方法**：

**Linux/macOS (bash)**：
```bash
# 1. 当前是否在 git 仓库
git rev-parse --is-inside-work-tree 2>/dev/null

# 2. 当前仓库是否为 osbot（remote 或目录名）
git remote get-url origin 2>/dev/null
basename "$PWD"

# 3. 常见 osbot 工作路径探测（处理目录改名漂移，如 osbot → osbot-new3）
for p in "$PWD" /home/peng/workspace/osbot /home/peng/workspace/osbot-new3; do
  [ -d "$p" ] && echo "found: $p"
done
```

**Windows (PowerShell)**：
```powershell
# 1. 当前是否在 git 仓库
git rev-parse --is-inside-work-tree 2>$null

# 2. 当前仓库是否为 osbot（remote 或目录名）
git remote get-url origin 2>$null
Split-Path -Leaf $PWD

# 3. 常见 osbot 工作路径探测（或用 OSBOT_PATH 环境变量）
foreach ($p in @($PWD, "$HOME\workspace\osbot", "$HOME\workspace\osbot-new3")) {
  if (Test-Path $p) { "found: $p" }
}
```

**判定**：
- 不在 git 仓库，或 remote 不匹配 osbot → ⚠️ 警告（工作流需在 osbot 仓库内执行）
- 所有探测路径都不存在 → ⚠️ 无法定位编译路径

**修复指引**：
- 切换到 osbot 仓库目录后重新运行工作流
- 确认实际路径后，可用 `OSBOT_PATH` 环境变量固定，供 setup.py 探测使用

### D. 项目 skills（osbot-eval / osbot-review / osbot-mr-preflight / osbot-trace-viz）

**检查方法**：

**Linux/macOS (bash)**：
```bash
for skill in osbot-eval osbot-review osbot-mr-preflight osbot-trace-viz; do
  ls .agents/skills/$skill/SKILL.md 2>/dev/null \
    || ls .claude/skills/$skill/SKILL.md 2>/dev/null \
    || ls /home/peng/workspace/osbot*/.agents/skills/$skill/SKILL.md 2>/dev/null \
    || echo "missing: $skill"
done
```

**Windows (PowerShell)**：
```powershell
foreach ($skill in @("osbot-eval", "osbot-review", "osbot-mr-preflight", "osbot-trace-viz")) {
  $found = Get-ChildItem ".agents\skills\$skill\SKILL.md", ".claude\skills\$skill\SKILL.md" -ErrorAction SilentlyContinue
  if (-not $found) { "missing: $skill" }
}
```

**判定**：对应 skill 文件缺失 → ⚠️（该工作流调用 `/osbot-xxx` 时会失败）

**修复指引**：在 osbot 仓库目录内运行工作流（项目 skills 随仓库存在）；不要用全局 setup.py install 覆盖项目级 skills

### E. 工作流安装状态（可选）

**检查方法**：

**Linux/macOS (bash)**：
```bash
readlink -f ~/.config/opencode/skills/ipd-fix-workflow 2>/dev/null
readlink -f ~/.claude/skills/ipd-fix-workflow 2>/dev/null
# 期望输出指向 <仓库根>/skills/ipd-fix-workflow
```

**Windows (PowerShell)**：
```powershell
(Get-Item "$HOME\.config\opencode\skills\ipd-fix-workflow" -ErrorAction SilentlyContinue).Target
(Get-Item "$HOME\.claude\skills\ipd-fix-workflow" -ErrorAction SilentlyContinue).Target
# 期望输出指向 <仓库根>\skills\ipd-fix-workflow
```

**判定**：不是软链接/junction，或指向非 my-ai-workflows → ⚠️ 版本可能过期/不是本仓库

**修复指引**：重新运行 `setup.py install`（仓库根定位方式见"调用时机"）

## 输出格式

检查完成后输出统一检查表：

```
## 环境诊断结果

| # | 依赖 | 类型 | 状态 | 说明 / 修复动作 |
|---|------|------|------|----------------|
| A | mi-adt MCP (IPD) | 必需/可选 | ✅/⚠️/❌ | ... |
| B | glab CLI | 必需/可选 | ✅/⚠️/❌ | ... |
| C | osbot 项目环境 | 必需 | ✅/⚠️ | 实际路径: ... |
| D | 项目 skills | 按需 | ✅/⚠️ | ... |
| E | 工作流安装 | 可选 | ✅/⚠️ | ... |

结论：
- 全部 ✅ → 就绪，可继续
- 存在 ❌ → 先执行修复动作；全部转为 ✅（或用户明确确认降级）后才继续
- 仅 ⚠️ → 可继续，但按说明降级（如 mi-adt 可选时跳过 IPD 关联步骤）
```

## 分级规则

| 状态 | 含义 | 处理 |
|------|------|------|
| ✅ | 可用 | 继续 |
| ⚠️ | 缺失但可降级 | 继续，跳过对应可选步骤并在记录中说明 |
| ❌ | 必需项缺失 | 停止，执行修复指引；修复后重跑本检查 |

## 与 setup.py / 工作流的配合

| 工具/工作流 | 使用时机 | 必需检查项 | 可选检查项 |
|------------|---------|-----------|-----------|
| setup.py check | 安装期一次性 | 全部 A-E（bash 版，不含 MCP 连通性实测） | - |
| mai-env-doctor | 运行时出错时 | A（含连通性实测）、B、C、D | E |
| ipd-fix-workflow | 出错时引用 | A、C | D（osbot-eval，不跑测试可跳过） |
| mai-mr-review-workflow | 出错时引用 | B、C、D | A（mi-adt，不关联 IPD 可跳过） |
| mai-mr-pick-workflow | 出错时引用 | B、C、D（osbot-eval） | - |

## 依赖

- MCP: `mi-adt` - IPD 问题库连通性测试
- CLI: `glab` - GitLab API 操作
- 项目: osbot 仓库 - 项目环境检查
- Skills: `osbot-eval` / `osbot-review` / `osbot-mr-preflight` / `osbot-trace-viz` - 项目级 skill 检查
- 脚本: `wf_root.py` - 工作流根目录定位
