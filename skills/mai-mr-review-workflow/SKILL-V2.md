---
name: mai-mr-review-workflow-v2
description: 双模式 MR Review 工作流：自己的 MR（CR 意见响应 + 独立复核 + 自动修复）；别人的 MR（对抗性 review + 分级意见发表）
---

# MR Review 工作流 V2

**核心升级**：支持"自己的 MR"和"别人的 MR"两种模式，所有判定均需复核。

## 触发方式

- "review 这个 MR"
- "响应 CR 意见"
- "对抗性 review MR"
- "/mai-mr-review-workflow-v2 <MR-URL>"

## 工作流程

### Step 0: 环境门禁 + 模式识别

**0.1 环境检查**（继承 V1 逻辑）

轻量门禁：定位仓库根，读 `.env-status.json`，验证必需依赖。

**0.2 模式识别**

```bash
# 获取 MR 信息
MR_URL="$1"
MR_INFO=$(glab mr view "$MR_URL" --json author,assignees,reviewers)

# 识别作者
MR_AUTHOR=$(echo "$MR_INFO" | jq -r '.author.username')
CURRENT_USER=$(git config user.name)

# 判定模式
if [ "$MR_AUTHOR" = "$CURRENT_USER" ]; then
  MODE="own"
  echo "✓ 检测到自己的 MR，进入修复模式"
else
  MODE="review"
  echo "✓ 检测到他人的 MR，进入对抗性 review 模式"
fi
```

---

## 模式 1: 自己的 MR（修复模式）

### Step 1.1: 读取所有 CR 意见

```bash
# 获取所有 discussions
glab mr view "$MR_URL" --json discussions > discussions.json

# 提取未 resolved 的意见
jq '[.discussions[] | select(.resolved == false) | {
  id: .id,
  note_id: .notes[0].id,
  author: .notes[0].author.username,
  body: .notes[0].body,
  position: .notes[0].position,
  created_at: .notes[0].created_at
}]' discussions.json > cr-opinions.json
```

**输出示例**：
```json
[
  {
    "id": "disc_123",
    "note_id": "note_456",
    "author": "wangjianlei",
    "body": "这里应该用 `readText()` 而不是 `readBytes().decodeToString()`",
    "position": {
      "new_path": "app/interconnect/RemoteFileTool.kt",
      "new_line": 142
    }
  }
]
```

### Step 1.2: 分析 CR 意见是否成立（需复核）

**Agent 1: Opinion Analyzer**（初步分析）

```python
for opinion in cr_opinions:
    analysis = agent(f"""
分析以下 CR 意见是否成立：

**意见**: {opinion.body}
**代码位置**: {opinion.position.new_path}:{opinion.position.new_line}
**上下文**: 
```kotlin
{read_code_context(opinion.position)}
```

**分析要点**：
1. 意见指出的问题是否真实存在？
2. 建议的修复方式是否正确？
3. 是否有更优方案？
4. 是否属于次要问题/风格问题？

**输出**：
- valid: true/false（意见是否成立）
- severity: critical/major/minor（严重程度）
- reason: 判定理由
- alternative: 更优方案（如果有）
""", schema={
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "severity": {"enum": ["critical", "major", "minor", "style"]},
        "reason": {"type": "string"},
        "alternative": {"type": "string"},
        "requires_clarification": {"type": "boolean"}
    }
})
    opinion["analysis"] = analysis
```

**Agent 2: Opinion Verifier**（独立复核）

```python
for opinion in cr_opinions:
    verification = agent(f"""
独立复核以下 CR 意见分析结论：

**原始意见**: {opinion.body}
**初步分析**: {opinion.analysis}
**代码位置**: {opinion.position.new_path}:{opinion.position.new_line}

**复核要点**：
1. 初步分析的 valid 判定是否准确？
2. severity 评级是否合理？
3. 是否遗漏了其他角度的考虑？

**输出**：
- agree: true/false（是否同意初步分析）
- corrected_severity: 修正后的严重程度（如果不同意）
- additional_context: 补充的考虑因素
""", schema={
    "type": "object",
    "properties": {
        "agree": {"type": "boolean"},
        "corrected_severity": {"enum": ["critical", "major", "minor", "style", null]},
        "additional_context": {"type": "string"}
    }
})
    
    # 如果复核不同意，使用复核结论
    if not verification["agree"]:
        opinion["analysis"]["severity"] = verification["corrected_severity"]
        opinion["analysis"]["reason"] += f"\n\n【复核补充】{verification['additional_context']}"
    
    opinion["verified"] = True
```

