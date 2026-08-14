---
name: ipd-fix-workflow
description: |
  IPD 问题修复工作流：读取根因结论 → 修复方案评审 → TDD 用例集 → 修复代码 →
  编译验证 + 充分跑用例 → 独立复核 → 提交 → 更新 IPD 状态。
  **强制前置**：必须由 ipd-analysis 给出过完整结论（IPD 评论根因 + 本地结论文件双查），
  无结论拒绝开始。触发词："修复 IPD 问题"、"修复 ISS-xxx"、"处理 ISS-xxx"。
---

# IPD 问题修复工作流

基于 `ipd-analysis` 的完整结论执行修复。**不重新分析根因**——结论是前置门禁，缺失即拒绝。

核心原则：
1. **结论门禁**：IPD 评论 + 本地结论文件双查，缺一不可
2. **TDD 先行**：修复前先定用例集合（osbot-test 编排），红→绿
3. **关键决策前子 agent 独立复核**：方案评审、完成复核
4. **充分验证**：相关用例 100% PASS + 冒烟，才可提交

## 触发方式

- "修复 IPD 问题 ISS-xxx"
- "/ipd-fix-workflow ISS-xxx"

## 前置

环境门禁（复用 `env-doctor` / `setup.py`）：`mi-adt` MCP、osbot 项目环境、`osbot-eval`（测试）。

---

## Step 0: 结论门禁（必须，不通过即拒绝）

双查该问题是否已有完整分析结论：

**0.1 查 IPD 评论**：调用 `mi-adt` `M_pageOverallComment` / `M_getCommentList`（issId），检查是否存在 `ipd-analysis` 上传的**根因分析评论**（内容含"根因定谳"标记）。

**0.2 查本地结论文件**：`.claude/ipd-conclusions/<issId>.md` 是否存在且完整（含结论/证据链/问题定界/问题清单/修复方案建议 + 审查记录）。

**判定**：
- 两者都有 → 继续 Step 1
- IPD 评论有、本地缺 → 从 IPD 评论重建本地结论文件（提示用户确认），继续
- 任一缺失 → **拒绝开始**：`该问题尚无完整分析结论，请先运行 ipd-analysis <issId> 完成根因分析与结论上传`

## Step 1: 读取结论

从 `.claude/ipd-conclusions/<issId>.md`（或 IPD 评论）提取：
- 一句话根因结论
- 根因证据链（日志+代码 file:line）
- 问题清单（可能多个根因）
- 修复方案建议

展示给用户确认。

## Step 2: 制定修复方案 + 门禁 F1 方案评审

**2.1 制定方案**（针对根因，不是症状）：
- 提出 2-3 个候选方案对比（优点/缺点/风险/推荐度）
- 推荐方案：修改内容 / 修改原因 / 影响范围 / 测试计划

**2.2 门禁 F1 — 方案评审（子 agent 独立复核）**：
启动独立子 agent（无主 agent 上下文，给结论文件 + 方案），检查：
- 方案与结论一致性：是否针对根因而非症状
- 覆盖度：是否覆盖结论问题清单里的全部问题（多根因场景）
- 回归风险：影响范围分析

输出落盘 `.claude/ipd-conclusions/<issId>-review-F1.md`。不过 → 修改方案重审；用户可豁免（记录原因）。

**与用户确认方案后**进入 Step 3。

## Step 3: TDD 用例集（修复前必做，门禁 F2）

**修复前先定测试用例集合**，用 `osbot-test` 编排测试方案：

**3.1 确定用例范围**（基于方案的影响面）：
- 行为类变更 → 新增/更新 `eval/cases/` YAML case（`validate_cases.py` schema 校验通过）
- CLI 命令逻辑 → 关联 `scripts/tests/*-test.mjs`
- 回归范围 → 相关 suite（`--set`）+ 冒烟（`--smoke`）

**3.2 用 osbot-test 编排**：调用 `osbot-test` skill 按场景路由（单端 eval / JS CLI / 冒烟 / 双端按需），明确：
- 用例清单（case-id 或 pattern）
- 执行顺序（先跑新增用例红→绿，再跑回归）
- 通过标准（新增用例 + 相关回归 100% PASS）

**3.3 输出用例集清单**到 `.claude/ipd-conclusions/<issId>-tdd-cases.md`（用例列表 + 通过标准 + 测试方案）。

**确认用例集后**才进入 Step 4 写代码。

## Step 4: 修复代码

按方案修复：
- 遵循项目规范（资源使用、日志脱敏、错误处理、参数校验、性能考虑）
- 关键路径添加日志埋点
- 注释说明修复原因

## Step 5: 编译验证 + 跑用例集

**5.1 编译**（路径以 env-doctor 探测的 osbot 路径为准）：
```bash
cd <env-doctor 探测到的 osbot 路径>
./scripts/package-ui.sh sidekick-ui
```
失败 → 修复后重新编译。

**5.2 跑 TDD 用例集**（按 Step 3 编排，经 osbot-test）：
- 新增用例 → 通过（红→绿完成）
- 相关回归 → 100% PASS
- 冒烟 → 100% PASS

记录结果。

## Step 6: 门禁 F3 — 修复完成独立复核（子 agent）

启动独立子 agent（给结论文件 + 修复 diff + 用例结果），检查：
- 修复与结论一致性：是否修了根因而非症状
- 用例覆盖：TDD 用例是否全跑、是否有未覆盖场景
- 代码质量：是否引入新问题（回归风险）

输出落盘 `.claude/ipd-conclusions/<issId>-review-F3.md`。不过 → 修复后重审；用户可豁免（记录原因）。

## Step 7: 提交代码

```bash
git add <修改的文件>
git commit -s -m "fix: <简短描述> (Issue ISS-xxx)"
```
遵循 commit 规范：类型 fix/feat、无 scope 括号、`-s`、引用 Issue。

## Step 8: 更新 IPD 状态 + 上传修复评论

**8.1 更新状态**（`M_updateSingleIssue`）：`issueStatus: Resolved`、`exNextPlan: 已修复 commit: <hash>，待验证`。

**8.2 上传修复评论**（`M_saveComment`,HTML）：
```
【修复完成】结论：<一句话根因> / 修复内容 / 验证结果(编译✓ 用例 x/x 100% PASS 冒烟✓) /
MR/Commit / 审查记录(F1✓ F3✓)
```

## Step 9: 生成修复报告

```markdown
# IPD 问题修复完成
- 问题单/标题/优先级
- 修复内容（定位模块/修改文件/修复逻辑）
- 验证结果（编译/用例/冒烟）
- 提交信息（Commit/Branch）
- IPD 更新（状态/进展）
- 审查记录（F1/F3 + 豁免原因如有）
```

## 错误处理

- **结论门禁拒绝**: 提示先运行 `ipd-analysis <issId>`，不绕过
- **环境类错误（MCP/路径/glab）**: `setup.py check` / env-doctor 定位,修复后重试
- **编译失败**: 参考故障排除文档,修复后重新编译
- **用例失败**: 区分新引入 vs 已存在;修复后重跑
- **审查打回**: 按审查报告修改,不豁免则必须通过
- **提交失败**: 检查 commit hook,确保格式正确

## 依赖

- 前置: `ipd-analysis` - 完整分析结论（强制门禁）
- 测试: `osbot-test` - 测试编排（TDD 用例集执行）
- 环境: `env-doctor` / `setup.py` - 环境门禁
- MCP: `mi-adt` - 状态更新/评论
- 子 agent: 门禁 F1/F3 独立复核
- 本地: `.claude/ipd-conclusions/` - 结论/用例集/审查报告
