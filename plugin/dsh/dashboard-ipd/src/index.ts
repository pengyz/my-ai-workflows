/**
 * Personal IPD issue + MR status dashboard for dsh.
 *
 * Registers two surfaces over one shared data path:
 * - `/ipd-board` slash command — human-invoked board, zero model tokens;
 * - `ipd_board` tool — the model queries a bounded digest during a turn.
 *
 * Both call `fetchBoard()` through the same {@link IssueSource}, which by
 * default spawns the personal `mai-issue-query.py` script (its `--json` output
 * already joins IPD issues with the local fix-db). Named exports preserve
 * loader injection metadata; there is no default export.
 * @module @deepseek-ai/dsh-dashboard-ipd
 */

import type { Agent } from '@deepseek-ai/dsh-agent'
import type { Context } from '@deepseek-ai/cordis'
import type { CommandResult } from '@deepseek-ai/dsh-commands'
import type { Session } from '@deepseek-ai/dsh-session'
import type { SubagentRunEndInfo, SubagentRunInfo, SubagentStopReason } from '@deepseek-ai/dsh-subagent'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-subagent'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { execFile } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { homedir } from 'node:os'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fetchBoard, DEFAULT_LIMIT } from './aggregate.js'
import type {} from './events.js'
import { renderBoard } from './format.js'
import { registerProjections } from './projections.js'
import { BoardError, SubprocessIssueSource } from './sources.js'
import type { IssueSource } from './sources.js'
import type { BoardDigestValue, BoardQuery, IpdAgentRunData, IpdBoardChatData, IpdAgentRunStatus } from './types.js'
import { PRIORITIES, SCOPES } from './types.js'
import type { Scope } from './types.js'

export const name = 'dashboard-ipd'
export const inject = ['tools', 'commands', 'subagents', 'sessions']

/** IPD 看板插件配置。 */
export interface Config {
  /**
   * `my-ai-workflows` 仓库根 (脚本 + fix-db 所在)。缺省时取环境变量
   * `MY_AI_WORKFLOWS`, 再回落到 `~/my-ai-workflows`; 解析出的脚本不存在则加载期 fail loud。
   */
  workflowRoot?: string
  /** 覆盖 `mai-issue-query.py` 路径 (测试/fixture 用), 默认 `<workflowRoot>/mai-issue-query.py`。 */
  scriptPath?: string
  /** Python 可执行文件, 默认 `python3`。 */
  pythonBin?: string
  /** MR 链接前缀, 默认 `https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/`。 */
  mrBaseUrl?: string
  /** 命令/工具缺省范围, 默认 `待办`。 */
  defaultScope?: Scope
}

/** 默认 MR 链接前缀 (IPD changeId 里的 MR 来自 osbot 仓库)。 */
export const DEFAULT_MR_BASE_URL = 'https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/'

/** 默认工作流仓库根: 环境变量 `MY_AI_WORKFLOWS` 优先, 否则 `~/my-ai-workflows`。 */
const DEFAULT_WORKFLOW_ROOT = '~/my-ai-workflows'

/** 每个 skill 的关键约束，根据 skill 动态注入 */
const SKILL_CONSTRAINTS: Record<string, string[]> = {
  'mai-analysis': [
    '必须基于日志定位根因，所有结论有日志+代码证据支撑',
    '根因定谳必须结合源码分析（强制）：全链路源码遍历，日志↔源码双向闭合',
    '结论整体二值化：确定根因 / 无法给出结论，禁止模糊定责',
    '门禁 G 核实后才可上传结论，收敛重跑默认 ≤2 轮',
    '凭证清单强制：实际读取的 file:line + 原文摘录 + 执行操作',
  ],
  'mai-fix-workflow': [
    '必须先有 mai-analysis 的完整结论（IPD 评论 + 本地文件双查），无结论拒绝开始',
    'TDD 先行：修复前先定用例集合（mai-osbot-test 编排），红→绿',
    '关键决策前子 agent 独立复核：方案评审（F1）、完成复核（F3）',
    '充分验证：新增用例 + 相关回归 + 冒烟 100% PASS',
    '修复方案必须绑定根因，说明修复机制和验证方法',
  ],
}