### Step 1.3: 独立复核整个 MR

**Agent 3: MR Holistic Reviewer**（整体复核）

```python
mr_review = agent(f"""
对整个 MR 进行独立复核，发现所有潜在问题：

**MR 信息**:
- URL: {MR_URL}
- 标题: {MR_INFO.title}
- 描述: {MR_INFO.description}

**变更范围**:
{git diff --stat origin/main...HEAD}

**完整 diff**:
{git diff origin/main...HEAD}

**复核维度**：
1. **正确性**: 逻辑错误、边界条件、并发问题
2. **安全**: 权限绕过、注入漏洞、数据泄露
3. **性能**: 内存泄漏、死循环、阻塞主线程
4. **可维护性**: 代码重复、命名混乱、缺少注释
5. **规范合规**: 违反项目规范（参考 CLAUDE.md）

**已有 CR 意见**（避免重复）:
{json.dumps([op["body"] for op in cr_opinions])}

**输出**：发现的新问题列表
""", schema={
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "severity": {"enum": ["critical", "major", "minor"]},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "suggestion": {"type": "string"}
                }
            }
        }
    }
})
```

**Agent 4: Findings Verifier**（发现问题复核）

```python
for finding in mr_review["findings"]:
    verification = agent(f"""
复核以下发现的问题：

**问题**: {finding.description}
**位置**: {finding.file}:{finding.line}
**严重程度**: {finding.severity}
**建议**: {finding.suggestion}

**代码上下文**:
```
{read_code_context(finding.file, finding.line)}
```

**复核要点**：
1. 这个问题是否真实存在？
2. 严重程度评估是否准确？
3. 修复建议是否可行？

**输出**：
- confirmed: true/false
- adjusted_severity: 调整后的严重程度（如果需要）
- reason: 复核理由
""", schema={
    "type": "object",
    "properties": {
        "confirmed": {"type": "boolean"},
        "adjusted_severity": {"enum": ["critical", "major", "minor", null]},
        "reason": {"type": "string"}
    }
})
    
    finding["verified"] = verification
    if not verification["confirmed"]:
        finding["status"] = "rejected"
    elif verification["adjusted_severity"]:
        finding["severity"] = verification["adjusted_severity"]
```

### Step 1.4: 综合所有意见做 fix

**合并问题清单**：

```python
# 收集所有需要修复的问题
issues_to_fix = []

# 1. CR 意见中成立的
for opinion in cr_opinions:
    if opinion["analysis"]["valid"] and opinion["verified"]:
        issues_to_fix.append({
            "source": "cr_opinion",
            "id": opinion["id"],
            "severity": opinion["analysis"]["severity"],
            "file": opinion["position"]["new_path"],
            "line": opinion["position"]["new_line"],
            "description": opinion["body"],
            "suggestion": opinion["analysis"].get("alternative") or "按 CR 意见修复"
        })

# 2. 独立复核发现的新问题
for finding in mr_review["findings"]:
    if finding["verified"]["confirmed"]:
        issues_to_fix.append({
            "source": "independent_review",
            "severity": finding["severity"],
            "file": finding["file"],
            "line": finding["line"],
            "description": finding["description"],
            "suggestion": finding["suggestion"]
        })

# 按严重程度排序
issues_to_fix.sort(key=lambda x: {"critical": 0, "major": 1, "minor": 2}[x["severity"]])
```

**Agent 5: Fix Implementor**（修复实施）

```python
for issue in issues_to_fix:
    # 只修复 critical 和 major，minor 询问用户
    if issue["severity"] == "minor":
        user_choice = ask_user(f"是否修复次要问题：{issue['description']}？")
        if not user_choice:
            continue
    
    fix_result = agent(f"""
实施以下修复：

**问题**: {issue.description}
**位置**: {issue.file}:{issue.line}
**建议**: {issue.suggestion}

**当前代码**:
```
{read_file(issue.file)}
```

**操作**：
1. 阅读完整文件理解上下文
2. 实施修复
3. 验证修复不引入新问题

使用 Edit 工具修改文件。
""")
    
    issue["fixed"] = True
    issue["fix_commit"] = git_current_commit()
```

