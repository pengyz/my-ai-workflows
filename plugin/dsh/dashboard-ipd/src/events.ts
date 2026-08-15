/**
 * Host-side event and projection declarations for the dashboard. The
 * `ipd/board` and `ipd/agent-run` session events are plugin-scoped types —
 * appended with the envelope's `ignorable` marker so harness builds without
 * the plugin skip them on replay instead of refusing the log (see
 * `KNOWN_SESSION_EVENT_TYPES` / `SessionEvent.ignorable`).
 * @module dashboard-ipd/events
 */

import type { IpdAgentRunData, IpdBoardChatData } from './types.js'

declare module '@deepseek-ai/dsh-session' {
  interface SessionEventMap {
    /** IPD 看板快照; 最新帧在 UI 中以 requestId 键控渲染为 Chat 节点。 */
    'ipd/board': IpdBoardChatData
    /** 一次从面板/命令发起的子 agent 分析/修复运行记录。 */
    'ipd/agent-run': IpdAgentRunData
  }
}

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionMap {
    /** 当前会话最新的 IPD 看板快照 (面板数据源)。 */
    ipdBoard: IpdBoardChatData | null
    /** 当前会话发起过的子 agent 运行列表 (按时间正序)。 */
    ipdAgents: readonly IpdAgentRunData[] | null
  }
}
