---
name: mai-osbot-test
description: |
  OSBot 测试缺口探测与执行编排。双阶段工作：(1) Analyze - 分析 MR 变更、探测测试缺口、设计测试覆盖、独立复核完备性；(2) Eval - 统一执行测试清单、生成测试报告、更新 MR 评论。
  触发词："测试分析"、"测试缺口"、"跑测试"、"测试这个 MR"、"验证修复"。
---

# OSBot 测试编排 (mai-osbot-test)

**核心定位**：测试缺口探测器 + 用例设计器 + 执行编排器

针对特定 MR/功能/修复，自动分析测试缺口，设计测试覆盖，执行多级门禁，产出完备的测试报告。

---

## 🎯 双阶段架构

### 阶段 1: Analyze（分析与设计）

**输入**：
- MR URL / IPD ID
- 代码变更 diff
- 修复描述

**处理流程**：
```
1. Change Analyzer   → 识别变更类型、范围、关键修改点
2. Gap Detector      → 检测单元测试、eval case、smoke 覆盖缺口
3. Test Designer     → 设计测试用例、确定验证点、定义硬判据
4. Compliance Checker→ 独立复核覆盖度、门禁层级、回归防护
```

**输出**：测试清单（Test Plan JSON）

### 阶段 2: Eval（执行与报告）

**输入**：Analyze 阶段的测试清单

**处理流程**：
```
1. Test Executor     → 按门禁层级执行（unit → eval → smoke）
2. Result Collector  → 收集测试结果、断言状态、执行时长
3. Report Generator  → 生成测试报告
4. MR Updater        → 将报告更新到 MR 评论
```

**输出**：测试报告 + MR 评论

---

## 📋 使用方式

### 方式 1：完整流程（推荐）

```bash
# 自动分析 + 执行 + 报告
mai-osbot-test analyze-and-eval --mr https://git.../osbot/-/merge_requests/6278
```

**流程**：
1. Analyze: 分析 MR 6278 的变更
2. Detect: 探测测试缺口
3. Design: 设计测试覆盖
4. Compliance: 复核完备性
5. Eval: 执行测试清单
6. Report: 更新 MR 评论

### 方式 2：分步执行

```bash
# 步骤 1: 仅分析
mai-osbot-test analyze --mr https://git.../6278 --output test-plan.json

# 步骤 2: 复核测试计划（可选）
cat test-plan.json

# 步骤 3: 执行测试
mai-osbot-test eval --plan test-plan.json --output test-report.json

# 步骤 4: 更新 MR
mai-osbot-test report --mr https://git.../6278 --report test-report.json
```

### 方式 3：自然语言触发

用户："帮我测试一下 MR 6278"

Claude 自动：
1. 识别 MR URL
2. 调用 `mai-osbot-test analyze-and-eval`
3. 输出测试报告摘要

---

## 🔍 Analyze 阶段详解

### 模块 1: Change Analyzer（变更分析器）

**识别变更类型**：
- `bugfix` → 测试重点：验证修复有效性 + 防回归
- `feature` → 测试重点：功能完整性 + 边界情况
- `refactor` → 测试重点：行为一致性 + 性能

**识别变更范围**：
```python
# 基于文件路径识别
"interconnect/" → cross-device
"agent/" → agent-behavior
"tools/" → tool-logic
"llm/" → llm-routing
```

**提取关键修改点**：
- 新增函数/类
- 修改的核心逻辑
- 新增的依赖

### 模块 2: Gap Detector（缺口探测器）

**检测维度**：

**1. 单元测试缺口**
```python
# 检查规则
for modified_file in change.modified_files:
    test_file = find_corresponding_test(modified_file)
    if not test_file:
        gap = "缺少单元测试文件"
    elif test_coverage(test_file) < 80:
        gap = "单元测试覆盖率不足"
```

**2. Eval Case 缺口**
```python
# 检查规则
scope = change.scope  # e.g., "interconnect"
keywords = extract_keywords(change.description)  # e.g., ["duplicate", "file"]

existing_cases = glob(f"eval/cases/{scope}/*")
matched = [c for c in existing_cases if any(k in c for k in keywords)]

if not matched:
    gap = f"缺少 {scope} 的 eval case（关键词：{keywords}）"
```

**3. Smoke 覆盖缺口**
```python
# 检查规则
if change.type == "bugfix" and not in_smoke_suite(change.scope):
    gap = "修复未纳入 smoke 回归集"
```

### 模块 3: Test Designer（测试设计器）

**设计 Eval Case**：

**输入**：变更分析结果

