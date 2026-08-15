---
name: mai-mr-review-workflow-v2-gated
description: 双模式 MR Review 工作流（带完整门禁）：自己的 MR（CR 意见响应 + 独立复核 + 自动修复）；别人的 MR（对抗性 review + 分级意见发表）。所有判定均需复核，所有门禁不通过则打回重做。
---

# MR Review 工作流 V2 (带门禁架构)

**核心升级**：
- 支持"自己的 MR"和"别人的 MR"两种模式
- 所有判定均需独立复核
- 6 层门禁架构，任一门禁失败则打回重做
- 问题去重机制
- 统一的修复-测试循环

## 触发方式

- "review 这个 MR"
- "响应 CR 意见"
- "对抗性 review MR"
- "/mai-mr-review-workflow-v2-gated <MR-URL>"

---

## 工作流程概览

```
Gate 0: 环境门禁 → Gate 1: 模式识别 →
[模式 1: 自己的 MR]
  Gate 2: CR 意见一致性 → Gate 3: 独立复核确认率 →
  问题去重 → Gate 4: 修复完整性 → Gate 5: 测试通过率 →
  更新 MR + Resolve CR 意见

[模式 2: 别人的 MR]
  对抗性 review → Gate 6: Review 发表质量 → 发表意见
```

---

## Gate 0: 环境门禁（硬性门禁）

**检查项**：

```bash
#!/bin/bash
# 环境门禁脚本（不通过则打回重做）

set -e

echo "=== Gate 0: 环境门禁 ==="

# 1. 检查 glab 认证
echo -n "检查 glab 认证... "
glab auth status >/dev/null 2>&1 || {
  echo "❌ FAILED"
  echo ""
  echo "修复方案："
  echo "  glab auth login"
  exit 1
}
echo "✓"

# 2. 检查 git 仓库状态
echo -n "检查 git 仓库状态... "
if [[ -n $(git status --porcelain) ]]; then
  echo "❌ FAILED"
  echo ""
  echo "修复方案："
  echo "  git status  # 查看未提交变更"
  echo "  git stash   # 或先提交"
  exit 1
fi
echo "✓"

# 3. 检查 MR 可访问
echo -n "检查 MR 可访问性... "
MR_URL="$1"
glab mr view "$MR_URL" >/dev/null 2>&1 || {
  echo "❌ FAILED"
  echo ""
  echo "MR 不存在或无权限: $MR_URL"
  exit 1
}
echo "✓"

# 4. 检查必需工具
echo -n "检查必需工具... "
MISSING_TOOLS=()
for tool in glab jq git; do
  command -v $tool >/dev/null 2>&1 || MISSING_TOOLS+=($tool)
done

if [[ ${#MISSING_TOOLS[@]} -gt 0 ]]; then
  echo "❌ FAILED"
  echo ""
  echo "缺少工具: ${MISSING_TOOLS[*]}"
  echo ""
  echo "修复方案："
  [[ " ${MISSING_TOOLS[*]} " =~ " glab " ]] && echo "  brew install glab  # macOS"
  [[ " ${MISSING_TOOLS[*]} " =~ " jq " ]] && echo "  brew install jq    # macOS"
  exit 1
fi
echo "✓"

# 5. 检查仓库根目录
echo -n "检查仓库根目录... "
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "❌ FAILED"
  echo ""
  echo "不在 git 仓库中"
  exit 1
}
echo "✓"

echo ""
echo "✅ Gate 0: 环境门禁通过"
echo ""
```

**不通过处理**：
- **打回重做** - 输出缺失项清单，exit 1，终止流程
- 用户修复后重新运行

---

## Gate 1: 模式识别门禁（硬性门禁）

```bash
echo "=== Gate 1: 模式识别 ==="

# 获取 MR 信息
echo -n "获取 MR 信息... "
MR_INFO=$(glab mr view "$MR_URL" --json author,assignees,reviewers 2>/dev/null) || {
  echo "❌ FAILED"
  echo ""
  echo "无法获取 MR 信息，检查："
  echo "  1. glab auth status"
  echo "  2. MR URL 是否正确"
  echo "  3. 网络连接"
  exit 1
}
echo "✓"

# 识别作者
echo -n "识别 MR 作者... "
MR_AUTHOR=$(echo "$MR_INFO" | jq -r '.author.username')
if [[ -z "$MR_AUTHOR" || "$MR_AUTHOR" == "null" ]]; then
  echo "❌ FAILED"
  echo ""
  echo "无法识别 MR 作者"
  exit 1
fi
echo "✓ $MR_AUTHOR"

# 识别当前用户
echo -n "识别当前用户... "
CURRENT_USER=$(git config user.name)
if [[ -z "$CURRENT_USER" ]]; then
  echo "❌ FAILED"
  echo ""
  echo "无法识别当前用户，运行："
  echo "  git config user.name"
  exit 1
fi
echo "✓ $CURRENT_USER"

# 判定模式
if [[ "$MR_AUTHOR" == "$CURRENT_USER" ]]; then
  MODE="own"
  echo ""
  echo "✅ Gate 1: 模式识别通过 - 自己的 MR（修复模式）"
else
  MODE="review"
  echo ""
  echo "✅ Gate 1: 模式识别通过 - 别人的 MR（对抗性 review 模式）"
fi
echo ""
```

