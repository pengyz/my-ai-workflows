---
name: mai-osbot-test
description: |
  OSBot 统一测试编排。按场景路由到正确的测试引擎（osbot-eval 单端行为 / smoke 提交门禁 /
  双端 RC-XDEV / JS CLI 单测 / jvm 离线），先做环境门禁（含 Linux 可行性说明）再执行，
  统一归一各引擎结果并对接 mr-preflight MR 门禁。
  触发词："跑测试"、"跑 eval"、"测试一下"、"smoke"、"冒烟"、"回归验证"、"双端联测"、"测试哪个引擎"。
  legacy 提示：app:shell / app:headless 已过时，主 app 为 sidekick-ui。
---

# OSBot 测试编排 (mai-osbot-test)

统一测试入口。**只做路由/门禁/归一，不重复实现引擎**——具体执行委托给 osbot 项目内的引擎 skill（osbot-eval / osbot-eval-remote-control / osbot-eval-cross-device）。

**前置**：在 osbot 仓库目录内运行（或设置 `OSBOT_PATH` 环境变量指向 osbot 仓库，见 `mai-env-doctor`）。

## 测试基础设施地图

| 层 | 引擎 | 被测对象 | 产出 |
|----|------|---------|------|
| 真机 Agent eval | `.claude/skills/osbot-eval/eval.py` | **主 app sidekick-ui**（com.miui.voiceassist） | `eval/results/<ts>/{report.json, report.html, eval-summary.json}` |
| 双端协议 e2e | osbot-eval-remote-control / osbot-eval-cross-device | 手机 sidekick + PC miclaw_desktop | 各自 sessions dump |
| JS CLI 单测 | `node scripts/tests/run-all-tests.mjs`（32 个） | `app/core` 的 bash-scripts CLI 命令 | mjs 汇总 |
| JVM 单测 | gradle `:app:core:jsTest` / unit-test | Kotlin 逻辑 | gradle 报告 |
| 离线 mock | `eval.py --target jvm` | osbot-server.jar（无设备） | 同上 eval 报告 |

## 场景路由（第一步：判断用户意图）

| 用户意图 | 路由到 | 命令 |
|---------|--------|------|
| 提交前门禁 | **smoke 100% PASS** | `python .claude/skills/osbot-eval/eval.py --smoke`（~5min，exit 0/1） |
| 单端行为验证（主 app） | osbot-eval，默认 sidekick-session | `eval.py --run-one <case-id>` / `--filter <pattern>` / `--set <suite>` |
| 真 UI 渲染验证 | osbot-eval `--target sidekick-ui` | `eval.py --set <suite> --target sidekick-ui` |
| CLI 命令逻辑 | JS CLI 测试 | `node scripts/tests/run-all-tests.mjs` |
| 双端远控 e2e | osbot-eval-remote-control | 按该 skill 流程（需双端在线） |
| 双端文件传输 e2e | osbot-eval-cross-device | 按该 skill 流程（需双端在线，无 LLM） |
| 多设备并行回归 | headless_smoke_rounds | ⚠️ **legacy**（见下） |
| 无设备离线 | osbot-eval `--target jvm` | `eval.py --set <suite> --target jvm` |
| 联调操作（发消息/consent/上传） | sidekick-talk / osbot-talk | 各自 CLI；**发消息前先做设备发现与寻址**（见下） |

> **多设备/给任意在线设备发消息**：先按 `sidekick-talk` 的「设备发现与寻址」章节建立 **设备名-suid-在线状态-adb device id 四元组图谱**（`adb devices -l` + 每台设备查询「我有哪些云端在线设备」），再以 `ANDROID_SERIAL` 寻址目标设备发消息。
| trace 查看 | osbot-trace-viz | 按该 skill |

## 环境门禁（执行前必做，复用 mai-env-doctor 模式）

按路由结果检查目标引擎的前置条件，输出 ✅/⚠️/❌，❌ 时给出修复动作（详见 `mai-env-doctor` skill）：

