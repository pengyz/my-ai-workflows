---
name: mai-fix-workflow
description: |
  IPD 问题修复工作流：读取根因结论 → 修复方案评审 → TDD 用例集 → 修复代码 →
  编译验证 + 充分跑用例 → 独立复核 → 提交 → 更新 IPD 状态。
  **强制前置**：必须由 mai-analysis 给出过完整结论（IPD 评论根因 + 本地结论文件双查），
  无结论拒绝开始。触发词："修复 IPD 问题"、"修复 ISS-xxx"、"处理 ISS-xxx"。
---

# IPD 问题修复工作流

基于 `mai-analysis` 的完整结论执行修复。**不重新分析根因**——结论是前置门禁，缺失即拒绝。

核心原则：
1. **结论门禁**：IPD 评论 + 本地结论文件双查，缺一不可
2. **TDD 先行**：修复前先定用例集合（mai-osbot-test 编排），红→绿
3. **关键决策前子 agent 独立复核**：方案评审、完成复核
4. **充分验证**：相关用例 100% PASS + 冒烟，才可提交

## 触发方式

- "修复 IPD 问题 ISS-xxx"
- "/mai-fix-workflow ISS-xxx"

## 前置

环境门禁（复用 `mai-env-doctor` / `setup.py`）：`mi-adt` MCP、osbot 项目环境、`osbot-eval`（测试）。WF_ROOT 定位：`python3 wf_root.py --check`（见 mai-env-doctor）。

---

## Step 0: 结论门禁（必须，不通过即拒绝）

双查该问题是否已有完整分析结论：

**0.1 查 IPD 评论**：调用 `mi-adt` `M_pageOverallComment` / `M_getCommentList`（issId），检查是否存在 `mai-analysis` 上传的**根因分析评论**（内容含"根因定谳"标记）。

**0.2 查本地结论文件**：`.claude/ipd-conclusions/<issId>-conclusion.md` 是否存在且完整（含结论/证据链/问题定界/问题清单/修复方案建议 + 审查记录）。

**0.3 查修复数据库**：
```bash
python <WF_ROOT>/fix-db.py query <issId>
```
确认状态为 conclusion_uploaded（分析已定谳,尚未修复完成）。

**0.4 判定结论类型**（强制）：
- 读取本地结论文件的"整体结论"字段
- 若为"**无法给出结论**" → **拒绝开始修复**：
  `该问题分析结论为"无法给出结论"，存在未闭合缺口（见结论文件 2.8 后续动作）。请先解决分析缺口（补日志/复现/QA 复现/源码确认）后再运行修复。`
- 若为"**确定根因**" → 继续判定

**判定**：
- 评论 + 本地结论 + 数据库状态均满足 + 结论为"确定根因" → 继续 Step 1
- IPD 评论有、本地缺 → 从 IPD 评论重建本地结论文件（提示用户确认），继续
  **注意**：重建的结论文件缺少结构化字段（凭证清单、闭环对照表、审查记录），标记为"降级结论"。
  后续步骤依赖这些字段时（如 F1 审查），需从 IPD 评论中提取或要求用户补充。
- 任一缺失 → **拒绝开始**：`该问题尚无完整分析结论，请先运行 mai-analysis <issId> 完成根因分析与结论上传`
- 结论为"无法给出结论" → **拒绝开始**：`该问题分析结论为"无法给出结论"，无法执行修复`

通过门禁后登记修复状态：
```bash
python <WF_ROOT>/fix-db.py update <issId> --status fixing -t "开始修复"
```

## Step 1: 读取结论

从 `.claude/ipd-conclusions/<issId>-conclusion.md`（或 IPD 评论）提取：
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

启动独立子 agent（无主 agent 上下文）。

**F1 prompt 模板**：
```
你是 IPD 问题修复方案评审专家。请审查以下修复方案：

## 审查维度
1. 方案与结论一致性：是否针对根因而非症状
2. 覆盖度：是否覆盖结论问题清单里的全部问题（多根因场景）
3. 回归风险：影响范围分析

## 输入材料
- 结论文件：<WF_ROOT>/.claude/ipd-conclusions/<issId>-conclusion.md
- 修复方案：见下方
- 门禁 G 报告：<WF_ROOT>/.claude/ipd-conclusions/<issId>-review-G[-vN].md（可选，供参考分析可信度）

## 修复方案内容
[在此粘贴 2.1 制定的方案]

## 输出要求
- 落盘：<WF_ROOT>/.claude/ipd-conclusions/<issId>-review-F1.md
- 格式：判定（通过/驳回）+ 逐维度审查意见 + 修改点清单（若驳回）
```

**重审上限**：默认 ≤2 轮，超限用户可豁免（记录原因）。

输出落盘 `.claude/ipd-conclusions/<issId>-review-F1.md`。不过 → 修改方案重审；用户可豁免（记录原因）。

**与用户确认方案后**进入 Step 3。

## Step 3: TDD 用例集（修复前必做，门禁 F2）

**修复前先定测试用例集合**，用 `mai-osbot-test` 编排测试方案：