### Step 1.5: 复核修复结果

**Agent 6: Fix Verifier**（修复复核）

```python
fix_summary = agent(f"""
复核所有修复结果：

**修复清单**:
{json.dumps([{
    "description": issue["description"],
    "file": issue["file"],
    "suggestion": issue["suggestion"]
} for issue in issues_to_fix if issue.get("fixed")])}

**修复后的完整 diff**:
{git diff origin/main...HEAD}

**复核要点**：
1. 所有问题是否真正被修复？
2. 修复是否引入新问题？
3. 修复是否符合项目规范？

**输出**：
- all_fixed: true/false
- remaining_issues: 未修复的问题
- introduced_issues: 新引入的问题
""", schema={
    "type": "object",
    "properties": {
        "all_fixed": {"type": "boolean"},
        "remaining_issues": {"type": "array", "items": {"type": "string"}},
        "introduced_issues": {"type": "array", "items": {"type": "string"}}
    }
})

# 如果有遗留问题或新问题，再次修复
if not fix_summary["all_fixed"] or fix_summary["introduced_issues"]:
    # 递归修复（最多 2 轮）
    ...
```

### Step 1.6: 跑测试

```bash
# 调用 mai-osbot-test
/mai-osbot-test analyze-and-eval --mr "$MR_URL"
```

等待测试完成，获取测试报告。

**如果测试失败**：
- 分析失败原因
- 修复测试失败
- 重新运行测试

### Step 1.7: 更新 MR

```bash
# Commit 所有修复
git add -A
git commit -m "fix: 响应 CR 意见并修复 review 发现的问题

- 修复 CR 意见: ${已修复的 CR 意见数量} 个
- 修复独立发现的问题: ${独立发现并修复的问题数量} 个

Co-Authored-By: Claude <noreply@anthropic.com>"

# Push
git push origin HEAD
```

### Step 1.8: Resolve CR 意见 / 请求澄清

**对于成立的 CR 意见**：

```bash
for opinion in cr_opinions:
    if opinion["analysis"]["valid"] and opinion.get("fixed"):
        # Resolve discussion
        glab mr discussion resolve "$MR_URL" \
          --discussion-id "${opinion.id}" \
          --note "✓ 已修复。${opinion.analysis.reason}"
    elif opinion["analysis"]["valid"] and not opinion.get("fixed"):
        # 说明为何未修复
        glab mr discussion reply "$MR_URL" \
          --discussion-id "${opinion.id}" \
          --note "⏳ 已确认问题，但因 ${原因} 暂未修复，已记录到 backlog"
```

**对于不成立的 CR 意见**：

```bash
for opinion in cr_opinions:
    if not opinion["analysis"]["valid"] or opinion["analysis"]["requires_clarification"]:
        # 请求澄清
        glab mr discussion reply "$MR_URL" \
          --discussion-id "${opinion.id}" \
          --note "❓ 请求澄清：${opinion.analysis.reason}

【复核意见】${opinion.verified 的补充上下文}

是否存在我遗漏的场景？"
```

### Step 1.9: 生成完成报告

```markdown
# MR 修复完成

**MR**: {MR_URL}

## CR 意见响应

### 已修复（{count}）
- ✓ [{opinion.author}] {opinion.body} → {fix_description}

### 请求澄清（{count}）
- ❓ [{opinion.author}] {opinion.body} → {clarification_reason}

## 独立复核发现

### 严重问题（{count}）
- 🔴 {finding.description} → 已修复

### 主要问题（{count}）
- 🟡 {finding.description} → 已修复

## 测试结果

✓ 测试通过: {passed}/{total}
✓ 编译通过

## 后续步骤

1. 等待 CR 意见澄清回复
2. 等待新一轮 review
```

---

## 模式 2: 别人的 MR（对抗性 review 模式）

### Step 2.1: 对抗性 review

**Agent 7: Adversarial Reviewer**（对抗性审查）