**不通过处理**：
- **打回重做** - 报告 API 失败或用户信息缺失，exit 1

---

## 模式 1: 自己的 MR（修复模式）

### Step 1.1: 读取所有 CR 意见

```bash
echo "=== Step 1.1: 读取 CR 意见 ==="

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

CR_COUNT=$(jq 'length' cr-opinions.json)
echo "✓ 读取到 $CR_COUNT 条未 resolved 的 CR 意见"
echo ""
```

### Step 1.2: 分析 CR 意见（双重复核）

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
4. 严重程度如何？

**输出**：
- valid: true/false（意见是否成立）
- severity: critical/major/minor/style（严重程度）
- reason: 判定理由
- alternative: 更优方案（如果有）
- requires_clarification: 是否需要澄清
""", schema={
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "severity": {"enum": ["critical", "major", "minor", "style"]},
        "reason": {"type": "string"},
        "alternative": {"type": "string"},
        "requires_clarification": {"type": "boolean"}
    },
    "required": ["valid", "severity", "reason"]
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
    },
    "required": ["agree"]
})
    
    # 如果复核不同意，使用复核结论
    if not verification["agree"]:
        opinion["analysis"]["severity"] = verification["corrected_severity"]
        opinion["analysis"]["reason"] += f"\n\n【复核补充】{verification['additional_context']}"
    
    opinion["verified"] = True
```

### Gate 2: CR 意见一致性门禁

```python
echo "=== Gate 2: CR 意见一致性门禁 ==="

# 计算一致性率
consensus_rate = sum(
    1 for op in cr_opinions
    if op["analysis"]["valid"] == op["verified"]["agree"]
) / len(cr_opinions) if cr_opinions else 1.0

CONSENSUS_THRESHOLD = 0.8  # 80% 一致性要求

print(f"一致性率: {consensus_rate:.1%} (要求 ≥ {CONSENSUS_THRESHOLD:.0%})")

if consensus_rate < CONSENSUS_THRESHOLD:
    print("❌ Gate 2: 不通过 - CR 意见分析一致性不足")
    print("")
    print("分歧意见清单：")
    for op in cr_opinions:
        if op["analysis"]["valid"] != op["verified"]["agree"]:
            print(f"  - {op['position']['new_path']}:{op['position']['new_line']}")
            print(f"    初步: {'成立' if op['analysis']['valid'] else '不成立'}")
            print(f"    复核: {'同意' if op['verified']['agree'] else '不同意'}")
    print("")
    print("需要人工复核分歧意见")
    exit 1

print("✅ Gate 2: 一致性门禁通过")
print("")
```

**不通过处理**：
- **打回重做** - 输出分歧清单，人工复核，exit 1

### Step 1.3: 独立复核整个 MR

**Agent 3: MR Holistic Reviewer**（整体复核，**完全独立**）

```python
mr_review = agent(f"""
对整个 MR 进行**完全独立**的复核，**忽略已有 CR 意见**，发现所有潜在问题：

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

**重要**：
- 即使某个问题已被 CR 意见指出，如果你独立发现了，仍应列出
- 我们会在后续去重环节处理重复问题
- 你的任务是**穷尽**所有问题，不是"避免重复"

**输出**：发现的所有问题列表
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
                },
                "required": ["file", "line", "severity", "category", "description", "suggestion"]
            }
        }
    },
    "required": ["findings"]
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
1. 这个问题是否真实存在？（不是误判）
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
    },
    "required": ["confirmed", "reason"]
})
    
    finding["verified"] = verification
    if not verification["confirmed"]:
        finding["status"] = "rejected"
    elif verification["adjusted_severity"]:
        finding["severity"] = verification["adjusted_severity"]
```

### Gate 3: 独立复核确认率门禁

```python
echo "=== Gate 3: 独立复核确认率门禁 ==="

# 计算确认率
if mr_review["findings"]:
    confirmation_rate = sum(
        1 for f in mr_review["findings"]
        if f["verified"]["confirmed"]
    ) / len(mr_review["findings"])
else:
    confirmation_rate = 1.0  # 无发现视为通过

CONFIRMATION_THRESHOLD = 0.9  # 90% 确认率（误判率 ≤ 10%）

print(f"确认率: {confirmation_rate:.1%} (要求 ≥ {CONFIRMATION_THRESHOLD:.0%})")

# 检查所有 critical 问题是否都已复核
critical_findings = [f for f in mr_review["findings"] if f["severity"] == "critical"]
critical_verified = all("verified" in f for f in critical_findings)

