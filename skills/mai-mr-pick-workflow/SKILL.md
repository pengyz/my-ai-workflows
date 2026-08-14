---
name: mai-mr-pick-workflow
description: 按 MR 维度进行 cherry-pick 工作流：逐个 MR pick → 编译验证 → 测试 → 子 agent 独立复核一致性
---

# Git Cherry-Pick 工作流

个人工作流，用于按 MR 维度进行 cherry-pick，每个 MR 独立验证，最后由子 agent 复核逻辑一致性。

## 触发方式

- "cherry-pick MR !123 !456"
- "pick MRs !123 !456 到当前分支"
- "/mai-mr-pick-workflow !123 !456"
- "回流 MR !123 !456"

## 工作流程

### Step 0: 环境门禁（轻量，不重复全量检查）

环境检查已由 `setup.py` 在安装时一次性完成。运行时只做轻量门禁：

1. 定位仓库根并读状态文件（环境变量 `MY_AI_WORKFLOWS` > 软链接反查 > 默认位置兜底）：

   **Linux/macOS (bash)**：
   ```bash
   WF_ROOT="${MY_AI_WORKFLOWS:-}"
   if [ -z "$WF_ROOT" ]; then
     for d in "$HOME/.config/opencode/skills" "$HOME/.claude/skills" "$HOME/.codex/skills" "$PWD/.agents/skills" "$PWD/.claude/skills"; do
       L="$(readlink -f "$d/mai-mr-pick-workflow" 2>/dev/null || true)"
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
       $item = Get-Item "$d\mai-mr-pick-workflow" -ErrorAction SilentlyContinue
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

**本工作流必需依赖**：`glab` CLI（获取 MR 信息）、osbot 项目环境（编译验证）、`osbot-eval`（测试）

### Step 1: 解析 MR 列表

从用户输入中提取 MR 编号列表：
- 支持格式：`!123`、`!456`
- 支持多个 MR
- 去重并排序

展示待 pick 的 MR 列表，询问用户确认：

```
准备 cherry-pick 以下 MRs:
  !123 - <title>
  !456 - <title>

目标分支: <current-branch>
是否继续? [y/n]
```

### Step 2: 准备工作

**2.1 检查当前分支状态**：

```bash
# 确保工作区干净
git status --porcelain

# 获取当前分支名
CURRENT_BRANCH=$(git branch --show-current)

# 确认 base 分支
BASE_BRANCH="main"  # 或根据项目约定
```

如果工作区不干净，提示用户清理或暂存。

**2.2 创建记录文件**：

创建 pick 记录文件用于追踪：
```bash
PICK_LOG=".claude/picks/$(date +%Y%m%d-%H%M%S)-pick-log.md"
mkdir -p .claude/picks
```

### Step 3: 逐个 MR Cherry-Pick

对每个 MR 执行完整的 pick → 验证流程：

#### 3.1 获取 MR 信息

使用 `glab` 获取 MR 详情：

```bash
# 获取 MR 基本信息
glab mr view !123 --json title,description,author,sourceBranch,targetBranch,commits

# 提取 commits 列表
glab mr view !123 --json commits | jq -r '.[].sha'
```

记录到 PICK_LOG：
```markdown
## MR !123: <title>

- Author: <author>
- Source: <sourceBranch> → <targetBranch>
- Commits: <count>
```

#### 3.2 Cherry-Pick Commits

按顺序 pick MR 的所有 commits：

```bash
# 获取 MR 的 commits（按时间正序）
COMMITS=$(glab mr view !123 --json commits | jq -r '.[].sha' | tac)

# 逐个 pick
for commit in $COMMITS; do
    echo "Picking $commit"
    git cherry-pick "$commit"
    
    if [ $? -ne 0 ]; then
        echo "冲突发生，需要解决"
        # 记录冲突
        git status --porcelain | grep "^UU" > conflicts.txt
        break
    fi
done
```

**冲突处理**：

如果发生冲突：
1. 展示冲突文件列表
2. 读取冲突文件内容
3. 分析冲突原因
4. 提供解决建议或询问用户
5. 解决后继续：
   ```bash
   git add <resolved-files>
   git cherry-pick --continue
   ```

记录到 PICK_LOG：
```markdown
### Cherry-Pick 结果
- Status: ✓ 成功 / ⚠ 有冲突
- Conflicts: <file-list>
- Resolution: <说明>
```

#### 3.3 编译验证

每个 MR pick 完成后立即编译（路径以 setup.py check 探测到的 osbot 路径为准，见 Step 0 状态文件 `items.osbot_path`）：

```bash
cd <状态文件 items.osbot_path 对应的 osbot 路径>
./scripts/package-ui.sh sidekick-ui
```

记录编译结果：
```markdown
### 编译验证
- Status: ✓ 通过 / ✗ 失败
- Time: <duration>
- Errors: <如果失败，记录错误>
```

如果编译失败：
- 展示错误信息
- 参考 `docs/03-开发指南/故障排除/编译错误.md`
- 询问用户是否回滚此 MR 的 pick
- 如果回滚：`git reset --hard <pick-前的commit>`

#### 3.4 运行相关测试

根据 MR 的变更范围，运行相关测试：

```bash
# 分析 MR 的变更文件
CHANGED_FILES=$(glab mr view !123 --json changes | jq -r '.[].path')

