# 个人 AI 工作流

个人使用的 AI 辅助工作流集合，支持跨多个 harness（Claude Code、OpenCode、Kiro、Codex 等），并配套 dsh (DeepSeek Harness) 插件。

## 工作流列表

### 1. 问题根因分析 (mai-analysis)
获取问题单 → 下载并全量分析日志 → 源码分析 → 日志↔源码闭环 → **收敛式单门禁核实**（根因定性 Agent 一次做全 → 单一门禁 Agent 核实全部维度 → 驳回则携反馈收敛重跑，默认 ≤2 轮）→ 上传根因结论到 IPD + 本地留档。

要点：Android logcat 强制全量分析、日志完备性前置门禁、结论收敛后复核、已有定性结论改由 LLM 判定。

触发：`/mai-analysis` 或 "分析 IPD 问题 ISS-xxx"

### 2. 问题修复工作流 (mai-fix-workflow)
基于 mai-analysis 的完整结论执行修复：结论门禁（双查）→ 修复方案评审 → TDD 用例集（mai-osbot-test 编排）→ 修复代码 → 编译 + 充分跑用例 → 独立复核 → 提交 → 更新 IPD 状态。

**强制前置**：必须由 mai-analysis 给出过完整结论，无结论拒绝开始。

触发：`/mai-fix-workflow` 或 "修复 IPD 问题 ISS-xxx"

### 3. 功能开发工作流 (mai-implement-workflow)
功能/新特性开发（非 bugfix）：需求确认门禁（目标/边界/验收标准/影响面）→ 方案评审 → TDD 用例集 → 实现 → 编译 + 充分跑用例 → 独立复核 → 提交 MR → 更新状态。**无需 mai-analysis 分析结论**。

触发：`/mai-implement-workflow` 或 "开发功能 X"

### 4. 问题统一编排 (mai-issue-schedule)
拉取名下 IPD 问题单（待办/未关闭/全部三种范围），按优先级/模块/状态维度过滤，关联 fix-db 输出 fix MR 链接与处理进度。查询由 `mai-issue-query.py` 直连 mi-adt API 完成（零 LLM 上下文），输出已内联 fix-db 进度。

触发：`/mai-issue-schedule` 或 "我还有哪些问题待处理" / "查 Critical 问题"

### 5. 测试缺口探测与执行编排 (mai-osbot-test)
双阶段工作：(1) **Analyze** - 分析 MR 变更、探测测试缺口、设计测试覆盖、独立复核完备性；(2) **Eval** - 统一执行测试清单、生成测试报告、更新 MR 评论。

触发：`/mai-osbot-test` 或 "测试这个 MR" / "验证修复"

### 6. 问题修复数据库 (mai-fix-db)
记录已 fix/正在 fix 的问题：IPD 单、分析结论、修复 MR、MR 合入状态。markdown 维护（每问题一文件 + 派生索引），支持多 session 并行写（写隔离 + flock 锁）。

```bash
python ~/my-ai-workflows/fix-db.py list [--days N] [--status X]   # 查询所有 / 最近 N 天修复进度
python ~/my-ai-workflows/fix-db.py query <issId>                  # 查单问题状态
python ~/my-ai-workflows/fix-db.py stats                          # 统计
python ~/my-ai-workflows/fix-db.py add <issId> --title "..."      # 登记（mai-analysis 自动）
python ~/my-ai-workflows/fix-db.py update <issId> -f key=val -t "说明" --status X  # 更新（自动追加时间线+重建索引）
```

状态机：`analyzing → conclusion_uploaded → fixing → mr_created → merged → closed`（feature 从 `implementing` 开始）。
`mai-analysis` / `mai-fix-workflow` 已内嵌自动读写。

### 7. MR Review 工作流 (mai-mr-review-workflow)
代码审查 → 多轮验证（review/测试/编译迭代）→ 关联 IPD → 生成 MR 描述 → 提交 MR → 更新 IPD。目录内含 **V2 双模式 + 6 层门禁架构** 版本（`SKILL-V2-GATED.md`：自己的 MR 走 CR 意见响应 + 独立复核；别人的 MR 走对抗性 review + 分级意见发表）。

触发：`/mai-mr-review-workflow` 或 "准备提交 MR"

### 8. Git Cherry-Pick 工作流 (mai-mr-pick-workflow)
按 MR 维度进行 cherry-pick，每个 MR 独立编译/测试验证，最后由子 agent 复核逻辑一致性。

触发：`/mai-mr-pick-workflow` 或 "cherry-pick MR !123 !456"

