# @deepseek-ai/dsh-dashboard-ipd

个人 IPD 问题单 + MR 状态看板插件（out-of-tree dsh plugin，server + web UI 双端）。

在 dsh 中提供三个面，共享同一条数据路径（`fetchBoard`）：

- `/ipd-board` 斜杠命令 — 人类触发，零模型 token；
- `ipd_board` 工具 — 模型在对话内查询有界摘要（计数 + top-N）；
- **Web UI 看板卡片** — 命令/工具执行后向会话追加 `ipd/board` 事件，浏览器端
  `ConversationNodeDefinition`（kind `ipd-board`）折叠为 Chat 节点，渲染为可视化看板卡片
  （优先级分布 / fix-db 进度 / MR 链接 / 合入率），替代纯文本输出。

数据来自 `~/my-ai-workflows` 的个人脚本与本地 fix-db：

1. `mai-issue-query.py 待办 --json` 直连 mi-adt streamableHttp API，输出已内联 fix-db 进度；
2. 插件聚合为摘要（全量统计 + 按优先级排序的前 N 行）。

## 结构

```
src/index.ts            server 插件: /ipd-board 命令 + ipd_board 工具 + ipd/board 事件发射
src/types.ts            BoardDigestValue / IpdBoardChatData + SessionEventMap 合并
src/client/             browser 端 (dsh.client manifest, 构建为 lib/client.js):
  ├── definition.ts     ConversationNodeDefinition (kind ipd-board, ChatNodeDataMap 合并)
  ├── IpdBoardCard.tsx  keyed conversation.chat.node renderer (可视化看板卡片)
  └── index.ts          apply: 注册 definition + keyed renderer
scripts/build-client.mjs esbuild 构建 lib/client.js (__ModuleLoader__ 契约, externals 仅 react)
```

## 安装

插件声明 `dsh.bundle`（自带 `cordis.patch.yml` 挂载行），`dsh plugin add` 自动将其加入 profile 的 bundles 层——**无需手写 profile 挂载配置**。

```sh
# 构建
cd ~/my-ai-workflows/plugin/dsh/dashboard-ipd && pnpm install && pnpm run build

# 装入 profile —— 必须用 file: (拷贝安装), 不能用 link:
# file: 把插件拷进 profile 的 node_modules, 其 @deepseek-ai/* 依赖经
# $DSH_HOME/profiles/node_modules 愈合 fallback 解析; link: 指向源目录,
# Node 父级上溯找不到依赖, built (非 tsx) 模式启动报 ERR_MODULE_NOT_FOUND。
pnpm dsh plugin --profile web add file:~/my-ai-workflows/plugin/dsh/dashboard-ipd

# 卸载
pnpm dsh plugin --profile web remove @deepseek-ai/dsh-dashboard-ipd
```

> **源码变更后必须重新安装**：`pnpm run build` 之后先 `dsh plugin remove` 再 `dsh plugin add file:...`（纯 add 会被 pnpm 判定 "Already up to date" 而跳过刷新）。`setup.py install` 已内置该 remove+add 流程。

`setup.py install/uninstall` 已集成 dsh 插件安装/卸载（`DSH_CLI` 环境变量指定 dsh 命令，如源码运行时 `DSH_CLI='pnpm dsh'` 并在 harness 仓库目录执行）。

## 配置

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `workflowRoot` | — | `$MY_AI_WORKFLOWS` → `~/my-ai-workflows` | `my-ai-workflows` 仓库根（脚本 + fix-db 所在）；解析出的脚本不存在时加载期 fail loud |
| `scriptPath` | — | `<workflowRoot>/mai-issue-query.py` | 脚本路径覆盖（测试/fixture 用） |
| `pythonBin` | — | `python3` | Python 可执行文件 |
| `mrBaseUrl` | — | `https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/` | MR 链接前缀 |
| `defaultScope` | — | `待办` | 命令/工具缺省范围 |

## 模型体验

- **`ipd_board` 工具**：`execute()` 返回有界摘要（`BoardDigestValue`：全量计数统计 + 前 `limit` 行），GFM 表格只在 `output.render` 中呈现，`presentResult` 用 generic 卡片。默认 `limit=20`，避免 500 行表格撑爆上下文。
- **`/ipd-board` 命令**：handler 返回 `{ kind, text }`，输出不进入模型历史，生命周期由 commands 注册表自动记录（`command/run` + `command/done`）。
- 错误为稳定错误码（`SCRIPT_MISSING` / `QUERY_FAILED` / `UNPARSEABLE_OUTPUT` / `TIMEOUT`），基础设施失败抛 `BoardError` → 工具 `isError`。

## 已知限制

- 数据面为个人环境：mi-adt MCP 配置（`~/.claude.json`）、`workflowRoot` 脚本、GitLab 均只在本人机器可用；CI 无法复现，无自动化端到端覆盖。
- 每调用即查（无缓存）；`未关闭`/`全部` 范围最多 500 条、最坏 ~5s。
- `ipd_board` 工具在 headless/web 均可用；`/ipd-board` 命令仅在提供命令适配器的交互面（web UI）生效。

## 开发

```sh
pnpm run typecheck   # 类型检查（paths 指向 harness 源码类型）
pnpm run build       # tsc 构建 lib/
pnpm run test        # vitest（fixture 驱动，23 用例）
```

数据 seam 位于 `src/sources.ts`：测试用 fixture provider 替代 child-process，`parseIssuesOutput` 是纯函数，覆盖脚本输出解析边界。
