# 个人 AI 工作流

个人使用的 AI 辅助工作流集合，支持跨多个 harness（Claude Code、OpenCode、Kiro、Codex 等）。

## 工作流列表

### 1. IPD 问题修复工作流 (ipd-fix-workflow)
完整的 IPD 问题修复流程：从问题单获取信息 → 修复代码 → 编译验证 → 测试 → 提交 → 更新 IPD 状态。

触发：`/ipd-fix-workflow` 或 "修复 IPD 问题 ISS-xxx"

### 2. MR Review 工作流 (mr-review-workflow)
完整的 MR review 流程：代码审查 → 自动化测试 → 问题修复 → 生成 MR 描述 → 关联 IPD → 提交 MR。

触发：`/mr-review-workflow` 或 "准备提交 MR"

### 3. Git Cherry-Pick 工作流 (mr-pick-workflow)
按 MR 维度进行 cherry-pick，每个 MR 独立验证，最后子 agent 复核一致性。

触发：`/mr-pick-workflow` 或 "cherry-pick MR !123 !456"

## 安装

### 一键全局安装（推荐）

在**任意目录**运行安装脚本，自动扫描所有 AI Harness 并安装到全局目录：

```bash
cd ~  # 或任意目录
~/my-ai-workflows/install.sh
```

安装脚本会：
1. 自动扫描所有 AI Harness 的 skills 目录
2. 显示将要安装的工作流和目标目录
3. 用户确认后一次性安装到所有检测到的目录

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

# 2. 运行安装脚本
~/my-ai-workflows/install.sh
```

**完成！** 现在在任何项目中都可以使用这些工作流。

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
~/my-ai-workflows/install.sh
```

**完成！** 所有工作流立即在该机器的所有项目中可用。

### 更新工作流
```bash
cd ~/my-ai-workflows
git pull

# 符号链接自动生效，无需重新安装
# 如果有新增工作流，重新运行 install.sh
```

## 目录结构

```
~/my-ai-workflows/
├── README.md                    # 本文件
├── install.sh                   # 自动安装脚本
├── skills/
│   ├── ipd-fix-workflow/       # IPD 问题修复工作流
│   │   └── SKILL.md
│   ├── mr-review-workflow/     # MR review 工作流
│   │   └── SKILL.md
│   └── mr-pick-workflow/       # Cherry-pick 工作流
│       └── SKILL.md
└── .git/                       # Git 版本控制
```

## 依赖

这些工作流依赖以下项目 skills（通过符号链接访问项目 skills）：
- `osbot-review` - 代码审查
- `osbot-mr-preflight` - MR 预检
- `osbot-eval` - 测试用例执行
- `osbot-issue` - Issue 创建

以及 MCP 工具：
- `mi-adt` - IPD 问题追踪系统

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
- 重新运行 `~/my-ai-workflows/install.sh`

**问题：工作流调用项目 skill 失败**
- 确保在正确的项目目录（如 osbot）
- 检查项目 skills 是否存在

**问题：MCP 工具调用失败**
- 检查 MCP 配置：`~/.claude/mcp.json`
- 确保相关 MCP server 已启动