if confirmation_rate < CONFIRMATION_THRESHOLD:
    print("❌ Gate 3: 不通过 - 确认率不足（误判过多）")
    print("")
    print("被拒绝的发现：")
    for f in mr_review["findings"]:
        if not f["verified"]["confirmed"]:
            print(f"  - {f['file']}:{f['line']} - {f['description']}")
            print(f"    拒绝理由: {f['verified']['reason']}")
    exit 1

if not critical_verified:
    print("❌ Gate 3: 不通过 - critical 问题未全部复核")
    exit 1

print("✅ Gate 3: 确认率门禁通过")
print("")
```

**不通过处理**：
- **打回重做** - 误判过多或 critical 问题未复核，人工介入，exit 1

### Step 1.3.5: 问题去重

```python
echo "=== Step 1.3.5: 问题去重 ==="

def deduplicate_issues(cr_issues, independent_issues):
    """
    基于 file + line + 文本相似度去重
    """
    all_issues = []
    
    # 转换 CR 意见为统一格式
    for op in cr_issues:
        if op["analysis"]["valid"] and op["verified"]:
            all_issues.append({
                "source": "cr_opinion",
                "id": op["id"],
                "file": op["position"]["new_path"],
                "line": op["position"]["new_line"],
                "severity": op["analysis"]["severity"],
                "description": op["body"],
                "suggestion": op["analysis"].get("alternative") or "按 CR 意见修复"
            })
    
    # 转换独立发现为统一格式
    for finding in independent_issues:
        if finding["verified"]["confirmed"]:
            all_issues.append({
                "source": "independent_review",
                "file": finding["file"],
                "line": finding["line"],
                "severity": finding["severity"],
                "description": finding["description"],
                "suggestion": finding["suggestion"]
            })
    
    # 去重逻辑
    deduped = []
    for issue in all_issues:
        # 查找相似问题（同文件、相近行号、描述相似）
        similar = [
            existing for existing in deduped
            if (existing["file"] == issue["file"] and
                abs(existing["line"] - issue["line"]) <= 3 and
                text_similarity(existing["description"], issue["description"]) > 0.85)
        ]
        
        if similar:
            # 合并：取更高的 severity，合并 sources 和 suggestions
            existing = similar[0]
            existing["severity"] = max(
                existing["severity"], issue["severity"],
                key=lambda s: {"critical": 0, "major": 1, "minor": 2, "style": 3}[s]
            )
            existing["sources"].append(issue["source"])
            if issue["suggestion"] not in existing["suggestions"]:
                existing["suggestions"].append(issue["suggestion"])
        else:
            issue["sources"] = [issue["source"]]
            issue["suggestions"] = [issue["suggestion"]]
            deduped.append(issue)
    
    return deduped

# 执行去重
issues_to_fix = deduplicate_issues(cr_opinions, mr_review["findings"])

# 统计
total = len(issues_to_fix)
by_severity = {
    "critical": sum(1 for i in issues_to_fix if i["severity"] == "critical"),
    "major": sum(1 for i in issues_to_fix if i["severity"] == "major"),
    "minor": sum(1 for i in issues_to_fix if i["severity"] == "minor")
}

print(f"✓ 去重完成: {total} 个问题")
print(f"  - Critical: {by_severity['critical']}")
print(f"  - Major: {by_severity['major']}")
print(f"  - Minor: {by_severity['minor']}")
print("")
```

### Step 1.4-1.6: 修复-测试循环（最多 2 轮）

```python
echo "=== Step 1.4-1.6: 修复-测试循环 ==="

MAX_ROUNDS = 2
current_issues = issues_to_fix  # 来自去重后的问题清单