**输出**：Eval Case 设计（YAML 结构）

**设计规则**：
```python
def design_eval_case(change: ChangeAnalysis) -> EvalCaseDesign:
    # 1. Case ID: {scope}-{feature-slug}
    case_id = f"{change.scope}-{slugify(change.key_feature)}"
    
    # 2. Setup: 根据修复类型确定前置条件
    if "db" in change.dependencies:
        setup.add("db_inject", ...)
    if "file" in change.dependencies:
        setup.add("files", ...)
    
    # 3. Validation: 从关键修改点提取验证点
    for key_change in change.key_changes:
        validation = extract_validation(key_change)
        validations.append(validation)
    
    # 4. Assertions: 定义硬判据
    for validation in validations:
        assertion = define_hard_assertion(validation)
        assertions.append(assertion)
    
    return EvalCaseDesign(...)
```

**硬判据设计原则**：
- ✅ 可机器验证（正则匹配、字段存在性、数值比较）
- ✅ 明确 PASS/FAIL（无模糊判断）
- ✅ 可复现（确定性 setup）

### 模块 4: Compliance Checker（合规复核器）

**复核标准**：

| 维度 | 标准 | 理由 |
|------|------|------|
| 单元测试覆盖率 | ≥ 80% | 确保核心逻辑被测试 |
| 门禁层级 | ≥ 3 层 | unit + eval + smoke |
| 硬判据 | 100% 覆盖 | 所有验证点必须有明确判据 |
| 回归防护 | 必需 | bugfix 必须有 smoke 测试 |
| **真机集成测试** | 按规则判定 | 自动化无法覆盖的场景 |

**复核输出**：
```json
{
  "compliant": true,
  "issues": [],
  "recommendations": [
    "建议将 eval case 纳入 smoke 集"
  ],
  "integration_test_required": {
    "required": true,
    "type": "osbot-eval-cross-device",
    "reason": "跨设备文件传输修改，需验证真实网络传输链路"
  }
}
```

---

### 模块 4.1: Integration Test Decider（真机集成测试判定器）

**职责**：判定是否需要真机集成测试，以及使用哪种测试手段

#### **判定规则（决策树）**

```
修改类型判定
│
├─ 协议解析纯逻辑？
│  └─ YES → Unit Test 足够 ✅
│
├─ 跨设备通信/文件传输？
│  ├─ 需要 LLM 决策？
│  │  └─ YES → osbot-eval + RC/XDEV（双重验证）🔴
│  └─ NO → RC/XDEV 足够 🟡
│
├─ 单端 Tool 工具？
│  ├─ 有副作用（电话/短信/智能家居/删除数据）？
│  │  └─ YES → 隔离环境 + 人工验证 🔴
│  └─ NO → osbot-eval 自动化 🟡
│
├─ Agent 路由/Skill 加载？
│  └─ osbot-eval（必须有对应 case）🟡
│
├─ Memory 读写？
│  └─ osbot-eval memory category case 🟡
│
├─ Permission guard？
│  └─ osbot-eval + RC（权限门交互）🟡
│
├─ UI 层/用户交互？
│  └─ 人工真机 + 录屏 🔴
│
└─ 资源文件（prompt/strings）？
   └─ osbot-eval（验证 LLM 理解）🟡
```

#### **测试能力矩阵**

| 维度 | osbot-eval | RC | XDEV | sidekick-talk | Unit Test |
|------|-----------|-----|------|---------------|-----------|
| **单端工具调用** | ✅ | ❌ | ❌ | ❌ | 部分 |
| **LLM 决策路由** | ✅ | ❌ | ❌ | ✅ | ❌ |
| **跨设备通信** | ❌ | ✅ | ✅ | ❌ | ❌ |
| **文件传输全链路** | ❌ | 部分 | ✅ | ❌ | ❌ |
| **权限门交互** | ✅ | ✅ | ❌ | ✅ | ❌ |
| **Chaos 注入** | ❌ | ❌ | ✅ | ❌ | ❌ |
| **自动化断言** | ✅ | ✅ | ✅ | ❌ | ✅ |
| **5min 冒烟门禁** | ✅ | ❌ | ❌ | ❌ | ✅ |
| **设备要求** | 1 手机 | 1手机+1PC | 1手机+1PC | 1 手机 | 0 |
| **判据硬度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |

#### **必须真机验证的修改类型**