**3.1 确定用例范围**（基于方案的影响面）：
- 行为类变更 → 新增/更新 `eval/cases/` YAML case（`validate_cases.py` schema 校验通过）
- CLI 命令逻辑 → 关联 `scripts/tests/*-test.mjs`
- 回归范围 → 相关 suite（`--set`）+ 冒烟（`--smoke`）

**3.1b 对齐 analysis 验证方法**（强制）：
- 从 conclusion 文件"修复方案"节提取每个修复项的"验证方法"
- 确认 TDD 用例集覆盖了这些验证方法：
  - 覆盖 → 标注对应关系（用例 ID ↔ 验证方法）
  - 未覆盖 → 补充用例或标注"待修复阶段手动验证"

**3.2 用 mai-osbot-test 编排**：调用 `mai-osbot-test` skill 按场景路由（单端 eval / JS CLI / 冒烟 / 双端按需），明确：
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

**5.1 编译**（路径以 mai-env-doctor 探测的 osbot 路径为准）：
```bash
cd <mai-env-doctor 探测到的 osbot 路径>
./scripts/package-ui.sh sidekick-ui
```
失败 → 修复后重新编译。

**5.2 跑 TDD 用例集**（按 Step 3 编排，经 mai-osbot-test）：
- 新增用例 → 通过（红→绿完成）
- 相关回归 → 100% PASS
- 冒烟 → 100% PASS

记录结果。

## Step 6: 门禁 F3 — 修复完成独立复核（子 agent）

启动独立子 agent（无主 agent 上下文）。

**F3 prompt 模板**：
```
你是 IPD 问题修复完成复核专家。请审查修复结果：

## 审查维度
1. 修复与结论一致性：是否修了根因而非症状
2. 用例覆盖：TDD 用例是否全跑、是否有未覆盖场景
3. 代码质量：是否引入新问题（回归风险）

## 输入材料
- 结论文件：<WF_ROOT>/.claude/ipd-conclusions/<issId>-conclusion.md
- 修复 diff：git diff 或修改文件列表
- 用例结果：Step 5 的测试执行结果
- TDD 用例集：<WF_ROOT>/.claude/ipd-conclusions/<issId>-tdd-cases.md

## 输出要求
- 落盘：<WF_ROOT>/.claude/ipd-conclusions/<issId>-review-F3.md
- 格式：判定（通过/驳回）+ 逐维度审查意见 + 修改点清单（若驳回）
```

**重审上限**：默认 ≤2 轮，超限用户可豁免（记录原因）。

输出落盘 `.claude/ipd-conclusions/<issId>-review-F3.md`。不过 → 修复后重审；用户可豁免（记录原因）。

## Step 7: 提交代码

```bash
git add <修改的文件>
git commit -s -m "fix: <简短描述> (Issue ISS-xxx)"
```
遵循 commit 规范：类型 fix/feat、无 scope 括号、`-s`、引用 Issue。

提交后登记修复数据库（`MR 编号来自 glab mr create 或已有 MR`）：
```bash
python <WF_ROOT>/fix-db.py update <issId> --status mr_created -f mr="!<MR编号>" -t "MR 已提交"
```

> 若 MR 合入后收到通知/确认，再更新：
> ```bash
> python <WF_ROOT>/fix-db.py update <issId> --status merged -f merge_status=merged -t "MR 已合入"
> ```

## Step 8: 更新 IPD 状态 + 上传修复评论

**8.1 更新状态**（`M_updateSingleIssue`）：
- 修复成功（Step 5/6 全部通过）→ `issueStatus: Resolved`、`exNextPlan: 已修复 commit: <hash>，待验证`
- 修复阻塞/失败 → 更新 fix-db 状态为 `blocked`，在 IPD 进展中说明阻塞原因，不修改 issueStatus

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

- **结论门禁拒绝**: 提示先运行 `mai-analysis <issId>`，不绕过
- **"无法给出结论"拒绝**: 提示先解决分析缺口（补日志/复现/QA 复现/源码确认），不绕过
- **环境类错误（MCP/路径/glab）**: `setup.py check` / mai-env-doctor 定位,修复后重试
- **编译失败**: 参考故障排除文档,修复后重新编译
- **用例失败**: 区分新引入 vs 已存在;修复后重跑
- **审查打回**: 按审查报告修改，最多 2 轮重审，超限用户可豁免（记录原因）
- **提交失败**: 检查 commit hook,确保格式正确
- **修复阻塞/失败**: 遇到不可恢复错误（编译无法修复、用例始终失败、根因不充分无法制定方案）→ 更新 fix-db 状态为 `blocked`，在 IPD 评论中说明阻塞原因和后续待办

## 依赖

- 前置: `mai-analysis` - 完整分析结论（强制门禁）
- 数据库: `fix-db.py` - 修复数据库（Step 0 查询 / fixing / mr_created / merged 登记）
- 测试: `mai-osbot-test` - 测试编排（TDD 用例集执行）
- 环境: `mai-env-doctor` / `setup.py` - 环境门禁
- MCP: `mi-adt` - 状态更新/评论
- 子 agent: 门禁 F1/F3 独立复核
- 本地: `.claude/ipd-conclusions/` - 结论/用例集/审查报告
