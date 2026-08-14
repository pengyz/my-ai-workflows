# 个人 AI 工作流

个人使用的 AI 辅助工作流集合，支持跨多个 harness（Claude Code、OpenCode、Kiro、Codex 等）。

## 工作流列表

### 1. IPD 根因分析 (ipd-analysis)
获取问题单 → 日志全量分析 → 根因定位 → 三道子 agent 独立审查门禁（根因定性复核 / 日志信息利用率 / IPD 评论核查）→ 上传根因结论到 IPD + 本地留档。

触发：`/ipd-analysis` 或 "分析 IPD 问题 ISS-xxx"

### 2. IPD 问题修复工作流 (ipd-fix-workflow)
基于 ipd-analysis 的完整结论执行修复：结论门禁（双查）→ 修复方案评审 → TDD 用例集（osbot-test 编排）→ 修复代码 → 编译 + 充分跑用例 → 独立复核 → 提交 → 更新 IPD 状态。

**强制前置**：必须由 ipd-analysis 给出过完整结论，无结论拒绝开始。

触发：`/ipd-fix-workflow` 或 "修复 IPD 问题 ISS-xxx"

### 3. MR Review 工作流 (mr-review-workflow)
完整的 MR review 流程：代码审查 → 自动化测试 → 问题修复 → 生成 MR 描述 → 关联 IPD → 提交 MR。

触发：`/mr-review-workflow` 或 "准备提交 MR"

### 3. Git Cherry-Pick 工作流 (mr-pick-workflow)
按 MR 维度进行 cherry-pick，每个 MR 独立验证，最后子 agent 复核一致性。

触发：`/mr-pick-workflow` 或 "cherry-pick MR !123 !456"

## 安装

### 一键全局安装（推荐）

在**任意目录**运行设置脚本，自动检查环境依赖并安装到所有 AI Harness：

```bash
cd ~  # 或任意目录
~/my-ai-workflows/setup.sh
```

设置脚本会：
1. **环境检查 (check)**：检查 glab CLI、mi-adt MCP 配置、osbot 项目路径、符号链接状态，输出 ✅/⚠️/❌ 检查表
2. **安装 (install)**：自动扫描所有 AI Harness 的 skills 目录，显示将安装的工作流，确认后安装

**子命令**：
- `setup.py check` - 仅环境检查（结果写入 `.env-status.json`，工作流运行时门禁依据）
- `setup.py install` - 仅安装符号链接（Unix: symlink；Windows: junction，免管理员权限）
- `setup.py uninstall` - 卸载：删除指向本仓库的符号链接（真实目录不受影响）

**跨平台**：核心逻辑为 Python 实现（`setup.py`，Python 3.9+），Linux/macOS 可用 `setup.sh` 便捷入口，Windows 直接运行 `python setup.py`。

**仓库根定位**：脚本使用自身位置定位仓库（支持任意 clone 位置）；也可通过环境变量 `MY_AI_WORKFLOWS` 指定仓库根。

**支持的 Harness**：
- ✅ Claude Code (`~/.claude/skills`)
- ✅ Codex (`~/.codex/skills`)
- ✅ OpenCode (`~/.config/opencode/skills`)
- ✅ 项目级（如果在项目中运行）

**安装后效果**：一次安装，所有项目可用！

### 首次设置

```bash
# 1. 克隆仓库到 home 目录
cd ~
git clone https://github.com/pengyz/my-ai-workflows.git

# 2. 运行设置脚本（检查环境 + 安装）
# Linux/macOS
~/my-ai-workflows/setup.sh
# Windows (PowerShell)
python $HOME\my-ai-workflows\setup.py
```

**完成！** 现在在任何项目中都可以使用这些工作流。

> 环境检查只需安装时做一次。工作流运行时只做轻量门禁（读 `.env-status.json`）；
> 依赖调用失败时会提示运行 `setup.py check` 定位并修复。

### 手动安装（可选）

如果需要手动创建符号链接：

