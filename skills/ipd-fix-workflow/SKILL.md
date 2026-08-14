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

### Step 2: 分析问题并定位代码

基于问题描述：
1. 识别相关模块（从 exHandleAction、issueTestComponent 推断）
2. 搜索相关代码文件
3. 使用 LSP 工具追踪调用关系
4. 定位可能的问题点

与用户讨论定位结果和修复方案。

### Step 3: 修复代码

根据分析结果修复代码：
- 使用 Edit/Write 工具修改文件
- 遵循项目规范（资源使用、日志脱敏等）
- 添加必要的注释说明修复原因

### Step 4: 编译验证

使用项目标准编译命令：

```bash
cd /home/peng/workspace/osbot
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

如果需要添加评论：
```
调用 mcp__mi-adt__M_saveComment，传入参数：
{
  "issId": "ISS-xxx",
  "content": "问题已修复\n\n修复说明：...\n\nCommit: <hash>\n测试结果：..."
}
```

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

- **IPD 查询失败**: 检查 MCP 配置，确认问题编号正确
- **编译失败**: 参考故障排除文档，修复后重新执行
- **测试失败**: 分析失败原因，修复后重新测试
- **提交失败**: 检查 commit hook，确保格式正确

## 个人偏好配置

可根据个人习惯调整：
- 编译命令（如果需要其他 build variant）
- 测试策略（全量测试 vs 冒烟测试）
- IPD 状态更新时机（修复后立即更新 vs 测试通过后更新）

## 依赖

- MCP: `mi-adt` - IPD 问题追踪系统
- 项目 skill: `osbot-eval` - 测试用例执行
- Git 配置: commit hook 已安装