/** 每个 skill 的可用工具列表 */
const SKILL_TOOLS: Record<string, string[]> = {
  'mai-analysis': [
    '- mi-adt MCP: 查询 IPD 问题 (M_issueQuery)、评论 (M_pageOverallComment/M_getCommentList)、保存评论 (M_saveComment)',
    '- fix-db.py: 修复数据库查询/更新 (python <WF_ROOT>/fix-db.py query/update)',
    '- wf_root.py: 工作流根目录定位 (python <WF_ROOT>/wf_root.py --check)',
    '- read/grep/glob: 文件读取和搜索',
    '- subagent: 启动子 agent (门禁 G 或收敛重跑 R\')',
  ],
  'mai-fix-workflow': [
    '- mi-adt MCP: 查询 IPD 问题、评论、保存评论',
    '- fix-db.py: 修复数据库查询/更新',
    '- mai-osbot-test: 测试编排 (行为类 eval/CLI/冒烟/双端)',
    '- glab: GitLab API 操作 (MR 创建/查询)',
    '- read/grep/glob: 文件读取和搜索',
    '- subagent: 启动子 agent (方案评审 F1/完成复核 F3)',
  ],
}

function expandHome(path: string): string {
  return path.replace(/^~(?=\/|$)/, homedir())
}

/** 手动配置校验 (fail loud): 无 Config schema 时由 Loader 原样传入, 这里在加载期拒绝坏配置。 */
function normalizeConfig(raw: unknown): Required<Pick<Config, 'workflowRoot' | 'scriptPath' | 'pythonBin'>> & Pick<Config, 'mrBaseUrl' | 'defaultScope'> {
  const c = (raw ?? {}) as Record<string, unknown>
  const workflowRoot = typeof c.workflowRoot === 'string' && c.workflowRoot !== ''
    ? expandHome(c.workflowRoot)
    : expandHome(process.env.MY_AI_WORKFLOWS ?? DEFAULT_WORKFLOW_ROOT)
  const scriptPath = resolve(workflowRoot, typeof c.scriptPath === 'string' ? c.scriptPath : 'mai-issue-query.py')
  if (!existsSync(scriptPath)) {
    throw new Error(`dashboard-ipd: 脚本不存在: ${scriptPath} (设置 config.workflowRoot 或环境变量 MY_AI_WORKFLOWS)`)
  }
  if (c.defaultScope !== undefined && !(SCOPES as readonly string[]).includes(c.defaultScope as string)) {
    throw new Error(`dashboard-ipd: 非法 defaultScope "${String(c.defaultScope)}" (允许: ${SCOPES.join('/')})`)
  }
  return {
    workflowRoot,
    scriptPath,
    pythonBin: typeof c.pythonBin === 'string' ? c.pythonBin : 'python3',
    ...(typeof c.mrBaseUrl === 'string' ? { mrBaseUrl: c.mrBaseUrl } : {}),
    ...(c.defaultScope !== undefined ? { defaultScope: c.defaultScope as Scope } : {}),
  }
}

/** 从命令原始输入解析范围 (支持 "全部"、"未关闭" 等), 否则返回 undefined。 */
function parseScope(input: string): Scope | undefined {
  const hit = SCOPES.find(scope => input === scope || input.startsWith(scope))
  return hit
}

function commandErrorText(err: unknown): string {
  if (err instanceof BoardError) return `ipd-board 失败 (${err.code}): ${err.message}`
  return `ipd-board 失败: ${err instanceof Error ? err.message : String(err)}`
}

/** 向会话追加一帧 `ipd/board` 事件供 UI 渲染; 无 agent (非会话调用方) 时跳过。 */
function appendBoardEvent(agent: Agent | undefined, digest: BoardDigestValue, mrBaseUrl: string): void {
  if (agent === undefined) return
  const data: IpdBoardChatData = {
    requestId: randomUUID(),
    fetchedAt: new Date().toISOString(),
    mrBaseUrl,
    ...digest,
  }
  agent.session.append('ipd/board', data, { ignorable: true })
}