```bash
# 全局安装（推荐）
ln -s ~/my-ai-workflows/skills/* ~/.claude/skills/
ln -s ~/my-ai-workflows/skills/* ~/.codex/skills/
ln -s ~/my-ai-workflows/skills/* ~/.config/opencode/skills/

# 或项目级安装
cd /path/to/your/project
ln -s ~/my-ai-workflows/skills/* .agents/skills/
ln -s ~/my-ai-workflows/skills/* .claude/skills/
```

## 使用

安装后，在任何支持的 harness 中直接调用：

```bash
# Claude Code / Kiro
/ipd-fix-workflow

# OpenCode
$ipd-fix-workflow

# Codex
调用 ipd-fix-workflow skill
```

## 跨环境同步

### 首次设置（在一台机器上）
```bash
cd ~/my-ai-workflows
git remote add origin https://github.com/your-username/my-ai-workflows.git
git push -u origin main
```

### 在其他机器同步
```bash
# 1. 克隆仓库
cd ~
git clone https://github.com/your-username/my-ai-workflows.git

# 2. 运行安装脚本（自动安装到所有 harness）
~/my-ai-workflows/setup.sh
```

**完成！** 所有工作流立即在该机器的所有项目中可用。

### 更新工作流
```bash
cd ~/my-ai-workflows
git pull

# 符号链接自动生效，无需重新安装
# 如果有新增工作流，重新运行 setup.sh
```

## 目录结构

```
~/my-ai-workflows/
├── README.md                    # 本文件
├── setup.py                     # 跨平台设置脚本 (check/install/uninstall, Python 3.9+)
├── setup.sh                     # Unix 便捷入口 (exec python3 setup.py)
├── .env-status.json             # 环境检查结果 (setup.py check 生成, 工作流门禁依据)
├── skills/
│   ├── env-doctor/             # 运行时环境深度诊断 (MCP 连通性实测等)
│   ├── ipd-analysis/           # IPD 根因分析 + 结论上传 (三道审查门禁)
│   ├── ipd-fix-workflow/       # IPD 问题修复 (需先有 ipd-analysis 完整结论)
│   ├── mr-review-workflow/     # MR review 工作流
│   ├── mr-pick-workflow/       # Cherry-pick 工作流
│   ├── osbot-test/             # OSBot 统一测试编排 (场景路由)
│   └── .git/                   # Git 版本控制
```

## 依赖

这些工作流依赖以下项目 skills（通过符号链接访问项目 skills）：
- `osbot-review` - 代码审查
- `osbot-mr-preflight` - MR 预检
- `osbot-eval` - 测试用例执行
- `osbot-issue` - Issue 创建

以及 MCP 工具：
- `mi-adt` - IPD 问题追踪系统

以及 CLI 工具：
- `glab` - GitLab API 操作

环境就绪性由 `setup.sh check` 一次性检查（结果写入 `.env-status.json`）；运行时的 MCP 连通性等深度诊断由 `env-doctor` skill 负责。

## 自定义

每个工作流的 `SKILL.md` 可以根据个人习惯调整：
- 修改验证标准
- 调整执行顺序
- 添加个人偏好的检查项
- 自定义输出格式

修改后提交到 git 即可在所有环境生效。

## 故障排查

**问题：调用工作流时提示找不到**
- 检查符号链接：`ls -la .agents/skills/` 或 `ls -la .claude/skills/`
- 重新运行 `setup.py install`（Unix 也可用 `~/my-ai-workflows/setup.sh install`）

**问题：工作流运行时依赖调用失败（MCP/glab/路径）**
- 运行 `setup.py check` 获取检查表和修复指引
- 深度诊断（MCP 连通性实测等）：调用 `env-doctor` skill

**问题：工作流调用项目 skill 失败**
- 确保在正确的项目目录（如 osbot）
- 检查项目 skills 是否存在

**问题：MCP 工具调用失败**
- 检查 MCP 配置：`~/.claude/mcp.json` 或 `~/.config/opencode/opencode.json`
- 确保相关 MCP server 已启动

**问题：Windows 下脚本无法运行**
- 确认已安装 Python 3.9+：`python --version`
- 使用 `python setup.py check/install/uninstall` 调用（不依赖 bash）
- 符号链接安装使用 junction（免管理员权限），自动处理
