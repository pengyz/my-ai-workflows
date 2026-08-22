---
name: mai-implement-workflow
description: |
  IPD 功能开发工作流（非 bugfix）：需求确认门禁 → 方案评审 → TDD 用例集 → 实现代码 →
  编译验证 + 充分跑用例 → 独立复核 → 提交 → 更新 IPD 状态。
  用于功能/新特性开发，不需要 mai-analysis 的根因分析结论（bugfix 用 mai-fix-workflow）。
  触发词："开发功能"、"implement"、"新功能开发"、"做 feature"。
---

# IPD 功能开发工作流 (implement)

用于**功能开发/新特性**（bugfix 请用 `mai-fix-workflow`,需先 mai-analysis 结论）。

核心原则：
1. **需求确认门禁**：先确认需求与验收标准（无 IPD 分析结论要求）
2. **TDD 先行**：实现前先定用例集合（mai-osbot-test 编排），红→绿
3. **关键决策前子 agent 独立复核**：方案评审、完成复核
4. **充分验证**：相关用例 100% PASS + 冒烟，才可提交

## 触发方式

- "开发功能 X"
- "/mai-implement-workflow"
- "implement 需求 ISS-xxx"（如有关联 IPD 单）

## 前置

环境门禁（复用 `mai-env-doctor` / `setup.py`）：`mi-adt` MCP（可选,有关联 IPD 单时）、osbot 项目环境、`osbot-eval`（测试）。WF_ROOT 定位：`python3 wf_root.py --check`（见 mai-env-doctor）。

---

## Step 0: 需求确认门禁（必须，不通过即拒绝）

确认本次开发的**需求定义**：

**0.1 需求来源**：
- 关联 IPD 需求单（exRequirementId / issId）→ 调用 `mi-adt` 查询需求描述与验收标准
- 无 IPD 单 → 用户直接给出需求说明 + 验收标准

**0.2 需求完整性检查**（缺一不可）：
- 功能目标（一句话）
- 范围边界（做什么/不做什么）
- 验收标准（可验证的行为/结果描述）
- 影响面（涉及模块/现有功能回归风险）

**判定**：
- 四项齐全 → 继续 Step 1
- 缺失 → **拒绝开始**：`需求定义不完整，请补充 <缺失项>（目标/边界/验收标准/影响面）`

**0.3 登记修复数据库**（关联 IPD 单时）：
```bash
python <WF_ROOT>/fix-db.py add <issId> --title "<功能名>" --type feature --status implementing
```
（无 IPD 单可跳过,或用内部标识登记）

## Step 1: 制定实现方案 + 门禁 F1 方案评审

**1.1 制定方案**：
- 技术选型/架构方案（2-3 候选对比：优点/缺点/风险/推荐度）
- 推荐方案：修改内容 / 修改原因 / 影响范围 / 测试计划

**1.2 门禁 F1 — 方案评审（子 agent 独立复核）**：
启动独立子 agent（无主 agent 上下文，给需求定义 + 方案），检查：
- 方案是否覆盖需求全部验收标准
- 范围是否贴合（无过度设计/无遗漏）
- 回归风险：影响面分析是否充分

输出落盘 `.claude/ipd-implementations/<需求或id>-review-F1.md`。不过 → 修改方案重审；用户可豁免（记录原因）。

**与用户确认方案后**进入 Step 2。

## Step 2: TDD 用例集（实现前必做，门禁 F2）

**实现前先定测试用例集合**，用 `mai-osbot-test` 编排测试方案：

**2.1 确定用例范围**（基于方案影响面）：
- 新行为 → 新增 `eval/cases/` YAML case（`validate_cases.py` schema 校验通过）
- CLI 命令逻辑 → 关联/新增 `scripts/tests/*-test.mjs`
- 回归范围 → 相关 suite（`--set`）+ 冒烟（`--smoke`）

**2.2 用 mai-osbot-test 编排**：调用 `mai-osbot-test` skill 按场景路由，明确：
- 用例清单（case-id 或 pattern）
- 执行顺序（新用例红→绿，再回归）
- 通过标准（新增用例 + 相关回归 100% PASS）

