/**
 * Pure board aggregation: fetches through the {@link IssueSource} seam and
 * produces the bounded canonical digest. Stats always cover the full result
 * set; only `issues` is sliced to `limit` rows, sorted by severity.
 * @module dashboard-ipd/aggregate
 */

import type { JsonValue } from '@deepseek-ai/dsh-tools'
import type { IssueSource } from './sources.js'
import type { BoardDigestValue, BoardQuery, DigestIssue, FixDbInfo, IssueRow } from './types.js'
import { PRIORITIES } from './types.js'

/** Default number of issue rows the model sees. */
export const DEFAULT_LIMIT = 20

/** Severity rank for sorting; unknown priorities sort last. */
export function priorityRank(priority: string): number {
  const index = PRIORITIES.indexOf(priority as (typeof PRIORITIES)[number])
  return index === -1 ? PRIORITIES.length : index
}

/** Stable severity-ascending sort (Blocker first). */
export function sortByPriority(rows: readonly IssueRow[]): IssueRow[] {
  return [...rows].sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority))
}

/** Count rows by one key; unknown keys keep their literal label. */
export function countBy(rows: readonly IssueRow[], key: (row: IssueRow) => string): Record<string, number> {
  const out: Record<string, number> = {}
  for (const row of rows) {
    const k = key(row)
    out[k] = (out[k] ?? 0) + 1
  }
  return out
}

/** Whether a row's fix-db entry reports its MR merged. */
export function isMerged(row: IssueRow): boolean {
  return row.fixdb !== null && (row.fixdb.merge_status === 'merged' || row.fixdb.status === 'merged')
}

function toCanonicalFixDb(fixdb: FixDbInfo | null): Record<string, JsonValue> | null {
  if (fixdb === null) return null
  const out: Record<string, JsonValue> = {}
  for (const [key, value] of Object.entries(fixdb)) {
    if (value !== undefined) out[key] = value
  }
  return out
}

function toDigestIssue(row: IssueRow): DigestIssue {
  return {
    issId: row.issId,
    ...(row.issueId !== undefined ? { issueId: row.issueId } : {}),
    title: row.title,
    priority: row.priority,
    status: row.status,
    component: row.component,
    mr: row.mr,
    fixdb: toCanonicalFixDb(row.fixdb),
  }
}

/**
 * Fetch and aggregate one board. Throws {@link BoardError} from the source on
 * infrastructure failure; an empty board is a successful zero-count digest.
 */
export async function fetchBoard(
  source: IssueSource,
  query: BoardQuery,
  signal?: AbortSignal,
): Promise<BoardDigestValue> {
  const { issues, truncated } = await source.fetchIssues(query, signal)
  const limit = query.limit ?? DEFAULT_LIMIT
  const registered = issues.filter(row => row.fixdb !== null)
  return {
    scope: query.scope,
    count: issues.length,
    truncated,
    byStatus: countBy(issues, row => row.status),
    byPriority: countBy(issues, row => row.priority),
    fixdbByStatus: countBy(registered, row => row.fixdb?.status ?? '(none)'),
    fixdbRegistered: registered.length,
    merged: issues.filter(isMerged).length,
    issues: sortByPriority(issues).slice(0, Math.max(0, limit)).map(toDigestIssue),
  }
}
