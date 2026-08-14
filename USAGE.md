# 使用指南

## 快速开始

### 1. 首次安装

```bash
# 克隆仓库
cd ~
git clone https://github.com/<你的用户名>/my-ai-workflows.git

# 在项目中安装
cd /path/to/your/project
~/my-ai-workflows/setup.sh
```

**Windows (PowerShell)**：不依赖 bash，直接调用 Python 版：

```powershell
cd $HOME\my-ai-workflows
python setup.py check   # 环境检查
python setup.py install # 安装 (junction 软链, 免管理员)
```

**卸载**：`python setup.py uninstall` 或 `~/my-ai-workflows/setup.sh uninstall`（只删除指向本仓库的链接，真实目录不受影响）

### 2. 验证安装

```bash
# 检查符号链接
ls -la .agents/skills/ | grep -E "(env-doctor|ipd-fix|mr-review|mr-pick)"

# 或
ls -la .claude/skills/ | grep -E "(env-doctor|ipd-fix|mr-review|mr-pick)"
```

应该看到四个符号链接指向 `~/my-ai-workflows/skills/`。

### 3. 环境检查（一次性）

`setup.py` 默认会先做环境检查再安装。之后想单独检查或刷新状态文件：

```bash
# Linux/macOS
~/my-ai-workflows/setup.sh check
# Windows
python $HOME\my-ai-workflows\setup.py check
```

检查 glab CLI、mi-adt MCP 配置、osbot 项目路径等，输出 ✅/⚠️/❌ 检查表。
工作流运行时依赖失败时，也会提示运行此命令定位问题。

## 使用方法

### 场景 1：修复 IPD 问题

**触发方式**：
- "修复 IPD 问题 ISS-202608-00051339A"
- "/ipd-fix-workflow ISS-202608-00051339A"

**工作流程**：
1. AI 从 IPD 获取问题信息并展示
2. 分析问题，定位相关代码
3. 与你讨论修复方案
4. 修复代码
5. 自动编译验证（`./scripts/package-ui.sh sidekick-ui`）
6. 运行测试（根据需要补 eval case）
7. 提交代码（符合 commit 规范）
8. 更新 IPD 状态为 "Resolved"

**示例对话**：
```
你: 修复 IPD 问题 ISS-202608-00051339A

AI: [获取问题信息]
问题标题: XXX崩溃
问题描述: ...
优先级: Critical
当前状态: OPEN

让我分析相关代码...
[分析定位]
找到可能的问题点在 src/xxx/yyy.kt:123

修复方案：...
是否同意这个方案？

你: 同意

AI: [修复代码 → 编译 → 测试 → 提交 → 更新 IPD]
✓ 修复完成
Commit: abc123
IPD 状态已更新为 Resolved
```

### 场景 2：准备提交 MR

**触发方式**：
- "准备提交 MR"
- "/mr-review-workflow"
- "review 完成后提交 MR"

**工作流程**：
1. AI 运行代码审查（osbot-review）
2. 如果有问题，展示并询问是否修复
3. 分析变更范围，判断是否需要 trace 证据和 eval case
4. 检查或运行测试（eval）
5. 询问是否关联 IPD 问题
6. 生成标准 MR 描述
7. 最后编译验证
8. 创建 MR
9. 如果关联了 IPD，更新 IPD 状态

**示例对话**：
```
你: 准备提交 MR

AI: 开始代码审查...
[运行 osbot-review]
发现 2 个 findings:
1. [Medium] src/xxx.kt:45 - 资源使用规范问题
2. [Low] src/yyy.kt:78 - 日志可以优化

是否立即修复？

你: 修复第一个，第二个忽略

AI: [修复代码 → 重新审查]
✓ 审查通过

分析变更范围...
检测到修改了 agent/ 目录，需要 trace 证据。
是否运行 /osbot-trace-viz？

你: 跳过，稍后手动添加

AI: 检查最近的 eval 结果...
找到最近的 eval: 25/25 passed
使用此结果。

是否关联 IPD 问题？

你: 是，ISS-202608-00051339A

AI: [获取 IPD 信息 → 生成 MR 描述 → 编译 → 创建 MR → 更新 IPD]
✓ MR 已创建: !5678
✓ IPD 已更新为 Resolved，进展：已提交 MR !5678
```

### 场景 3：Cherry-Pick MRs

**触发方式**：
- "cherry-pick MR !123 !456"
- "/mr-pick-workflow !123 !456"
- "回流 MR !123 !456"

**工作流程**：
1. 解析 MR 列表，展示确认
2. 检查当前分支状态
3. 逐个 MR pick：
   - 获取 MR 的 commits
   - Cherry-pick
   - 处理冲突（如果有）
   - 编译验证
   - 运行相关测试
4. **所有 MR pick 完成后，启动子 agent 独立复核**
5. 子 agent 对比原始 diff 和 picked diff，验证逻辑一致性
6. 生成完整报告
7. 询问是否创建回流 MR

**示例对话**：
```
你: cherry-pick MR !5432 !5445 到当前分支

AI: 准备 cherry-pick 以下 MRs:
  !5432 - fix: 修复 xxx 问题
  !5445 - feat: 新增 yyy 功能

目标分支: feature/backport-v2
是否继续？

你: 继续

AI: === MR !5432 ===
获取 commits: 3 个
Cherry-picking commit abc123...
Cherry-picking commit def456...
Cherry-picking commit ghi789...
✓ Pick 完成

编译验证...
✓ 编译通过

运行测试...
✓ 测试通过 (12/12)

=== MR !5445 ===
获取 commits: 2 个
Cherry-picking commit jkl012...
⚠ 冲突发生在 src/xxx.kt

冲突文件:
- src/xxx.kt

[展示冲突内容和分析]
建议保留 HEAD 的 xxx 部分...

你: 同意

AI: [解决冲突]
Cherry-picking commit mno345...
✓ Pick 完成
✓ 编译通过
✓ 测试通过 (8/8)

=== 所有 MRs Pick 完成 ===
启动子 agent 独立复核一致性...

[子 agent 独立分析]
- 对比原始 MR diff 和 picked diff
- 验证逻辑一致性
- 检查功能完整性

子 agent 复核结果:
✓ MR !5432: 逻辑一致
✓ MR !5445: 逻辑一致，冲突解决正确

✓ 所有 MRs 复核通过

是否创建回流 MR？

你: 是

AI: [创建回流 MR]
✓ MR 已创建: !5678
```