```python
adversarial_review = agent(f"""
以"挑刺"视角对抗性 review 这个 MR：

**MR 信息**:
- URL: {MR_URL}
- 作者: {MR_INFO.author}
- 标题: {MR_INFO.title}
- 描述: {MR_INFO.description}

**完整 diff**:
{git diff origin/main...HEAD}

**对抗性审查要点**：
1. **正确性**：会不会 crash？会不会数据丢失？会不会死锁？
2. **安全**：会不会被绕过？会不会泄露数据？
3. **边界条件**：空值、大数据、并发、网络失败、权限不足
4. **规范合规**：是否违反 CLAUDE.md 中的规则？
5. **可维护性**：是否引入技术债？是否有坏味道？
6. **测试覆盖**：是否有测试？测试是否充分？

**审查标准**：
- 对严重问题零容忍
- 对次要问题也要指出，但标明非阻塞
- 对风格问题保持克制，除非影响可读性

**输出**：发现的问题列表，区分严重和次要
""", schema={
    "type": "object",
    "properties": {
        "critical_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "description": {"type": "string"},
                    "impact": {"type": "string"},
                    "blocking": {"type": "boolean", "const": True}
                }
            }
        },
        "minor_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "description": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "blocking": {"type": "boolean", "const": False}
                }
            }
        }
    }
})
```

### Step 2.2: 门禁复核

**Agent 8: Review Gatekeeper**（review 门禁复核）

```python
for issue in adversarial_review["critical_issues"]:
    gate_check = agent(f"""
门禁复核以下严重问题：

**问题**: {issue.description}
**影响**: {issue.impact}
**位置**: {issue.file}:{issue.line}

**代码上下文**:
```
{read_code_context(issue.file, issue.line)}
```

**门禁标准**：
1. 这个问题是否真的严重到需要阻塞 MR？
2. 是否存在误判（理解偏差、上下文不足）？
3. 是否有快速缓解方案（降级为非阻塞）？

**输出**：
- approve_publish: true/false（是否批准发表）
- adjusted_severity: 调整后的严重程度（如果需要）
- reason: 门禁判定理由
""", schema={
    "type": "object",
    "properties": {
        "approve_publish": {"type": "boolean"},
        "adjusted_severity": {"enum": ["critical", "major", "minor", null]},
        "reason": {"type": "string"}
    }
})
    
    issue["gate_checked"] = gate_check
    if not gate_check["approve_publish"]:
        issue["status"] = "rejected_by_gate"
    elif gate_check["adjusted_severity"]:
        # 降级为次要问题
        adversarial_review["minor_issues"].append({
            **issue,
            "blocking": False,
            "original_severity": "critical"
        })
        issue["status"] = "downgraded"

# 对次要问题也做门禁（避免过于吹毛求疵）
for issue in adversarial_review["minor_issues"]:
    gate_check = agent(f"""
门禁复核次要问题：

**问题**: {issue.description}

**判断标准**：
1. 这个问题是否值得提出？
2. 是否过于吹毛求疵？
3. 是否应该建议开 issue 而不是在 MR 中讨论？

**输出**：
- approve_publish: true/false
- recommend_issue: true/false（是否建议开 issue）
- reason: 理由
""", schema={
    "type": "object",
    "properties": {
        "approve_publish": {"type": "boolean"},
        "recommend_issue": {"type": "boolean"},
        "reason": {"type": "string"}
    }
})
    
    issue["gate_checked"] = gate_check
    if not gate_check["approve_publish"]:
        issue["status"] = "rejected_by_gate"
```

### Step 2.3: 发表 review 意见

**对于严重问题**：行内 discussion

```bash
for issue in adversarial_review["critical_issues"]:
    if issue["gate_checked"]["approve_publish"]:
        # 创建行内 discussion
        glab mr discussion create "$MR_URL" \
          --file "${issue.file}" \
          --line "${issue.line}" \
          --blocking \
          --note "🔴 【严重问题】${issue.description}

**影响**: ${issue.impact}

**建议**: ${issue.suggestion}

【门禁复核】${issue.gate_checked.reason}"
```

**对于次要问题**：汇总成一个回复

```bash
# 构造次要问题汇总
minor_issues_summary=$(cat <<EOF
## 次要问题汇总（非阻塞）

以下问题不阻塞 MR，但建议考虑优化：

$(for issue in adversarial_review["minor_issues"]; do
    if issue["gate_checked"]["approve_publish"]:
        echo "### ${issue.file}:${issue.line}"
        echo ""
        echo "${issue.description}"
        echo ""
        echo "**建议**: ${issue.suggestion}"
        echo ""
        if issue["gate_checked"]["recommend_issue"]:
            echo "💡 建议开 issue 跟进：${issue.description}"
        fi
        echo "---"
        echo ""
    fi
done)

**说明**: 以上问题均不阻塞本 MR merge，可在后续优化。
EOF
)

# 发表汇总评论
glab mr comment "$MR_URL" --note "$minor_issues_summary"
```