### 9. 运行时环境诊断 (mai-env-doctor)
深度诊断运行时依赖：mi-adt MCP 连通性实测、glab CLI、osbot 项目环境、项目 skills、符号链接，输出 ✅/⚠️/❌ 检查表并给出修复动作。

触发：`/mai-env-doctor` 或 "环境检查" / "环境诊断"

## 安装说明（给大模型，整段复制即用）

> 把下方代码块整个复制，粘贴给任意大模型（Claude/GPT/DeepSeek/本地 agent 等），
> 它会自动完成 clone → 检查 → 修复 → 安装 → 验证 → 上报。指令自包含，无需额外解释。
> 适用于新机器首次接入、或仓库更新后重新对齐环境。

````text
# 任务：安装 my-ai-workflows（个人 AI 工作流 + dsh 插件）
你是资深运维/开发助手。目标是在当前机器上完整安装本仓库的 AI 工作流 skills 与配套 dsh 插件，
逐项验证并上报结构化结果。只做本指令要求的事。

## 前置信息
- 仓库：my-ai-workflows（个人 AI 工作流集合），默认位置 ~/my-ai-workflows
- 布局：skills/ = 8 个工作流 skill；plugin/dsh/ = dsh 插件；setup.py = 跨平台安装脚本
- 目标 harness：Claude Code / Codex / OpenCode / 当前项目 / dsh (DeepSeek Harness)
- 环境变量：MY_AI_WORKFLOWS(仓库根) DSH_CLI(dsh 命令) DSH_SOURCE_DIR(dsh 源码目录) DSH_PROFILE(dsh profile, 默认 ipd) IPD_USER(IPD 用户名)

## 执行步骤

### 步骤 1：定位/克隆仓库
- 若 ~/my-ai-workflows/setup.py 已存在 → 直接使用该仓库
- 否则执行：git clone https://github.com/pengyz/my-ai-workflows.git ~/my-ai-workflows

### 步骤 2：环境检查
- 运行：cd ~/my-ai-workflows && python3 setup.py check
- 逐行记录检查表：mi-adt MCP 配置 / glab CLI / osbot 项目路径 / 项目 skills / skills 符号链接 / dsh CLI / dsh 插件

### 步骤 3：修复缺失项（仅处理检查表中 ❌/⚠️ 的项）
- glab 未安装/未认证：按 check 指引安装或提示用户执行 glab auth login
- mi-adt MCP 缺失：提示用户按指引配置（不得自行获取或编造凭据）
- dsh CLI ❌：按 check 提示在源码仓库执行 cd <harness>/apps/cli && pnpm link；或设 DSH_CLI
- 其余按 check 给出的修复指引处理；无法自动修复的明确列出，不猜测、不跳过
- 修复后重跑 setup.py check 确认该项转 ✅

### 步骤 4：安装
- 运行：cd ~/my-ai-workflows && python3 setup.py install
- 脚本有交互确认（skills 安装、dsh 插件安装各一次），一律输入 y；自动化环境可用 printf 'y\ny\n' | 管道
- 期望结果：skills 符号链接全部建立；dsh 插件构建成功并装入 profile（bundle 层自动挂载）

### 步骤 5：验证
- 重跑 setup.py check，确认必需项（mi-adt MCP、glab、osbot 路径）全 ✅，符号链接与 dsh 插件为 ✅
- 抽查符号链接：ls -la ~/.claude/skills/ | grep mai- 等（每个 harness 目录应有 8 个 mai-* 链接）
- 验证 dsh 插件已装入：python3 -c "import json;print(json.load(open('$HOME/.dsh/profiles/<profile>/package.json'))['dsh']['profile']['bundles'])"
- 可选冒烟（有网络时）：加载 plugin/dsh/dashboard-ipd 的 fetchBoard 渲染真实 IPD 看板，确认能出数据

### 步骤 6：上报
以如下格式输出最终报告（不得省略失败项）：

## 安装报告
| 项 | 状态 | 说明 |
|---|---|---|
| 仓库 | ✅/❌ | 路径与分支 |
| mi-adt MCP | ✅/❌ | 配置文件位置 |
| glab CLI | ✅/❌ | 认证状态 |
| osbot 路径 | ✅/❌ | 探测结果 |
| skills 符号链接 | ✅/❌ | 每 harness 链接数 |
| dsh CLI | ✅/❌ | PATH 或 DSH_CLI |
| dsh 插件 | ✅/❌ | bundle+已装入 profile |
| 遗留问题 | - | 未修复项 + 修复指引 |