## 在不同 Harness 中使用

### Claude Code / Kiro
```bash
/ipd-fix-workflow ISS-xxx
/mr-review-workflow
/mr-pick-workflow !123 !456
```

### OpenCode
```bash
$ipd-fix-workflow ISS-xxx
$mr-review-workflow
$mr-pick-workflow !123 !456
```

### Codex
直接说：
```
调用 ipd-fix-workflow 修复 ISS-xxx
使用 mr-review-workflow 准备提交 MR
运行 mr-pick-workflow cherry-pick !123 !456
```

## 多环境同步

### 场景：在办公室和家里的电脑使用

**办公室电脑（首次设置）**：
```bash
cd ~/my-ai-workflows
git remote add origin https://github.com/<你的用户名>/my-ai-workflows.git
git push -u origin main
```

**家里电脑（同步）**：
```bash
cd ~
git clone https://github.com/<你的用户名>/my-ai-workflows.git

# 在各个项目中安装
cd ~/project1
~/my-ai-workflows/setup.sh

cd ~/project2
~/my-ai-workflows/setup.sh
```

**更新工作流**：
```bash
# 办公室修改后
cd ~/my-ai-workflows
git add -A
git commit -s -m "feat: 优化 IPD 工作流的测试策略"
git push

# 家里同步
cd ~/my-ai-workflows
git pull
# 所有项目的符号链接自动生效
```

## 个性化定制

### 修改工作流

编辑对应的 SKILL.md 文件：

```bash
cd ~/my-ai-workflows/skills/ipd-fix-workflow
vim SKILL.md

# 例如：调整默认测试策略
# 从冒烟测试改为全量测试
```

修改后提交：
```bash
cd ~/my-ai-workflows
git add -A
git commit -s -m "chore: 调整 IPD 工作流默认测试策略"
git push
```

所有环境自动生效（通过符号链接）。

### 添加新工作流

```bash
cd ~/my-ai-workflows/skills
mkdir my-new-workflow
vim my-new-workflow/SKILL.md

# 编辑 setup.sh，添加到 WORKFLOWS 数组
vim ~/my-ai-workflows/setup.sh

# 提交
cd ~/my-ai-workflows
git add -A
git commit -s -m "feat: 添加新工作流 my-new-workflow"
git push

# 重新安装
cd /path/to/project
~/my-ai-workflows/setup.sh
```

## 故障排查

### 问题：调用工作流时提示找不到

**检查符号链接**：
```bash
ls -la .agents/skills/ipd-fix-workflow
# 或
ls -la .claude/skills/ipd-fix-workflow
```

**重新安装**：
```bash
~/my-ai-workflows/setup.sh
```

### 问题：工作流调用项目 skill 失败

**确认在正确的项目目录**：
```bash
pwd  # 应该在 /home/peng/workspace/osbot 或其他项目根目录
```

**检查项目 skills 是否存在**：
```bash
ls .agents/skills/osbot-review
ls .agents/skills/osbot-eval
```

### 问题：MCP 工具调用失败

**检查 MCP 配置**：
```bash
cat ~/.claude/mcp.json | grep mi-adt
```

**确认 MCP server 已启动**（如果适用）

### 问题：Git 操作失败

**检查 glab 配置**：
```bash
glab auth status
```

**重新登录**：
```bash
glab auth login
```

## 进阶技巧

### 1. 在工作流中插入断点

编辑 SKILL.md，在任何步骤后添加：
```markdown
**暂停点**：展示当前状态，等待用户确认是否继续。
```

### 2. 跳过某些步骤

在对话中明确告诉 AI：
```
你: /mr-review-workflow，跳过代码审查，直接运行测试
```

### 3. 组合使用工作流

```
你: 先用 ipd-fix-workflow 修复 ISS-xxx，完成后自动用 mr-review-workflow 提交 MR
```

### 4. 查看工作流内容

```bash
cat ~/my-ai-workflows/skills/ipd-fix-workflow/SKILL.md
```

了解工作流的详细步骤和可配置项。

## 最佳实践

### 1. 定期同步

每周或每月从 GitHub 拉取最新版本：
```bash
cd ~/my-ai-workflows
git pull
```

### 2. 备份自定义配置

如果你对工作流做了个性化修改，确保提交到 git。

### 3. 在新项目中使用

每次开始新项目，运行一次安装脚本：
```bash
cd /path/to/new/project
~/my-ai-workflows/setup.sh
```

### 4. 团队分享（可选）

如果团队成员也想使用，他们可以：
```bash
git clone https://github.com/<你的用户名>/my-ai-workflows.git ~/my-ai-workflows
```

但建议每人 fork 一份，自己定制。

## 更多帮助

- **查看 README**：`cat ~/my-ai-workflows/README.md`
- **查看设计文档**：`cat ~/workspace/osbot/docs/superpowers/specs/2026-08-14-personal-ai-workflows-design.md`
- **查看具体工作流**：`cat ~/my-ai-workflows/skills/<workflow-name>/SKILL.md`