/** 从命令原始输入解析 ISS 单号。 */
function parseIssId(raw: string): string {
  return raw.trim().split(/\s+/)[0] ?? ''
}

/**
 * 读取 skill SKILL.md 并构建 system-reminder 注入内容。
 * 提取关键步骤、工具、约束，减少 LLM 探索次数。
 */
function buildSkillContext(workflowRoot: string, skillName: string): string {
  const skillPath = resolve(workflowRoot, 'skills', skillName, 'SKILL.md')
  if (!existsSync(skillPath)) {
    return `[skill ${skillName} 未找到: ${skillPath}]`
  }
  try {
    const content = readFileSync(skillPath, 'utf-8')
    // 提取关键部分：触发方式、前置、工作流程步骤、输出、门禁、收敛
    const sections: string[] = []
    const lines = content.split('\n')
    let currentSection = ''
    let inTargetSection = false
    for (const line of lines) {
      // 捕获标题
      const headerMatch = line.match(/^(#{1,4})\s+(.+)/)
      if (headerMatch !== null && headerMatch[1] !== undefined && headerMatch[2] !== undefined) {
        currentSection = headerMatch[2]
        // 判断是否进入目标 section
        inTargetSection = (
          currentSection.includes('触发') ||
          currentSection.includes('前置') ||
          currentSection.includes('Step') ||
          currentSection.includes('输出') ||
          currentSection.includes('门禁') ||
          currentSection.includes('收敛') ||
          currentSection.includes('判定')
        )
      }
      // 收集目标 section 的内容
      if (inTargetSection) {
        sections.push(line)
      }
    }
    // 如果提取内容太少，返回摘要
    if (sections.length < 20) {
      const summaryMatch = content.match(/description:\s*\|?\s*\n([\s\S]*?)(?=\n---|\n#)/)
      const summary = summaryMatch !== null && summaryMatch[1] !== undefined ? summaryMatch[1].trim() : skillName
      return `<skill-summary>\n${summary}\n</skill-summary>\n\n完整 skill 文档路径: ${skillPath}\n请先读取该文件了解详细工作流程。`
    }
    // 限制输出长度，避免过大
    const output = sections.join('\n')
    if (output.length > 16000) {
      return output.slice(0, 16000) + '\n\n... [内容截断，请读取完整文档]'
    }
    return output
  } catch {
    return `[读取 ${skillName} 失败]`
  }
}

/** 注册一个面板动作命令: 启动 continuable 子 agent 执行分析/修复并记录 `ipd/agent-run`。 */
function registerAgentCommand(
  ctx: Context,
  action: 'analyze' | 'fix',
  config: Config,
  agentRuns: Map<string, { controller: AbortController; session: Session; record: IpdAgentRunData }>,
): void {
  const isAnalyze = action === 'analyze'
  const skill = isAnalyze ? 'mai-analysis' : 'mai-fix-workflow'
  ctx.commands.register({
    name: isAnalyze ? 'ipd-analyze' : 'ipd-fix',
    description: isAnalyze
      ? '对指定 IPD 问题启动子 agent 根因分析 (mai-analysis 工作流)'
      : '对指定 IPD 问题启动子 agent 修复 (mai-fix-workflow 工作流)',
    input: { hint: 'ISS-xxx' },
    handler: async (invocation): Promise<CommandResult> => {
      const issId = parseIssId(invocation.rawInput)
      if (!/^ISS-\d/.test(issId)) {
        return { kind: 'error', text: '需要 ISS-xxx 问题单号' }
      }
      const controller = new AbortController()
      const label = `${action}: ${issId}`
      // 读取 skill 内容，构建 system-reminder 注入
      const workflowRoot = config.workflowRoot ?? expandHome(DEFAULT_WORKFLOW_ROOT)
      const skillContext = buildSkillContext(workflowRoot, skill)
      const constraints = SKILL_CONSTRAINTS[skill] ?? []
      const tools = SKILL_TOOLS[skill] ?? []
      const promptText = [
        `<system-reminder>`,
        `你是 IPD 问题${isAnalyze ? '分析' : '修复'}专家。当前任务：对问题 ${issId} 执行${isAnalyze ? '根因分析' : '修复'}。`,
        ``,
        `## 可用 Skill: ${skill}`,
        skillContext,
        ``,
        `## 可用工具`,
        ...tools,
        ``,
        `## 关键约束`,
        ...constraints.map((c, i) => `${i + 1}. ${c}`),
        `</system-reminder>`,
        ``,
        `请按照 ${skill} 工作流执行，首先读取完整 skill 文档：${workflowRoot}/skills/${skill}/SKILL.md`,
      ].join('\n')
      // startContinuable 建立持久可续子 agent：面板可监控、可追加信息、可终止。
      const started = await ctx.subagents.startContinuable({
        provider: 'spawn',
        label,
        request: {
          prompt: [{
            type: 'text',
            text: promptText,
          }],
          parent: invocation.agent,
          maxDepth: 3,
        },
        signal: controller.signal,
      })
      const record: IpdAgentRunData = {
        issueId: issId, agentId: started.childId, action, startedAt: new Date().toISOString(), status: 'running',
      }
      agentRuns.set(started.childId, { controller, session: invocation.agent.session, record })
      invocation.agent.session.append('ipd/agent-run', record, { ignorable: true })
      return { kind: 'success', text: `已启动${isAnalyze ? '分析' : '修复'}子 agent (${started.childId}) 处理 ${issId}` }
    },
  })
}

/** 注册停止命令: 面板"停止分析/停止修复"通过它中止对应子 agent。 */
function registerStopCommand(ctx: Context, agentRuns: Map<string, { controller: AbortController; session: Session; record: IpdAgentRunData }>): void {
  ctx.commands.register({
    name: 'ipd-stop',
    description: '停止指定子 agent 的分析/修复运行 (面板内部使用)',
    internal: true,
    handler: async (invocation): Promise<CommandResult> => {
      const agentId = parseIssId(invocation.rawInput)
      if (agentId === '') return { kind: 'error', text: '需要子 agent 会话 id' }
      const entry = agentRuns.get(agentId)
      if (entry === undefined) {
        // 子 agent 可能已自行结束 (subagent/end 已清理条目): 按已停止处理, 不报错。
        return { kind: 'success', text: `子 agent ${agentId} 已不在运行中` }
      }
      entry.controller.abort()
      return { kind: 'success', text: `已请求停止 ${agentId}` }
    },
  })
}

/** stopReason → 面板终态: 仅 completed 视为正常完成。 */
function statusFromStopReason(reason: SubagentStopReason): IpdAgentRunStatus {
  if (reason === 'completed') return 'completed'
  if (reason === 'aborted') return 'aborted'
  return 'failed'
}

/** 从父会话最近的用户/助手文本中提取最近提到的问题号 (LLM 编排关联用). */
function extractIssueFromContext(session: Session): { issueId: string; action: 'analyze' | 'fix' } | undefined {
  const texts: string[] = []
  const events = session.events
  for (let i = events.length - 1; i >= 0 && texts.length < 12; i--) {
    const event = events[i]
    if (event === undefined) continue
    if (event.type !== 'user/message' && event.type !== 'assistant/message') continue
    const content = (event.data as { content?: unknown }).content
    if (!Array.isArray(content)) continue
    for (const block of content) {
      if (block !== null && typeof block === 'object' && 'text' in block && typeof block.text === 'string') {
        texts.push(block.text)
      }
    }
  }
  for (const text of texts) {
    const match = /ISS-\d{6}-\d{8}[A-Z]?/.exec(text)
    if (match !== null && match[0] !== undefined) {
      return { issueId: match[0], action: /修复/.test(texts.join('')) ? 'fix' : 'analyze' }
    }
  }
  return undefined
}

/**
 * 通用子 agent 关联跟踪: 面板命令 spawn 的在命令时已记录 (agentRuns 命中跳过);
 * LLM 经 skill/subagent 工具编排的 spawn, 从父会话上下文推导问题号并记录,
 * 使面板能展示"哪个子 agent 在分析哪个问题"。终态统一由 subagent/end 回写。
 */
function registerSubagentTracker(
  ctx: Context,
  agentRuns: Map<string, { controller: AbortController; session: Session; record: IpdAgentRunData }>,
): void {
  ctx.on('subagent/start', (info: SubagentRunInfo) => {
    if (agentRuns.has(info.id)) return
    const child = ctx.sessions.get(info.id)
    if (child === undefined) return
    const parentId = child.header.parentSession
    if (parentId === undefined) return
    const parent = ctx.sessions.get(parentId)
    if (parent === undefined) return
    const derived = extractIssueFromContext(parent)
    if (derived === undefined) return
    const record: IpdAgentRunData = {
      issueId: derived.issueId,
      agentId: info.id,
      action: derived.action,
      startedAt: new Date().toISOString(),
      status: 'running',
    }
    agentRuns.set(info.id, { controller: new AbortController(), session: parent, record })
    parent.append('ipd/agent-run', record, { ignorable: true })
  })
  ctx.on('subagent/end', (info: SubagentRunEndInfo) => {
    const entry = agentRuns.get(info.id)
    if (entry === undefined) return
    agentRuns.delete(info.id)
    entry.session.append('ipd/agent-run', {
      ...entry.record,
      status: statusFromStopReason(info.stopReason),
      endedAt: new Date().toISOString(),
    }, { ignorable: true })
  })
}

/** 运行 fix-db.py 更新问题字段 (argv 直接传参, 无 shell 注入). */
function runFixDbUpdate(config: { workflowRoot: string; pythonBin: string }, issId: string, note: string): Promise<boolean> {
  return new Promise(done => {
    const script = resolve(config.workflowRoot, 'fix-db.py')
    execFile(config.pythonBin, [script, 'update', issId, '-f', `note=${note}`], (error) => {
      done(error === null)
    })
  })
}

/** 注册标注命令: 面板"自定义标注"列通过它写入 fix-db 的 note 字段。 */
function registerNoteCommand(ctx: Context, config: { workflowRoot: string; pythonBin: string }): void {
  ctx.commands.register({
    name: 'ipd-note',
    description: '更新 fix-db 中问题的自定义标注 (面板内部使用)',
    internal: true,
    handler: async (invocation): Promise<CommandResult> => {
      const raw = invocation.rawInput.trim()
      const space = raw.indexOf(' ')
      if (space <= 0) return { kind: 'error', text: '需要 <issId> <标注>' }
      const issId = raw.slice(0, space)
      const note = raw.slice(space + 1)
      if (!/^ISS-\d/.test(issId)) return { kind: 'error', text: '需要 ISS-xxx 问题单号' }
      const ok = await runFixDbUpdate(config, issId, note)
      return ok
        ? { kind: 'success', text: `已更新 ${issId} 标注` }
        : { kind: 'error', text: 'fix-db 更新失败' }
    },
  })
}

/** 监听 subagent/end, 把终态回写进发起会话的 `ipd/agent-run` (按 agentId 更新)。 */
function registerAgentEndListener(
  ctx: Context,
  agentRuns: Map<string, { controller: AbortController; session: Session; record: IpdAgentRunData }>,
): void {
  ctx.on('subagent/end', (info: SubagentRunEndInfo) => {
    const entry = agentRuns.get(info.id)
    if (entry === undefined) return
    agentRuns.delete(info.id)
    entry.session.append('ipd/agent-run', {
      ...entry.record,
      status: statusFromStopReason(info.stopReason),
      endedAt: new Date().toISOString(),
    }, { ignorable: true })
  })
}

export function apply(ctx: Context, rawConfig: unknown): void {
  const config = normalizeConfig(rawConfig)
  const source: IssueSource = new SubprocessIssueSource({
    scriptPath: config.scriptPath,
    pythonBin: config.pythonBin,
  })
  const mrBaseUrl = config.mrBaseUrl ?? DEFAULT_MR_BASE_URL
  const defaultScope: Scope = config.defaultScope ?? '待办'
  // 运行中的子 agent 句柄 (agentId → AbortController), 供 /ipd-stop 中止。
  const agentRuns = new Map<string, { controller: AbortController; session: Session; record: IpdAgentRunData }>()

  ctx.inject(['sessionProjections'], registerProjections)

  ctx.commands.register({
    name: 'ipd-board',
    description: '查看个人 IPD 问题单与 MR 处理状态看板 (可传范围: 待办/未关闭/全部)',
    internal: true,
    handler: async (invocation): Promise<CommandResult> => {
      const scope = parseScope(invocation.rawInput.trim()) ?? defaultScope
      try {
        const digest = await fetchBoard(source, { scope, limit: 100 }, invocation.signal)
        appendBoardEvent(invocation.agent, digest, mrBaseUrl)
        return { kind: 'success', text: renderBoard(digest, { mrBaseUrl }) }
      } catch (err) {
        return { kind: 'error', text: commandErrorText(err) }
      }
    },
  })
  registerAgentCommand(ctx, 'analyze', config, agentRuns)
  registerAgentCommand(ctx, 'fix', config, agentRuns)
  registerStopCommand(ctx, agentRuns)
  registerSubagentTracker(ctx, agentRuns)
  registerNoteCommand(ctx, config)

  ctx.tools.register(defineTool({
    name: 'ipd_board',
    description: '查询个人 IPD 问题看板: 名下 IPD 问题单的优先级/状态分布、fix-db 处理进度与 MR 合入情况。',
    parameters: {
      scope: {
        type: 'string',
        enum: [...SCOPES],
        description: '查询范围: 待办(默认)/未关闭/全部',
      },
      limit: {
        type: 'integer',
        description: `返回的最大问题行数, 默认 ${DEFAULT_LIMIT}`,
      },
      priority: {
        type: 'string',
        enum: [...PRIORITIES],
        description: '按严重等级过滤',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          scope: { type: 'string', required: true },
          count: { type: 'integer', required: true },
          truncated: { type: 'boolean', required: true },
          byStatus: { type: 'object', additionalProperties: true, required: true },
          byPriority: { type: 'object', additionalProperties: true, required: true },
          fixdbByStatus: { type: 'object', additionalProperties: true, required: true },
          fixdbRegistered: { type: 'integer', required: true },
          merged: { type: 'integer', required: true },
          issues: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                issId: { type: 'string', required: true },
                issueId: { type: 'integer' },
                title: { type: 'string', required: true },
                priority: { type: 'string', required: true },
                status: { type: 'string', required: true },
                component: { type: 'string', required: true },
                mr: { type: 'array', items: { type: 'string' }, required: true },
                fixdb: {
                  oneOf: [
                    { type: 'object', additionalProperties: true },
                    { type: 'null' },
                  ],
                  required: true,
                },
              },
            },
          },
        },
      },
      render: (_args, value) => [{ type: 'text', text: renderBoard(value, { mrBaseUrl }) }],
    },
    presentCall: () => ({ card: 'generic', title: '查询 IPD 看板', kind: 'other' }),
    presentResult: (_args, result) => ({ card: 'generic', title: 'IPD 看板', content: result.content }),
    timeoutMs: 150_000,
    execute: async (args, exec) => {
      const scope = args.scope ?? defaultScope
      const query: BoardQuery = {
        scope,
        ...(typeof args.limit === 'number' ? { limit: args.limit } : {}),
        ...(typeof args.priority === 'string' ? { priority: args.priority } : {}),
      }
      const digest = await fetchBoard(source, query, exec.signal)
      appendBoardEvent(exec.agent, digest, mrBaseUrl)
      return digest
    },
  }))
}