## 硬性约束
- 禁止 git push / git commit（除非用户明确要求）
- 禁止修改仓库内任何文件（安装一律走 setup.py）
- 禁止删除或改写其他 harness 的既有配置（.claude.json、opencode 配置等）
- 每一步失败：报告命令与错误原文、你的修复尝试；修不动就如实上报，禁止编造成功结果
````

## 安装

### 一键全局安装（推荐）

在**任意目录**运行设置脚本，自动检查环境依赖并安装到所有 AI Harness：

```bash
cd ~  # 或任意目录
~/my-ai-workflows/setup.sh
```

设置脚本会：
1. **环境检查 (check)**：检查 glab CLI、mi-adt MCP 配置、osbot 项目路径、skills 符号链接、dsh CLI（含 `pnpm link` 指引）、dsh 插件状态，输出 ✅/⚠️/❌ 检查表
2. **安装 (install)**：自动扫描所有 AI Harness 的 skills 目录安装工作流，并构建 + 安装 `plugin/dsh/` 下的 dsh 插件

**子命令**：
- `setup.py check` - 仅环境检查（结果写入 `.env-status.json`，工作流运行时门禁依据）
- `setup.py install` - 安装：skills 符号链接 + dsh 插件（构建 + `dsh plugin add`）
- `setup.py uninstall` - 卸载：删除指向本仓库的符号链接 + `dsh plugin remove`

**跨平台**：核心逻辑为 Python 实现（`setup.py`，Python 3.9+），Linux/macOS 可用 `setup.sh` 便捷入口，Windows 直接运行 `python setup.py`。

**仓库根定位**：脚本使用自身位置定位仓库（支持任意 clone 位置）；也可通过环境变量 `MY_AI_WORKFLOWS` 指定仓库根。

**支持的 Harness**：
- ✅ Claude Code (`~/.claude/skills`)
- ✅ Codex (`~/.codex/skills`)
- ✅ OpenCode (`~/.config/opencode/skills`)
- ✅ 项目级（如果在项目中运行）
- ✅ dsh（`plugin/dsh/` 插件，装入 profile）

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
/mai-fix-workflow

# OpenCode
$mai-fix-workflow

# Codex
调用 mai-fix-workflow skill

# dsh（IPD 看板）
/ipd-board          # dsh --profile ipd 会话内
ipd_board           # 模型可调用的工具
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
# 如果有新增工作流或插件，重新运行 setup.sh
# dsh 插件为 file: 拷贝安装，源码变更后需重新 setup.py install 刷新
```

## 配套 dsh 插件 (`plugin/dsh/`)

工作流配套的 dsh (DeepSeek Harness) 插件，每个插件一个目录，未来可继续扩展。每个插件声明 `dsh.bundle`（自带 `cordis.patch.yml` 挂载行），`dsh plugin add` 自动将其加入 profile 的 bundles 层并应用挂载——**无需手写 profile 配置**。

**Harness 底座**：插件依赖 fork 的 dsh dev 分支
`https://github.com/pengyz/deepseek-harness`（branch `dev`）——该分支包含 out-of-repo
插件所需的最小 harness 补丁（如 `Session.append` 的 `ignorable` 选项）。本地开发/运行以此
fork 的 dev 分支为准，upstream 同步后按需 rebase。

| 插件 | 作用 |
|---|---|
| [`dashboard-ipd/`](plugin/dsh/dashboard-ipd/README.md) | 个人 IPD 问题单 + MR 状态看板: `/ipd-board` 命令 + `ipd_board` 工具 + `shell.overlay` 独立面板 |

`setup.py install` / `uninstall` 已集成 dsh 插件安装与卸载（构建 + `dsh plugin add/remove`）。`setup.py check` 会检查 `dsh` 是否在 PATH：

- **dsh 未在 PATH** → 提示在源码仓库执行 `cd <harness>/apps/cli && pnpm link`（自动探测 `DSH_SOURCE_DIR` 环境变量 > 当前目录 > `~/workspace/deepseek-harness` > git root）
- 也可用 `DSH_CLI` 环境变量直接指定 dsh 命令（源码运行时: 在 harness 仓库目录 `DSH_CLI='pnpm dsh'`）
- 目标 profile 通过 `DSH_PROFILE` 指定（默认 `ipd`）

手动安装:

```bash
cd ~/my-ai-workflows/plugin/dsh/dashboard-ipd && pnpm install && pnpm run build
pnpm dsh plugin --profile ipd add file:~/my-ai-workflows/plugin/dsh/dashboard-ipd
```