1. **通用**：`python3`（≥3.10）、`PyYAML`、`adb` 可用
2. **单端 smoke/eval（sidekick-session / sidekick-ui）**：adb 在线设备 ≥1、`com.miui.voiceassist` debug APK 已装（`setup.py check` 可查 osbot 路径）
3. **双端 RC/XDEV**：USB adb 手机 + **运行中的 miclaw dev 实例**（`cd miclaw_desktop && npm run electron:dev`，写 `$TMPDIR/rc-dev-driver.json`）+ MiTalk 同账号在线配对
4. **JS CLI 测试**：node ≥18
5. **jvm 离线**：`app/jvm-runner` 已构建，无设备要求
6. **legacy 引擎**（shell / headless）：命中即提示过时并询问是否改用主 target

**Linux 可行性**（本 skill 全部引擎在 Linux 可运行）：

| 引擎 | Linux | 说明 |
|------|-------|------|
| osbot-eval（单端/jvm） | ✅ | python3 + adb；jvm 完全免设备 |
| JS CLI / JVM 单测 | ✅ | 无设备 |
| sidekick-talk / osbot-talk | ✅ | 纯 bash + adb |
| RC / XDEV（双端） | ✅（条件） | 需本机跑 miclaw dev 实例（Electron 跨平台）+ USB adb；不依赖 Windows 原生互联 |
| headless（legacy） | ✅ | 需旧 headless APK 设备 |

**Windows**：Python 脚本 `python .../eval.py`；bash 命令用 Git Bash 或 PowerShell 等价（双平台约定见各引擎 skill）。

## 结果归一

执行完向用户统一汇报，格式：

```markdown
## 测试结果 (<引擎名>)

- **目标**: sidekick-ui / <case-set>
- **结果**: <passed>/<total> (<pass_rate>)
- **关键失败**: <case-id>: <失败摘要>（详见 <report 路径>）
- **产物**: <report.json / eval-summary.json / mjs 汇总路径>
```

各引擎产物位置：
- osbot-eval / jvm：`eval/results/<ts>/`（`report.json` + `eval-summary.json` + `sessions/<case-id>/`）
- JS CLI：`scripts/tests/` runner 汇总输出
- RC / XDEV：各自 skill 的 sessions 目录

## MR 门禁对接

提交前（配合 `osbot-mr-preflight` skill）：
- 必跑 `eval.py --smoke` 且 100% PASS
- 变更命中 trace 门禁路径（`**/agent/**`、`**/tools/**`、`**/llm/**`、`**/assets/agents/**`、`**/assets/prompts/**`、`**/assets/tool_overlays.json`）→ 用 `osbot-trace-viz` 取 trace 证据
- Agent 行为修复 / 新意图 / 工具路由改动 → 需补 eval case（`eval/cases/`，schema 校验：`validate_cases.py`）

## legacy 标注（2026-08 确认）

| 模块 | 状态 | 说明 |
|------|------|------|
| `app:shell`（miclaw-ui，com.aios.osbot） | ⚠️ 过时 | 独立聊天 UI 已被 sidekick-ui 取代；`--target shell` 仅历史用例使用 |
| `app:headless`（server/pilot） | ⚠️ 过时 | headless APK / CliTransportService socket 路径（`--target headless/auto`）已废弃；osbot-headless-eval 的用例不再新增 |
| **`:mainApp`（sidekick-ui，com.miui.voiceassist）** | ✅ **当前主 app** | 默认 target = `sidekick-session`（内嵌 osbot 进程），真 UI 用 `sidekick-ui` |

路由时默认走主 app target；用户明确要求旧模块时才走 legacy，且先提示过时。

## 依赖

- 环境: `mai-env-doctor` / `setup.py` - 环境门禁与检查
- 项目 skill: `osbot-eval` - 单端 eval 引擎（路由目标）
- 项目 skill: `osbot-eval-remote-control` / `osbot-eval-cross-device` - 双端引擎（路由目标）
- 项目 skill: `osbot-mr-preflight` / `osbot-trace-viz` - MR 门禁对接
- 项目 skill: `sidekick-talk` / `osbot-talk-to-osbot` - 联调操作（路由目标）
- CLI: `adb`、`python3`、`node`（按路由场景）