for round_num in range(1, MAX_ROUNDS + 1):
    print(f"=== 修复轮次 {round_num}/{MAX_ROUNDS} ===")
    print("")
    
    # 1. 修复代码
    print("1. 修复代码...")
    fix_results = []
    for issue in current_issues:
        # minor 问题询问用户
        if issue["severity"] == "minor":
            user_choice = ask_user(f"是否修复次要问题：{issue['description']}？")
            if not user_choice:
                issue["skipped"] = True
                print(f"  ⏭️  跳过 minor: {issue['file']}:{issue['line']}")
                continue
        
        print(f"  🔧 修复 {issue['severity']}: {issue['file']}:{issue['line']}")
        fix_result = agent(f"""
实施以下修复：

**问题**: {issue['description']}
**位置**: {issue['file']}:{issue['line']}
**建议**: {', '.join(issue['suggestions'])}
**来源**: {', '.join(issue['sources'])}

**当前代码**:
```
{read_file(issue['file'])}
```

**操作**：
1. 阅读完整文件理解上下文
2. 实施修复
3. 验证修复不引入新问题

使用 Edit 工具修改文件。
""")
        
        issue["fixed"] = True
        fix_results.append(fix_result)
    
    print("")
    
    # 2. 复核修复
    print("2. 复核修复结果...")
    verification = agent(f"""
复核所有修复结果：

**修复清单**:
{json.dumps([{
    "description": issue["description"],
    "file": issue["file"],
    "suggestions": issue["suggestions"]
} for issue in current_issues if issue.get("fixed")])}

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
        "remaining_issues": {"type": "array", "items": {"type": "object"}},
        "introduced_issues": {"type": "array", "items": {"type": "object"}}
    },
    "required": ["all_fixed", "remaining_issues", "introduced_issues"]
})
    
    print(f"  - 全部修复: {verification['all_fixed']}")
    print(f"  - 遗留问题: {len(verification['remaining_issues'])}")
    print(f"  - 新引入问题: {len(verification['introduced_issues'])}")
    print("")
    
    # 3. 编译检查
    print("3. 编译检查...")
    compile_result = subprocess.run(
        ["./gradlew", ":app:shell:assembleCnPhoneDebug", "--build-cache", "--parallel"],
        capture_output=True,
        text=True
    )
    
    if compile_result.returncode != 0:
        print(f"  ❌ 编译失败")
        verification["introduced_issues"].append({
            "type": "compile_error",
            "file": "build",
            "description": f"编译失败: {compile_result.stderr[:200]}"
        })
    else:
        print(f"  ✓ 编译通过")
    print("")
    
    # 4. 跑测试
    print("4. 运行测试...")
    test_result = subprocess.run(
        ["python3", "/home/peng/my-ai-workflows/skills/mai-osbot-test/analyze-and-eval.py",
         "--mr", MR_URL],
        capture_output=True,
        text=True
    )
    
    test_summary = json.loads(test_result.stdout)
    print(f"  - 通过率: {test_summary['pass_rate']:.1%}")
    print(f"  - 通过: {test_summary['passed']}/{test_summary['total']}")
    print(f"  - 新增失败: {len(test_summary['new_failures'])}")
    print("")
    
    # 5. 综合判断
    all_fixed = verification["all_fixed"]
    tests_passed = test_summary["pass_rate"] >= 0.9
    no_new_issues = len(verification["introduced_issues"]) == 0
    
    if all_fixed and tests_passed and no_new_issues:
        print(f"✅ 修复成功（第 {round_num} 轮）")
        print("")
        break
    elif round_num < MAX_ROUNDS:
        # 收集下一轮需要修复的问题
        current_issues = []
        current_issues.extend(verification["remaining_issues"])
        current_issues.extend(verification["introduced_issues"])
        current_issues.extend([
            {
                "type": "test_failure",
                "file": f["case_file"],
                "line": 0,
                "severity": "major",
                "description": f"测试失败: {f['case_id']} - {f['reason']}",
                "suggestion": f["suggestion"]
            }
            for f in test_summary["failures"]
        ])
        print(f"⏳ 发现 {len(current_issues)} 个问题，进入第 {round_num+1} 轮修复")
        print("")
    else:
        # 最后一轮仍失败 → 自动派 agent 分析 + 人工介入
        print(f"❌ {MAX_ROUNDS} 轮修复后仍有问题")
        print(f"  - 未修复问题: {len(verification['remaining_issues'])}")
        print(f"  - 新引入问题: {len(verification['introduced_issues'])}")
        print(f"  - 测试失败: {len(test_summary['failures'])}")
        print("")
        
        # 自动派 agent 分析根因
        print("自动派 agent 分析根因...")
        diagnosis_agents = []
        
        # Agent A: 分析未修复问题
        if verification["remaining_issues"]:
            diagnosis_agents.append(agent(f"""
分析为何以下问题在 {MAX_ROUNDS} 轮修复后仍未解决：

**未修复问题**:
{json.dumps(verification["remaining_issues"])}

**历史修复尝试**:
{git log --oneline -10}

**当前 diff**:
{git diff origin/main...HEAD}

**输出**：
- root_cause: 根本原因
- blocking_factor: 阻塞因素
- recommendation: 建议方案
"""))
        
        # Agent B: 分析新引入问题
        if verification["introduced_issues"]:
            diagnosis_agents.append(agent(f"""
分析修复过程中引入的新问题：

**新问题**:
{json.dumps(verification["introduced_issues"])}

**修复 diff**:
{git diff origin/main...HEAD}

**输出**：
- introduced_by: 哪个修复引入的
- why_missed: 为何复核时未发现
- prevention: 如何避免
"""))
        
        # Agent C: 分析测试失败
        if test_summary["failures"]:
            diagnosis_agents.append(agent(f"""
分析测试失败的根因：

**失败测试**:
{json.dumps(test_summary["failures"])}

**修改内容**:
{git diff origin/main...HEAD}

**输出**：
- pattern: 失败模式（是否系统性失败）
- root_cause: 根本原因
- fix_approach: 修复方向
"""))
        
        # 等待所有 agent 完成
        diagnoses = await_all(diagnosis_agents)
        
        print("")
        print("=== 根因分析 ===")
        for i, diag in enumerate(diagnoses, 1):
            print(f"Agent {i}: {diag}")
        print("")
        
        raise ManualInterventionRequired(
            remaining_issues=verification["remaining_issues"],
            introduced_issues=verification["introduced_issues"],
            test_failures=test_summary["failures"],
            diagnoses=diagnoses
        )
```

### Gate 4: 修复完整性门禁

```python
echo "=== Gate 4: 修复完整性门禁 ==="

# 检查所有 critical 是否修复
critical_issues = [i for i in issues_to_fix if i["severity"] == "critical"]
critical_fixed = all(i.get("fixed") for i in critical_issues)

# 检查所有 major 是否处理
major_issues = [i for i in issues_to_fix if i["severity"] == "major"]
major_handled = all(i.get("fixed") or i.get("skipped") for i in major_issues)

# 检查编译是否通过
compile_success = compile_result.returncode == 0

print(f"Critical 问题: {sum(1 for i in critical_issues if i.get('fixed'))}/{len(critical_issues)} 已修复")
print(f"Major 问题: {sum(1 for i in major_issues if i.get('fixed') or i.get('skipped'))}/{len(major_issues)} 已处理")
print(f"编译状态: {'✓ 通过' if compile_success else '❌ 失败'}")

if not (critical_fixed and major_handled and compile_success):
    print("")
    print("❌ Gate 4: 不通过 - 修复不完整")
    
    if not critical_fixed:
        print("  未修复的 critical 问题:")
        for i in critical_issues:
            if not i.get("fixed"):
                print(f"    - {i['file']}:{i['line']} - {i['description']}")
    
    if not major_handled:
        print("  未处理的 major 问题:")
        for i in major_issues:
            if not (i.get("fixed") or i.get("skipped")):
                print(f"    - {i['file']}:{i['line']} - {i['description']}")
    
    if not compile_success:
        print(f"  编译错误: {compile_result.stderr[:200]}")
    
    exit 1

print("")
print("✅ Gate 4: 修复完整性门禁通过")
print("")
```

**不通过处理**：
- **打回重做** - 递归修复最多 2 轮，仍失败则 exit 1，人工介入

### Gate 5: 测试通过率门禁

```python
echo "=== Gate 5: 测试通过率门禁 ==="

TEST_PASS_RATE_THRESHOLD = 0.9  # 90% 通过率
MAX_NEW_FAILURES = 0  # 不允许新增失败测试

pass_rate = test_summary["pass_rate"]
new_failures = len(test_summary["new_failures"])

print(f"通过率: {pass_rate:.1%} (要求 ≥ {TEST_PASS_RATE_THRESHOLD:.0%})")
print(f"新增失败: {new_failures} (要求 = {MAX_NEW_FAILURES})")

tests_passed = (
    pass_rate >= TEST_PASS_RATE_THRESHOLD and
    new_failures <= MAX_NEW_FAILURES
)

if not tests_passed:
    print("")
    print("❌ Gate 5: 不通过 - 测试门禁失败")
    
    if pass_rate < TEST_PASS_RATE_THRESHOLD:
        print(f"  通过率不足: {pass_rate:.1%} < {TEST_PASS_RATE_THRESHOLD:.0%}")
    
    if new_failures > MAX_NEW_FAILURES:
        print(f"  新增失败测试:")
        for f in test_summary["new_failures"]:
            print(f"    - {f['case_id']}: {f['reason']}")
    
    exit 1

print("")
print("✅ Gate 5: 测试通过率门禁通过")
print("")
```

**不通过处理**：
- **打回重做** - 修复测试失败，最多重试 2 次（已在修复-测试循环中），仍失败则 exit 1

### Step 1.7: 更新 MR

```bash
echo "=== Step 1.7: 更新 MR ==="

# Commit 所有修复
FIXED_CR=$(jq -r '[.[] | select(.analysis.valid and .fixed)] | length' cr-opinions.json)
FIXED_INDEPENDENT=$(echo "$verification" | jq '.remaining_issues | length' | xargs expr $(echo "$verification" | jq '.introduced_issues | length') + | xargs expr ${#issues_to_fix[@]} -)

git add -A
git commit -m "fix: 响应 CR 意见并修复 review 发现的问题

- 修复 CR 意见: $FIXED_CR 个
- 修复独立发现的问题: $FIXED_INDEPENDENT 个
- 测试通过率: ${test_summary[pass_rate]:.1%}

Co-Authored-By: Claude <noreply@anthropic.com>"

# Push
git push origin HEAD

echo "✓ MR 已更新"
echo ""
```

### Step 1.8: Resolve CR 意见 / 请求澄清

```bash
echo "=== Step 1.8: Resolve CR 意见 ==="

# 对于成立且已修复的 CR 意见
for opinion in $(jq -c '.[] | select(.analysis.valid and .fixed)' cr-opinions.json); do
  ID=$(echo "$opinion" | jq -r '.id')
  REASON=$(echo "$opinion" | jq -r '.analysis.reason')
  
  glab mr discussion resolve "$MR_URL" \
    --discussion-id "$ID" \
    --note "✓ 已修复。$REASON"
done

# 对于不成立或需要澄清的 CR 意见
for opinion in $(jq -c '.[] | select((.analysis.valid == false) or .analysis.requires_clarification)' cr-opinions.json); do
  ID=$(echo "$opinion" | jq -r '.id')
  REASON=$(echo "$opinion" | jq -r '.analysis.reason')
  ADDITIONAL=$(echo "$opinion" | jq -r '.verified.additional_context // ""')
  
  glab mr discussion reply "$MR_URL" \
    --discussion-id "$ID" \
    --note "❓ 请求澄清：$REASON

【复核意见】$ADDITIONAL

是否存在我遗漏的场景？"
done

echo "✓ CR 意见响应完成"
echo ""
```

### Step 1.9: 生成完成报告

```markdown
echo "=== Step 1.9: 生成完成报告 ==="

cat <<EOF

# MR 修复完成

**MR**: $MR_URL

## CR 意见响应

### 已修复（$FIXED_CR）
$(jq -r '.[] | select(.analysis.valid and .fixed) | "- ✓ [\(.author)] \(.body[:50])... → \(.analysis.alternative // "按建议修复")"' cr-opinions.json)

### 请求澄清（$(jq '[.[] | select((.analysis.valid == false) or .analysis.requires_clarification)] | length' cr-opinions.json)）
$(jq -r '.[] | select((.analysis.valid == false) or .analysis.requires_clarification) | "- ❓ [\(.author)] \(.body[:50])... → \(.analysis.reason)"' cr-opinions.json)

## 独立复核发现

### 严重问题（$(jq '[.findings[] | select(.severity == "critical" and .verified.confirmed)] | length' mr_review.json)）
$(jq -r '.findings[] | select(.severity == "critical" and .verified.confirmed) | "- 🔴 \(.description) → 已修复"' mr_review.json)

### 主要问题（$(jq '[.findings[] | select(.severity == "major" and .verified.confirmed)] | length' mr_review.json)）
$(jq -r '.findings[] | select(.severity == "major" and .verified.confirmed) | "- 🟡 \(.description) → 已修复"' mr_review.json)

## 测试结果

✓ 测试通过: ${test_summary[passed]}/${test_summary[total]} (${test_summary[pass_rate]:.1%})
✓ 编译通过

## 门禁通过情况

- ✅ Gate 0: 环境门禁
- ✅ Gate 1: 模式识别
- ✅ Gate 2: CR 意见一致性（${consensus_rate:.0%}）
- ✅ Gate 3: 独立复核确认率（${confirmation_rate:.0%}）
- ✅ Gate 4: 修复完整性
- ✅ Gate 5: 测试通过率（${test_summary[pass_rate]:.1%}）

## 后续步骤

1. 等待 CR 意见澄清回复
2. 等待新一轮 review

EOF
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
                    "suggestion": {"type": "string"},
                    "blocking": {"type": "boolean", "const": True}
                },
                "required": ["file", "line", "description", "impact", "suggestion"]
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
                },
                "required": ["file", "line", "description", "suggestion"]
            }
        }
    },
    "required": ["critical_issues", "minor_issues"]
})
```

### Step 2.2: 门禁复核（分严重和次要）

**Agent 8: Review Gatekeeper**（review 门禁复核）

```python
echo "=== Step 2.2: 门禁复核 ==="

downgraded_issues = []  # 跟踪降级问题

# 复核严重问题
for issue in list(adversarial_review["critical_issues"]):  # 复制列表避免迭代时修改
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
3. 是否有快速缓解方案（可降级为非阻塞）？

**输出**：
- approve_publish: true/false（是否批准发表）
- adjusted_severity: 调整后的严重程度（critical/major/minor，如果需要降级）
- reason: 门禁判定理由
""", schema={
    "type": "object",
    "properties": {
        "approve_publish": {"type": "boolean"},
        "adjusted_severity": {"enum": ["critical", "major", "minor", null]},
        "reason": {"type": "string"}
    },
    "required": ["approve_publish", "reason"]
})
    
    issue["gate_checked"] = gate_check
    
    if not gate_check["approve_publish"]:
        issue["status"] = "rejected_by_gate"
    elif gate_check["adjusted_severity"] and gate_check["adjusted_severity"] != "critical":
        # 降级处理
        issue["status"] = "downgraded"
        issue["original_severity"] = "critical"
        issue["adjusted_severity"] = gate_check["adjusted_severity"]
        downgraded_issues.append(issue)