| 优先级 | 修改类型 | 必须验证方式 | 理由 |
|-------|---------|-------------|------|
| **P0** | **跨设备通信协议** | RC + XDEV | 单端无法验证双端状态机 |
| **P0** | **文件传输链路** | XDEV | 真实网络/云端依赖 |
| **P0** | **Tool 工具实现** | osbot-eval | LLM 调用行为需真实验证 |
| **P0** | **Agent 路由逻辑** | osbot-eval | LLM 路由决策难 mock |
| **P1** | **Permission guard** | osbot-eval + RC | 需真实权限栈 |
| **P1** | **Skill 加载/路由** | osbot-eval | 依赖真实 assets 文件 |
| **P1** | **Memory 读写** | osbot-eval memory case | 真实文件系统行为 |
| **P2** | **UI 层** | 人工真机 | UI 交互自动化成本高 |
| **P2** | **资源文件** | osbot-eval | 验证 LLM 理解无偏差 |
| **P3** | **协议解析纯逻辑** | Unit Test 足够 | 确定性逻辑 |

#### **自动化测试不够的场景**

1. **UI 跳转后的用户操作**
   - 场景：Agent 跳转到系统设置页，用户需手动开启权限
   - 验证方式：人工测试 + 操作录屏

2. **极端长上下文压缩行为**
   - 场景：数千轮对话后的上下文管理
   - 验证方式：压测环境 + 抽样人工检查

3. **LLM 主观语言质量**
   - 场景：对话自然度、礼貌性、用户体验
   - 验证方式：人工评测 + A/B Test

4. **跨设备 A2A 防死循环**
   - 场景：设备 A 派任务给设备 B，B 又派回 A
   - 验证方式：多设备真机联调

5. **MCP 外部服务稳定性**
   - 场景：第三方 MCP 服务（高德/百度地图）
   - 验证方式：宽松断言 + 人工抽查

6. **副作用类操作**
   - 场景：真打电话/发短信/控制智能家居/删除用户数据
   - 验证方式：隔离测试环境 + 人工验证

#### **判定输出**

**格式**：
```json
{
  "integration_test_required": true,
  "test_strategy": {
    "primary": "osbot-eval-cross-device",
    "secondary": ["osbot-eval"],
    "manual": false
  },
  "reason": "跨设备文件传输修改，需验证真实网络传输链路",
  "test_matrix": {
    "cases_required": [
      "xdev-file-transfer-duplicate-names",
      "xdev-chaos-disconnect-during-upload"
    ],
    "estimated_time": "20-30 min",
    "devices_required": "1 手机 + 1 PC"
  },
  "manual_test_checklist": null
}
```

#### **人工测试矩阵生成**

当判定需要人工测试时，自动生成测试矩阵：

```markdown
## 人工真机测试矩阵

### 测试场景：跨端文件转发 - 同名文件处理

| 编号 | 前置条件 | 操作步骤 | 预期结果 | 实际结果 | 状态 |
|------|---------|---------|---------|---------|------|
| TC-01 | 手机已有 `合同.pdf` | PC 回传同名 `合同.pdf` | 手机保存为 `合同 (1).pdf` | | ⏳ |
| TC-02 | TC-01 完成 | 语音："把合同发到平板" | 平板收到 `合同 (1).pdf`（新版本） | | ⏳ |
| TC-03 | TC-01 完成 | LLM 错误使用无后缀路径 | remote_file 工具拒绝，返回 `[STALE_LOCAL_FILE]` | | ⏳ |

### 验证命令

```bash
# TC-01: 验证文件重命名
adb shell "ls -lh /sdcard/Documents/XiaoAi/*.pdf"
# 预期：合同.pdf + 合同 (1).pdf

# TC-02: 验证平板收到新文件
ANDROID_SERIAL=<平板> adb shell "cat /sdcard/Documents/XiaoAi/合同.pdf"
# 预期：新版本内容

# TC-03: 验证拦截日志
adb logcat -s "RemoteFileTool:*" | grep "\[STALE_LOCAL_FILE\]"
```

### 测试数据

```bash
# 准备测试文件
echo "历史旧版本" > /tmp/合同.pdf
echo "新回传版本" > /tmp/合同-new.pdf
```
```

---

## 🏃 Eval 阶段详解

### 模块 5: Test Executor（测试执行器）

**执行流程**：

**门禁 Level 1: 单元测试**
```bash
./gradlew test --tests <test_class>
```
- 失败 → 停止，报告 "单元测试未通过"
- 通过 → 继续

**门禁 Level 2: 集成测试（Eval Cases）**
```bash
python .claude/skills/osbot-eval/eval.py --run-one <case_id>
```
- 失败 → 停止，报告 "集成测试未通过"
- 通过 → 继续