# 判断测试范围
# 如果涉及 agent/tools/llm → 运行对应 eval cases
# 如果纯 UI → 可以跳过或只运行冒烟测试

# 运行测试
/osbot-eval --filter "<根据变更推断的pattern>"
```

记录测试结果：
```markdown
### 测试验证
- Strategy: <冒烟/全量/过滤>
- Results: <passed>/<total>
- Failed Cases: <list>
```

如果测试失败：
- 分析是否因为 pick 引入
- 如果是，询问用户是否继续或回滚

#### 3.5 记录 MR 完成

MR 验证通过后，记录到 PICK_LOG：

```markdown
### MR !123 Pick 完成 ✓

- Cherry-Pick: ✓ <commit-count> commits
- Conflicts: <count> resolved
- Compile: ✓ passed
- Tests: ✓ <passed>/<total>
- Picked Commits: <hash-list>

---
```

### Step 4: 所有 MRs Pick 完成总结

生成所有 MRs 的汇总：

```markdown
# Cherry-Pick 汇总

**目标分支**: <current-branch>
**Base**: <base-branch>
**MRs 总数**: <count>

## 成功 Pick 的 MRs

| MR | Title | Commits | Status |
|----|-------|---------|--------|
| !123 | ... | 3 | ✓ |
| !456 | ... | 2 | ✓ |

## 统计

- 总 Commits: <count>
- 冲突解决: <count>
- 编译验证: ✓ 全部通过
- 测试验证: ✓ <total-passed>/<total-cases>
```

### Step 5: 子 Agent 独立复核

**重要**：启动一个独立的子 agent 复核 pick 的一致性。

#### 5.1 启动子 Agent

```
使用 Agent 工具启动子 agent，传入任务：

"独立复核 cherry-pick 一致性。对比以下 MRs 的原始变更和当前分支的 picked commits，验证逻辑一致性。

MRs: !123, !456
当前分支: <current-branch>
Pick log: <PICK_LOG>

要求：
1. 对每个 MR，对比原始 diff 和 picked diff
2. 检查是否有遗漏的修改
3. 检查冲突解决是否正确保留了原意
4. 验证功能完整性（不只是代码一致性）
5. 输出详细的复核报告

不要依赖主 agent 的上下文，独立分析。"
```

#### 5.2 子 Agent 复核步骤

子 agent 应该执行：

**对每个 MR**：

1. 获取原始 MR 的 diff：
   ```bash
   glab mr diff !123 > /tmp/mr-123-original.diff
   ```

2. 获取当前分支对应 commits 的 diff：
   ```bash
   # 从 PICK_LOG 提取该 MR 的 picked commits
   git show <commit-hash> > /tmp/mr-123-picked.diff
   ```

3. 对比两个 diff：
   ```bash
   # 去除 commit hash、时间戳等元数据后对比
   diff -u /tmp/mr-123-original.diff /tmp/mr-123-picked.diff
   ```

4. 分析差异：
   - 纯上下文差异（因 base 不同）→ 正常
   - 冲突解决导致的差异 → 需要验证逻辑是否保留
   - 遗漏的修改 → 严重问题

5. 功能验证（如果可能）：
   - 读取相关代码
   - 理解原 MR 的意图
   - 验证 picked 代码是否实现相同功能

**生成复核报告**：

```markdown
# Cherry-Pick 一致性复核报告

**复核人**: Sub-Agent (独立)
**复核时间**: <timestamp>
**MRs**: !123, !456

## MR !123: <title>

### Diff 对比
- 原始 Commits: <count>
- Picked Commits: <count>
- Diff 差异: <summary>

### 一致性检查
- ✓ 核心逻辑一致
- ✓ 所有文件都已 pick
- ⚠ 冲突解决处需要验证: <file:line>
  - 原逻辑: ...
  - Picked 逻辑: ...
  - 评估: 功能等价/有差异

### 功能完整性
- ✓ 功能完整
- 说明: <分析>

## 总体结论

- ✓ 全部 MRs 逻辑一致
- ⚠ 需要人工验证: <list>
- ✗ 发现问题: <list>

## 建议