# **关键**：从 critical_issues 中移除已降级/拒绝的
adversarial_review["critical_issues"] = [
    i for i in adversarial_review["critical_issues"]
    if i.get("status") not in ["rejected_by_gate", "downgraded"]
]

# 复核次要问题
for issue in adversarial_review["minor_issues"]:
    gate_check = agent(f"""
门禁复核次要问题：

**问题**: {issue.description}
**建议**: {issue.suggestion}
**位置**: {issue.file}:{issue.line}

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
    },
    "required": ["approve_publish", "reason"]
})
    
    issue["gate_checked"] = gate_check
    if not gate_check["approve_publish"]:
        issue["status"] = "rejected_by_gate"

# 合并降级问题到 minor_issues
adversarial_review["minor_issues"].extend(downgraded_issues)

echo "✓ 门禁复核完成"
echo ""
```

### Gate 6: Review 发表质量门禁

```python
echo "=== Gate 6: Review 发表质量门禁 ==="

# 检查所有意见都经过门禁复核
critical_gated = all(
    "gate_checked" in issue
    for issue in adversarial_review["critical_issues"]
)

minor_gated = all(
    "gate_checked" in issue
    for issue in adversarial_review["minor_issues"]
)

# 至少有一个可发表的意见
publishable_critical = [
    i for i in adversarial_review["critical_issues"]
    if i.get("gate_checked", {}).get("approve_publish")
]

publishable_minor = [
    i for i in adversarial_review["minor_issues"]
    if i.get("gate_checked", {}).get("approve_publish")
]

has_publishable = len(publishable_critical) + len(publishable_minor) > 0

print(f"Critical 意见: {len(publishable_critical)}/{len(adversarial_review['critical_issues'])} 可发表")
print(f"Minor 意见: {len(publishable_minor)}/{len(adversarial_review['minor_issues'])} 可发表")

if not (critical_gated and minor_gated):
    print("")
    print("❌ Gate 6: 不通过 - 存在未复核的意见")
    exit 1

if not has_publishable:
    print("")
    print("⚠️  Gate 6: 无有效 review 意见可发表")
    print("（所有意见都被门禁拒绝，可能过于吹毛求疵或误判）")
    exit 0  # 不是错误，只是无意见

print("")
print("✅ Gate 6: Review 发表质量门禁通过")
print("")
```

**不通过处理**：
- **降级处理** - 不符合标准的意见被过滤，不发表
- 如果全部被过滤则输出"无有效 review 意见"，exit 0

### Step 2.3: 发表 review 意见

```bash
echo "=== Step 2.3: 发表 review 意见 ==="

# 发表严重问题（行内 blocking discussion）
echo "发表严重问题..."
for issue in $(echo "$publishable_critical" | jq -c '.[]'); do
  FILE=$(echo "$issue" | jq -r '.file')
  LINE=$(echo "$issue" | jq -r '.line')
  DESC=$(echo "$issue" | jq -r '.description')
  IMPACT=$(echo "$issue" | jq -r '.impact')
  SUGGESTION=$(echo "$issue" | jq -r '.suggestion')
  GATE_REASON=$(echo "$issue" | jq -r '.gate_checked.reason')
  
  glab mr discussion create "$MR_URL" \
    --file "$FILE" \
    --line "$LINE" \
    --blocking \
    --note "🔴 【严重问题】$DESC

**影响**: $IMPACT

**建议**: $SUGGESTION

【门禁复核】$GATE_REASON"
done

# 汇总发表次要问题
echo "发表次要问题汇总..."

MINOR_SUMMARY=$(cat <<EOF
## 次要问题汇总（非阻塞）

以下问题不阻塞 MR，但建议考虑优化：

$(for issue in $(echo "$publishable_minor" | jq -c '.[]'); do
  FILE=$(echo "$issue" | jq -r '.file')
  LINE=$(echo "$issue" | jq -r '.line')
  DESC=$(echo "$issue" | jq -r '.description')
  SUGGESTION=$(echo "$issue" | jq -r '.suggestion')
  RECOMMEND_ISSUE=$(echo "$issue" | jq -r '.gate_checked.recommend_issue')
  ORIGINAL_SEVERITY=$(echo "$issue" | jq -r '.original_severity // ""')
  
  echo ""
  echo "### $FILE:$LINE"
  echo ""
  [[ "$ORIGINAL_SEVERITY" == "critical" ]] && echo "**注**: 原为严重问题，经复核降级为次要问题"
  echo ""
  echo "$DESC"
  echo ""
  echo "**建议**: $SUGGESTION"
  echo ""
  [[ "$RECOMMEND_ISSUE" == "true" ]] && echo "💡 建议开 issue 跟进：$DESC"
  echo ""
  echo "---"
done)

**说明**: 以上问题均不阻塞本 MR merge，可在后续优化。
EOF
)

glab mr comment "$MR_URL" --note "$MINOR_SUMMARY"

echo "✓ Review 意见发表完成"
echo ""
```

### Step 2.4: 生成 review 报告

```markdown
echo "=== Step 2.4: 生成 review 报告 ==="

cat <<EOF

# MR Review 完成

**MR**: $MR_URL
**作者**: ${MR_INFO[author]}

## Review 结果

### 严重问题（${#publishable_critical[@]}）🔴 阻塞 merge

$(for issue in "${publishable_critical[@]}"; do
  echo "- [${issue[file]}:${issue[line]}] ${issue[description]}"
done)

### 次要问题（${#publishable_minor[@]}）🟡 非阻塞

$(for issue in "${publishable_minor[@]}"; do
  echo "- [${issue[file]}:${issue[line]}] ${issue[description]}"
  [[ "${issue[gate_checked][recommend_issue]}" == "true" ]] && echo "  💡 建议开 issue 跟进"
done)

### 门禁复核统计

- 严重问题: ${#publishable_critical[@]} 发表 / $(echo "${adversarial_review[critical_issues]}" | jq 'length') 发现 / $(expr $(echo "${adversarial_review[critical_issues]}" | jq 'length') - ${#publishable_critical[@]}) 被门禁拒绝
- 次要问题: ${#publishable_minor[@]} 发表 / $(echo "${adversarial_review[minor_issues]}" | jq 'length') 发现 / $(expr $(echo "${adversarial_review[minor_issues]}" | jq 'length') - ${#publishable_minor[@]}) 被门禁拒绝

### 已发表意见

- 行内 discussion: ${#publishable_critical[@]} 个（严重问题）
- 汇总评论: 1 条（包含 ${#publishable_minor[@]} 个次要问题）

## 门禁通过情况

- ✅ Gate 0: 环境门禁
- ✅ Gate 1: 模式识别
- ✅ Gate 6: Review 发表质量

## 建议

$(if [[ ${#publishable_critical[@]} -gt 0 ]]; then
  echo "❌ 建议暂不 approve，待修复严重问题后重新 review"
else
  echo "✅ 无严重问题，建议 approve（次要问题可后续优化）"
fi)

EOF
```

---

## 会话级偏好配置（可选）

可在工作流启动时询问用户偏好，记录到会话上下文：

```python
# 询问会话偏好
preferences = AskUserQuestion({
    "questions": [
        {
            "question": "是否自动修复 minor 问题？",
            "header": "Minor 修复",
            "multiSelect": False,
            "options": [
                {"label": "询问后修复 (Recommended)", "description": "每个 minor 问题都询问用户"},
                {"label": "自动修复", "description": "全部自动修复，不询问"},
                {"label": "全部跳过", "description": "只修复 critical 和 major"}
            ]
        },
        {
            "question": "修复失败时是否自动派 agent 分析？",
            "header": "自动诊断",
            "multiSelect": False,
            "options": [
                {"label": "是 (Recommended)", "description": "自动派 agent 并行调查根因"},
                {"label": "否", "description": "只展示错误信息，由我手动分析"}
            ]
        },
        {
            "question": "最大修复轮次？",
            "header": "重试次数",
            "multiSelect": False,
            "options": [
                {"label": "2 轮 (Recommended)", "description": "默认配置，平衡速度和成功率"},
                {"label": "1 轮", "description": "快速模式，一次失败就人工介入"},
                {"label": "3 轮", "description": "激进模式，多次尝试"}
            ]
        }
    ]
})

# 记录到会话上下文
AUTO_FIX_MINOR = preferences["Minor 修复"] == "自动修复"
SKIP_MINOR = preferences["Minor 修复"] == "全部跳过"
AUTO_DIAGNOSE = preferences["自动诊断"] == "是"
MAX_ROUNDS = int(preferences["重试次数"].split()[0])
```

---

## 错误处理

### 环境类错误
- **现象**: glab 未认证、git 仓库有未提交变更、缺少工具
- **处理**: Gate 0 拦截，输出修复指引，exit 1

### API 调用失败
- **现象**: glab API 返回错误、网络超时
- **处理**: 指数退避重试 3 次，仍失败则 exit 1

### 门禁失败
- **现象**: 一致性率不足、确认率不足、修复不完整、测试不通过
- **处理**: **打回重做** - 输出详细失败信息，人工介入，exit 1

### 递归修复失败
- **现象**: MAX_ROUNDS 轮后仍有问题
- **处理**: 自动派 agent 分析根因，输出诊断报告，人工介入，exit 1

---

## 依赖

- **环境**: glab (GitLab CLI), jq, git
- **项目 skill**: `mai-osbot-test` - 测试用例执行
- **MCP**: `mi-adt`（可选，用于关联 IPD）
- **Workflow**: 使用子 agent 实现并行分析和复核

---

## 配置

可通过环境变量自定义：

```bash
# 门禁标准
export CONSENSUS_THRESHOLD=0.8       # CR 意见一致性要求（80%）
export CONFIRMATION_THRESHOLD=0.9    # 独立复核确认率要求（90%）
export TEST_PASS_RATE_THRESHOLD=0.9  # 测试通过率要求（90%）
export MAX_NEW_FAILURES=0            # 允许的新增失败测试数（0）

# 修复策略
export MAX_ROUNDS=2                  # 最大修复轮次（2）
export AUTO_FIX_MINOR=false          # 是否自动修复 minor 问题
export AUTO_DIAGNOSE=true            # 失败时是否自动派 agent 分析

# 重试策略
export API_MAX_RETRIES=3             # API 调用最大重试次数
export API_RETRY_BACKOFF=2           # 指数退避基数（秒）
```