> dsh 插件必须用 `file:`（拷贝）安装：拷贝进 profile 后依赖经愈合 fallback 解析；`link:` 会导致 built 模式 `ERR_MODULE_NOT_FOUND`。源码变更后重新 `setup.py install`（内部 remove+add 强制刷新）。

## 目录结构

```
~/my-ai-workflows/
├── README.md                    # 本文件
├── setup.py                     # 跨平台设置脚本 (check/install/uninstall, Python 3.9+)
├── setup.sh                     # Unix 便捷入口 (exec python3 setup.py)
├── fix-db.py                    # 问题修复数据库命令
├── mai-issue-query.py           # 问题查询脚本(直连 mi-adt API, 零 LLM 上下文; --json 内联 fix-db)
├── wf_root.py                   # 共享 WF_ROOT 定位脚本(各 skill Step 0 统一调用)
├── fix-db/                      # 修复数据库数据 (每问题一 md + 派生 index.md)
├── tests/                       # 单元测试 (pytest)
├── .env-status.json             # 环境检查结果 (setup.py check 生成, 工作流门禁依据)
├── plugin/
│   └── dsh/                     # 配套 dsh 插件 (每插件一目录, 声明 dsh.bundle)
│       └── dashboard-ipd/       # IPD/MR 状态看板插件
├── skills/
│   ├── mai-analysis/            # IPD 根因分析 + 结论上传 (单门禁 G 收敛)
│   ├── mai-env-doctor/          # 运行时环境深度诊断 (MCP 连通性实测等)
│   ├── mai-fix-workflow/        # IPD 问题修复 (需先有 mai-analysis 完整结论)
│   ├── mai-implement-workflow/  # 功能开发工作流
│   ├── mai-issue-schedule/      # 问题统一编排
│   ├── mai-mr-pick-workflow/    # Cherry-pick 工作流
│   ├── mai-mr-review-workflow/  # MR review 工作流 (含 V2 双模式门禁版)
│   └── mai-osbot-test/          # 测试缺口探测与执行编排 (Analyze+Eval)
└── docs/                        # 辅助文档 (如 IPD 富文本格式)
```

### 工作流输出目录约定

各工作流在项目目录下产出审查/结论/报告文件，按功能分目录：

| 目录 | 用途 | 使用者 |
|------|------|--------|
| `.claude/ipd-conclusions/` | IPD 根因分析报告 + 结论 + 审查报告 | mai-analysis, mai-fix-workflow |
| `.claude/ipd-implementations/` | 功能开发方案 + 用例集 + 审查报告 | mai-implement-workflow |
| `.claude/reviews/` | 代码审查报告 | mai-mr-review-workflow |
| `.claude/picks/` | Cherry-pick 记录 | mai-mr-pick-workflow |

## 依赖

这些工作流依赖以下项目 skills（通过符号链接访问项目 skills）：
- `osbot-review` - 代码审查
- `osbot-mr-preflight` - MR 预检
- `osbot-eval` - 测试用例执行
- `osbot-trace-viz` - Trace 证据（可选）

以及 MCP 工具：
- `mi-adt` - IPD 问题追踪系统（`mai-issue-query.py` 直连其 HTTP API）

以及 CLI 工具：
- `glab` - GitLab API 操作
- `dsh` + `pnpm` - 配套 dsh 插件（构建与安装）

环境就绪性由 `setup.py check` 一次性检查（结果写入 `.env-status.json`）；运行时的 MCP 连通性等深度诊断由 `mai-env-doctor` skill 负责。

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
- 深度诊断（MCP 连通性实测等）：调用 `mai-env-doctor` skill

**问题：工作流调用项目 skill 失败**
- 确保在正确的项目目录（如 osbot）
- 检查项目 skills 是否存在

**问题：MCP 工具调用失败**
- 检查 MCP 配置：`~/.claude/mcp.json` 或 `~/.config/opencode/opencode.json`
- 确保相关 MCP server 已启动

**问题：dsh 插件未生效 / check 报 dsh CLI ❌**
- 按 check 提示在源码仓库执行 `cd <harness>/apps/cli && pnpm link`，或设置 `DSH_CLI` 环境变量
- 确认插件已装入 profile：`python3 -c "import json; print(json.load(open('$HOME/.dsh/profiles/<profile>/package.json'))['dsh']['profile']['bundles'])"`
- 插件改动后重启 dsh（link: 符号链接安装，源码变更即时生效但需重启加载）

**问题：Windows 下脚本无法运行**
- 确认已安装 Python 3.9+：`python --version`
- 使用 `python setup.py check/install/uninstall` 调用（不依赖 bash）
- 符号链接安装使用 junction（免管理员权限），自动处理
