/**
 * Host-side projection units feeding the dashboard panel: `ipdBoard` folds the
 * latest `ipd/board` snapshot, `ipdAgents` folds the current session's spawned
 * agent runs. Registered under `ctx.inject(['sessionProjections'], ...)` so
 * assemblies without the seam stay unaffected.
 * @module dashboard-ipd/projections
 */

import type { ProjectionDefinition } from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-session-projection/types'
import type { Context } from '@deepseek-ai/cordis'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import { z } from 'zod'
import type {} from './events.js'
import type { IpdAgentRunData, IpdBoardChatData } from './types.js'

/** Latest whole board snapshot; `null` before the first `ipd/board` event. */
export const ipdBoardProjection: ProjectionDefinition<'ipdBoard', IpdBoardChatData | null> = {
  key: 'ipdBoard',
  schema: z.any(),
  init: () => null,
  apply: (state, event) => event.type === 'ipd/board' ? event.data as IpdBoardChatData : state,
  view: state => state,
  stateVersion: 1,
}

/** Spawned agent runs in log order, bounded to the latest 50; same agentId updates in place. */
export const ipdAgentsProjection: ProjectionDefinition<'ipdAgents', readonly IpdAgentRunData[] | null> = {
  key: 'ipdAgents',
  schema: z.union([z.array(z.any()), z.null()]),
  init: () => null,
  apply: (state, event): readonly IpdAgentRunData[] | null => {
    if (event.type !== 'ipd/agent-run') return state
    const run = event.data as IpdAgentRunData
    if (state === null) return [run]
    const index = state.findIndex(r => r.agentId === run.agentId)
    if (index === -1) return [...state, run].slice(-50)
    const next = [...state]
    next[index] = run
    return next
  },
  view: state => state,
  stateVersion: 2,
}

/** Register both units; call inside `ctx.inject(['sessionProjections'], ...)`. */
export function registerProjections(projectionCtx: Context): void {
  projectionCtx.sessionProjections.register(ipdBoardProjection)
  projectionCtx.sessionProjections.register(ipdAgentsProjection)
}