<如果有问题，给出修复建议>
```

#### 5.3 处理复核结果

等待子 agent 完成，获取复核报告：

- 如果 **全部 ✓**：继续 Step 6
- 如果 **有 ⚠**：展示给用户，询问是否需要人工确认
- 如果 **有 ✗**：展示问题，询问是否修复或回滚

将复核报告追加到 PICK_LOG。

### Step 6: 生成最终报告

输出完整的 pick 报告：

```markdown
# Cherry-Pick 工作流完成

**目标分支**: <current-branch>
**Pick 时间**: <timestamp>

## Pick 汇总

- 成功 MRs: <count>
- 总 Commits: <count>
- 冲突解决: <count>
- 编译验证: ✓
- 测试验证: ✓ <passed>/<total>

## 一致性复核

- 状态: ✓ 通过独立复核
- 复核报告: <PICK_LOG>

## 后续步骤

1. 人工验证关键变更（如有）
2. 运行完整回归测试（可选）
3. 提交当前分支
4. 创建回流 MR

## 详细日志

完整记录: <PICK_LOG>
```

### Step 7: 可选 - 创建回流 MR

询问用户是否立即创建回流 MR：

```
Pick 完成。是否创建回流 MR？
1) 是 - 立即创建
2) 否 - 稍后手动创建
```

如果选择创建：
```bash
# Push 当前分支
git push -u origin HEAD

# 创建 MR
glab mr create \
  --title "chore: 回流 MRs !123 !456" \
  --description "$(cat <生成的回流MR描述>)" \
  --label "backport" \
  --target-branch <target>
```

**回流 MR 创建后——回填修复数据库**（被 pick 的 MR 均来自 fix-db 产出，双向关联）：

对**每个被 pick 的源 MR**，反查 fix-db 关联的 IPD 单并回填回流 MR：

```bash
# 1. 反查源 MR 关联的 issId（WF_ROOT 定位见 Step 0）
python <WF_ROOT>/fix-db.py list --mr !123
# 2. 对每个命中的 issId 回填回流 MR
python <WF_ROOT>/fix-db.py update <issId> -f backport_mr=!<回流MR编号> -t "回流至 !<回流MR编号>"
```

> **多个 MR 统一提交场景**：一个回流 MR 关联多个源 MR（多个 IPD 单）→ 对每个源 MR 重复上述反查+回填，使回流 MR 反向关联所有被 pick 的 IPD 单（双向可查）。

MR 描述模板：
```markdown
# 回流 MRs

回流以下 MRs 到 <target-branch>:

- !123 - <title> (IPD: ISS-xxx)
- !456 - <title> (IPD: ISS-yyy)

## 验证结果

- 编译: ✓ 通过
- 测试: ✓ <passed>/<total>
- 一致性: ✓ 已通过子 agent 复核

## 详细日志

<PICK_LOG 链接或内容>
```

## 错误处理

**环境启发规则**：任何依赖调用失败时，先判断是否环境问题（glab 未认证、路径不对）。是 → 提示修复指引 + 运行 `setup.py check` 定位（路径按 Step 0 定位结果），修复后重试一次；瞬时错误直接重试一次，不重复尝试第三次。

- **环境类错误（CLI/项目路径）**: 运行 `setup.py check` 获取检查表与修复指引；运行时深度诊断可调用 `mai-env-doctor` skill
- **MR 不存在**: 检查 MR 编号，跳过该 MR
- **Cherry-pick 冲突**: 提供冲突分析和解决建议
- **编译失败**: 回滚该 MR，继续或停止
- **测试失败**: 分析原因，决定继续或回滚
- **子 agent 复核失败**: 展示问题，等待用户决策

## 个人偏好配置

可根据个人习惯调整：
- 是否每个 MR 都运行测试（vs 只在最后统一测试）
- 编译失败时的处理策略（立即停止 vs 继续）
- 是否自动创建回流 MR
- 子 agent 复核的详细程度

## 依赖

- 环境: `setup.py` - 一次性环境检查与安装（Step 0 门禁依据，仓库根定位见 Step 0）
- Skill: `mai-env-doctor` - 运行时深度诊断（可选，出错时用）
- 数据库: `fix-db.py` - 回流 MR 与 IPD 单双向关联（Step 7 回填 backport_mr）
- CLI: `glab` - GitLab API 操作
- 项目 skill: `osbot-eval` - 测试用例执行
- 子 agent: 独立复核一致性（通过 Agent 工具）
- Git: cherry-pick 操作

## 注意事项

1. **子 agent 必须独立**：不依赖主 agent 的上下文，独立分析
2. **逻辑一致性 > 代码一致性**：冲突解决后代码可能不同，但功能要等价
3. **记录完整**：所有决策和结果都记录到 PICK_LOG
4. **可中断恢复**：如果中途失败，可以基于 PICK_LOG 恢复