**门禁 Level 3: Smoke 回归**
```bash
python .claude/skills/osbot-eval/eval.py --smoke
```
- 失败 → 报告 "回归测试失败"
- 通过 → 报告 "所有门禁通过 ✅"

### 模块 6: Report Generator（报告生成器）

**报告结构**：

```markdown
## 测试报告 - MR 6278

**执行时间**: 2026-08-15 15:30:00  
**总体状态**: ✅ PASS

### 门禁 Level 1: 单元测试
- **状态**: ✅ PASS
- **通过**: 42 / 42
- **耗时**: 2m15s

### 门禁 Level 2: 集成测试
- **状态**: ✅ PASS
- **用例**: interconnect-send-task-duplicate-file-names
- **断言**:
  - ✅ remote_file 工具被调用
  - ✅ paths 参数匹配序号后缀模式
  - ✅ 未使用无后缀路径
- **耗时**: 2m30s

### 门禁 Level 3: Smoke 回归
- **状态**: ✅ PASS
- **通过**: 50 / 50
- **耗时**: 5m20s

### 建议
✅ 所有门禁通过，建议 approve MR
```

---

## 📊 测试策略地图

| 变更类型 | 测试重点 | 门禁层级 |
|---------|---------|---------|
| **bugfix** | 验证修复 + 防回归 | unit (必需) + eval (推荐) + smoke (必需) |
| **feature** | 功能完整性 + 边界 | unit (必需) + eval (必需) + smoke (可选) |
| **refactor** | 行为一致性 + 性能 | unit (必需) + smoke (必需) |
| **perf** | 性能指标 + 回归 | unit (可选) + perf (必需) + smoke (必需) |

---

## 🔧 依赖工具

### 底层测试引擎（委托执行）
- `osbot-eval` - 单端 eval 引擎
- `osbot-eval-remote-control` - 双端 RC 测试
- `osbot-eval-cross-device` - 双端 XDEV 测试
- `gradle` - JVM 单元测试
- `node` - JS CLI 测试

### 辅助工具
- `eval/helpers/db_injector.py` - 数据库注入
- `sidekick-talk` - 真机消息发送
- `mai-env-doctor` - 环境门禁

---

## 🎯 设计原则

1. **只做分析和编排，不重复实现引擎**
   - 执行委托给 osbot-eval / gradle / node
   
2. **硬判据优先**
   - 所有验证点必须有明确的 PASS/FAIL

3. **多层门禁**
   - unit → eval → smoke，门禁失败立即停止

4. **自动化优先，手工兜底**
   - 优先设计自动化测试
   - 无法自动化时输出测试指南（Playbook）

5. **独立复核**
   - Compliance Checker 独立验证测试完备性

---

## 📚 示例

### 示例 1: 分析 IPD 847472

```
用户: "帮我测试 MR 6278"

mai-osbot-test:
  1. Analyze MR 6278
  2. Detect gaps:
     - ✅ 单元测试充分
     - ⚠️ 缺少 eval case
     - ✅ 在 smoke 集中
  3. Design eval case: send-task-duplicate-file-names.yaml
  4. Compliance check: ✅ 覆盖完备
  5. Eval:
     - Level 1 (unit): PASS
     - Level 2 (eval): PASS
     - Level 3 (smoke): PASS
  6. Report: 更新 MR 6278 评论
```

### 示例 2: 仅分析不执行

```bash
mai-osbot-test analyze --mr https://git.../6278

# 输出 test-plan.json
{
  "gaps": [
    {
      "type": "eval_case",
      "description": "缺少同名文件路径验证的 eval case",
      "priority": "P0",
      "recommendation": "创建 send-task-duplicate-file-names.yaml"
    }
  ],
  "test_plan": {
    "level_1": ["RemoteFileToolTest", "SendTaskToDeviceToolTest"],
    "level_2": ["interconnect-send-task-duplicate-file-names"],
    "level_3": ["smoke suite"]
  }
}
```

---

## ⚠️ 限制

1. **仅支持 osbot 项目**
   - 前置：在 osbot 仓库目录内运行

2. **依赖底层引擎**
   - osbot-eval / gradle 必须可用

3. **不替代 QA**
   - 研发视角的测试覆盖（快速反馈 + 硬判据）
   - QA 负责完整测试覆盖和探索性测试

## 依赖

- 项目: osbot 仓库 - 测试代码和用例
- CLI: `gradle` - 编译和测试执行
- Skills: `osbot-eval` - 用例执行引擎
- 工具: `adb` - Android 设备连接（双端测试）