**2.3 输出用例集清单**到 `.claude/ipd-implementations/<需求或id>-tdd-cases.md`。

**确认用例集后**才进入 Step 3 写代码。

## Step 3: 实现代码

按方案实现：
- 遵循项目规范（资源使用、日志脱敏、错误处理、参数校验、性能考虑）
- 关键路径添加日志埋点
- 注释说明实现意图

## Step 4: 编译验证 + 跑用例集

**4.1 编译**（路径以 mai-env-doctor 探测的 osbot 路径为准）：
```bash
cd <mai-env-doctor 探测到的 osbot 路径>
./scripts/package-ui.sh sidekick-ui
```
失败 → 修复后重新编译。

**4.2 跑 TDD 用例集**（按 Step 2 编排，经 mai-osbot-test）：
- 新增用例 → 通过（红→绿完成）
- 相关回归 → 100% PASS
- 冒烟 → 100% PASS

记录结果。

## Step 5: 门禁 F3 — 实现完成独立复核（子 agent）

启动独立子 agent（给需求定义 + 实现 diff + 用例结果），检查：
- 实现是否覆盖全部验收标准
- 用例是否全跑、是否有未覆盖场景
- 代码质量：是否引入新问题（回归风险）

输出落盘 `.claude/ipd-implementations/<需求或id>-review-F3.md`。不过 → 修改后重审；用户可豁免（记录原因）。

## Step 6: 提交代码

```bash
git add <修改的文件>
git commit -s -m "feat: <简短描述> (<需求/IssId>)"
```
遵循 commit 规范：类型 feat、无 scope 括号、`-s`。

## Step 7: 创建 MR + 更新状态

**7.1 创建 MR**（`glab mr create`），标题 `feat: <描述>`。

**7.2 更新修复数据库**（关联 IPD 单时）：
```bash
python <WF_ROOT>/fix-db.py update <issId> --status mr_created -f mr="!<MR编号>" -t "MR 已提交"
```

**7.3 更新 IPD 状态**（`M_updateSingleIssue`，如有关联单）：`issueStatus: Resolved`（或项目约定状态）、`exNextPlan: 已实现，MR !<编号>`。

## Step 8: 生成完成报告

```markdown
# 功能开发完成
- 需求 / 验收标准
- 实现内容（模块/文件/逻辑）
- 验证结果（编译/用例/冒烟）
- 提交信息（Commit/MR）
- 审查记录（F1/F3 + 豁免原因如有）
```

## 错误处理

- **需求门禁拒绝**: 补齐需求定义（目标/边界/验收标准/影响面），不绕过
- **环境类错误（MCP/路径）**: `setup.py check` / mai-env-doctor 定位,修复后重试
- **编译失败**: 参考故障排除文档,修复后重新编译
- **用例失败**: 区分新引入 vs 已存在;修复后重跑
- **审查打回**: 按审查报告修改,不豁免则必须通过

## 与 mai-fix-workflow 的区别

| 维度 | mai-fix-workflow (bugfix) | mai-implement-workflow (feature) |
|------|--------------------------|----------------------------------|
| 前置门禁 | F0 结论双查（必须 mai-analysis 根因结论） | 需求确认门禁（目标/边界/验收标准/影响面） |
| fix-db type | bugfix | feature |
| 初始状态 | analyzing → conclusion_uploaded | implementing |
| commit 类型 | fix: | feat: |
| 触发词 | "修复 ISS-xxx" | "开发功能 X" |

## 依赖

- 数据库: `fix-db.py` - 修复数据库（Step 0 登记 / mr_created / merged）
- 测试: `mai-osbot-test` - 测试编排（TDD 用例集执行）
- 环境: `mai-env-doctor` / `setup.py` - 环境门禁
- MCP: `mi-adt` - 需求查询/状态更新（可选）
- 子 agent: 门禁 F1/F3 独立复核
- 本地: `.claude/ipd-implementations/` - 方案/用例集/审查报告