**对于已有 CR 意见的响应**：

```bash
# 获取现有 discussions
existing_discussions=$(glab mr view "$MR_URL" --json discussions)

for discussion in existing_discussions:
    review_response = agent(f"""
分析以下 CR 意见：

**原意见**: {discussion.notes[0].body}
**位置**: {discussion.position}

**判断**：
1. 这个 CR 意见是否成立？
2. 是否属于严重问题/次要问题/非 MR 问题？
3. 如果是次要问题，是否应该建议开 issue？

**输出**：你的回复意见
""", schema={
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "severity": {"enum": ["critical", "minor", "non_issue", "out_of_scope"]},
        "response": {"type": "string"},
        "recommend_issue": {"type": "boolean"}
    }
})
    
    # 门禁复核
    gate_check = agent(f"""
门禁复核以下回复：

**原 CR 意见**: {discussion.notes[0].body}
**你的回复**: {review_response.response}

**判断**：
1. 回复是否客观、专业？
2. 是否存在过于主观的判断？
3. 是否尊重原 reviewer 的意见？

**输出**：是否批准发表
""", schema={
    "type": "object",
    "properties": {
        "approve_publish": {"type": "boolean"},
        "reason": {"type": "string"}
    }
})
    
    if gate_check["approve_publish"]:
        # 发表回复
        glab mr discussion reply "$MR_URL" \
          --discussion-id "${discussion.id}" \
          --note "${review_response.response}

【门禁复核】${gate_check.reason}"
```

### Step 2.4: 生成 review 报告

```markdown
# MR Review 完成

**MR**: {MR_URL}
**作者**: {MR_INFO.author}

## Review 结果

### 严重问题（{count}）🔴 阻塞 merge

{for issue in critical_issues if issue.gate_checked.approve_publish:
    - [{issue.file}:{issue.line}] {issue.description}
}

### 次要问题（{count}）🟡 非阻塞

{for issue in minor_issues if issue.gate_checked.approve_publish:
    - [{issue.file}:{issue.line}] {issue.description}
    {if issue.gate_checked.recommend_issue:
        💡 建议开 issue 跟进
    }
}

### 已发表意见

- 行内 discussion: {严重问题数量} 个
- 汇总评论: 1 条（包含 {次要问题数量} 个次要问题）
- CR 意见回复: {回复数量} 条

## 建议

{if has_critical_issues:
    ❌ 建议暂不 approve，待修复严重问题后重新 review
else:
    ✅ 无严重问题，建议 approve（次要问题可后续优化）
}
```

---

## 多轮迭代逻辑

### 自己的 MR
- CR 意见分析 → 复核 → 修复 → 再复核 → 测试
- 独立 review → 复核 → 修复 → 再复核 → 测试
- 测试失败 → 修复 → 重测

### 别人的 MR
- 对抗性 review → 门禁复核 → 发表
- 不通过门禁的意见不发表

---

## 错误处理

- **环境类错误**：运行 `setup.py check` 或 `mai-env-doctor`
- **分析失败**：重试一次，失败则报告并询问用户
- **修复失败**：报告失败原因，询问用户是否手动修复
- **测试失败**：分析失败原因，修复后重测
- **GitLab API 失败**：检查 `glab auth status`，重试一次

---

## 依赖

- 项目 skill: `osbot-review`, `osbot-eval`, `mai-osbot-test`
- CLI: `glab` - GitLab MR 操作
- MCP: `mi-adt`（可选，用于关联 IPD）
- Workflow: 使用子 agent 实现并行分析和复核

---

## 配置

可通过环境变量自定义：

```bash
# 自己的 MR 模式
export MR_FIX_AUTO_MINOR=true  # 自动修复次要问题，无需询问

# 别人的 MR 模式
export MR_REVIEW_STRICT_GATE=true  # 严格门禁，次要问题也需复核
export MR_REVIEW_AUTO_ISSUE=true   # 自动为次要问题创建 issue
```
