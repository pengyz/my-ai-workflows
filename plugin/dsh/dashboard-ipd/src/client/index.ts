/**
 * Browser plugin for the IPD dashboard: registers the `shell.overlay` docked
 * panel with host action round-trips. Chat rendering is intentionally absent —
 * the panel is the only surface; `ipd/board` events feed the `ipdBoard`
 * projection, not a conversation node.
 * @module dashboard-ipd/client
 */

import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import { IpdBoardPanel } from './IpdBoardPanel.tsx'
import type { PanelInjected } from './IpdBoardPanel.tsx'

/** Services for the keyed renderer, slots, and host RPC. */
export const inject = ['slots', 'sessions', 'remote', 'remote.commands']

/** Register the IPD dashboard overlay panel. */
export function apply(ctx: ClientContext): void {
  ctx.slots.inject('shell.overlay', () => ctx.slots.register({
    name: 'shell.overlay',
    id: 'ipd-dashboard',
    inject: (): PanelInjected => ({
      refresh: (sessionId) => {
        if (sessionId !== undefined) void ctx.remote.commands.execute(sessionId, '/ipd-board', [])
      },
      runAction: (sessionId, action, issId) => {
        if (sessionId !== undefined) void ctx.remote.commands.execute(sessionId, `/ipd-${action} ${issId}`, [])
      },
      stop: (sessionId, agentId) => {
        if (sessionId !== undefined) void ctx.remote.commands.execute(sessionId, `/ipd-stop ${agentId}`, [])
      },
      saveNote: (sessionId, issId, text) => {
        if (sessionId !== undefined) void ctx.remote.commands.execute(sessionId, `/ipd-note ${issId} ${text}`, [])
      },
      openAgent: (sessionId, agentId) => {
        // 子 agent 会话在 session list 中 (parentId 谱系), 直接 open 最稳 —
        // openSubagent 依赖父会话的 subagent catalog 已拉取, spawn 后可能未就绪。
        void ctx.sessions.open(agentId)
      },
    }),
  }, IpdBoardPanel))
}
