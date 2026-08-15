/**
 * Shared vocabulary for the IPD dashboard plugin: query scopes, issue rows from
 * `mai-issue-query.py --json`, the fix-db join payload, and the bounded digest
 * the tool returns. `BoardDigestValue` is the canonical tool value and matches
 * `ipd_board`'s `output.schema` inference exactly. Data-only — host-side event
 * and projection merges live in `events.ts` (kept out of the browser program).
 * @module dashboard-ipd/types
 */

/** 任意可 JSON 序列化的值 (本地定义, 避免 client 程序拉入 host 依赖)。 */
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }

/** IPD 查询范围, 与 mai-issue-query.py 的位置参数一致。 */
export const SCOPES = ['待办', '未关闭', '全部'] as const

/** IPD 严重等级, 与 mi-adt issuePriority 枚举一致。 */
export const PRIORITIES = ['Blocker', 'Critical', 'Major', 'Minor', 'Trivial'] as const

export type Scope = (typeof SCOPES)[number]

/**
 * fix-db 条目 front-matter, 形状与 fix-db.py 写出的 `- key: value` 行一致。
 * `mai-issue-query.py --json` 的 `fixdb` 字段即此对象; 无记录时为 `null`。
 */
export interface FixDbInfo {
  issId?: string
  type?: string
  title?: string
  status?: string
  conclusion?: string
  /** 用户自定义标注 (面板编辑, fix-db.py note 字段)。 */
  note?: string
  mr?: string
  backport_mr?: string
  merge_status?: string
  updated_at?: string
  /** fix-db 时间线条目 (按时间正序)。 */
  timeline?: string[]
}

/** 一行 IPD 问题 + fix-db 关联信息 (源层类型)。 */
export interface IssueRow {
  issId: string
  /** IPD 数字问题 ID (用于 item 链接), 缺失时为 undefined。 */
  issueId?: number
  title: string
  priority: string
  status: string
  component: string
  /** 从 IPD changeId 提取的 MR 编号。 */
  mr: string[]
  /** fix-db 关联信息, 未登记时为 `null`。 */
  fixdb: FixDbInfo | null
}

/** 一次看板查询请求。 */
export interface BoardQuery {
  scope: Scope
  /** 返回的最大问题行数 (默认 20)。 */
  limit?: number
  /** 按严重等级过滤。 */
  priority?: string
}

/** 看板中的一行 (canonical 值形状, 与 output.schema 推断一致)。 */
export interface DigestIssue {
  issId: string
  /** IPD 数字问题 ID (用于 item 链接), 缺失时为 undefined。 */
  issueId?: number
  title: string
  priority: string
  status: string
  component: string
  mr: string[]
  fixdb: Record<string, JsonValue> | null
}

/**
 * 有界看板摘要 (canonical 值): 统计基于全量问题集, `issues` 仅含优先级排序后的
 * 前 `limit` 行, 避免 500 行表格撑爆模型上下文。
 */
export interface BoardDigestValue {
  scope: string
  count: number
  truncated: boolean
  byStatus: Record<string, JsonValue>
  byPriority: Record<string, JsonValue>
  fixdbByStatus: Record<string, JsonValue>
  fixdbRegistered: number
  merged: number
  issues: DigestIssue[]
}

/**
 * `ipd/board` 会话事件载荷: UI 渲染一帧看板所需的全部数据。
 * 每次 `/ipd-board` 命令或 `ipd_board` 工具触发追加一帧, 客户端以 `requestId` 键控节点。
 */
export interface IpdBoardChatData extends BoardDigestValue {
  /** 每次命令/工具触发生成的唯一请求标识。 */
  requestId: string
  /** 抓取时间 (ISO 字符串)。 */
  fetchedAt: string
  /** MR 链接前缀, 用于渲染可点击链接。 */
  mrBaseUrl: string
}

/** 子 agent 运行终态: 正常完成 vs 意外结束 (中止/失败/超限/拒答). */
export type IpdAgentRunStatus = 'running' | 'completed' | 'aborted' | 'failed'

/**
 * 一次由面板发起的子 agent 运行: action 为分析或修复, agentId 为子会话 id。
 * 面板以 `ipdAgents` projection 折叠出当前会话的运行列表; 终态由 server
 * 侧 `subagent/end` 监听回写 (按 agentId 更新)。
 */
export interface IpdAgentRunData {
  /** 被处理的问题单号。 */
  issueId: string
  /** 子 agent 会话 id。 */
  agentId: string
  action: 'analyze' | 'fix'
  startedAt: string
  status: IpdAgentRunStatus
  /** 终态时间, 运行时为空。 */
  endedAt?: string
}
