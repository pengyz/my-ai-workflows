/**
 * Pure GFM rendering of a board digest: a summary line plus a bounded markdown
 * table. Both the tool's `output.render` and the `/ipd-board` command share
 * this module, so model-visible text and human output stay identical.
 * @module dashboard-ipd/format
 */

import type { JsonValue } from '@deepseek-ai/dsh-tools'
import type { BoardDigestValue, DigestIssue } from './types.js'

export interface FormatOptions {
  /** MR 链接前缀, 例如 `https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/`. */
  mrBaseUrl?: string
  /** 标题最大显示长度, 默认 40。 */
  maxTitleLength?: number
}

const HEADER = '| issId | 优先级 | IPD状态 | fix-db进度 | MR | 合入 | 标题 |'
const SEPARATOR = '|---|---|---|---|---|---|---|'
const PRIORITY_ORDER = ['Blocker', 'Critical', 'Major', 'Minor', 'Trivial']

/** 从文本中提取 MR 编号 (支持 `merge_requests/N` 与 `!N` 两种写法)。 */
export function extractMrNumbers(text: string | undefined): string[] {
  if (text === undefined || text === '') return []
  const out: string[] = []
  for (const match of text.matchAll(/(?:merge_requests\/|!)(\d+)/g)) {
    const num = match[1]
    if (num !== undefined) out.push(num)
  }
  return [...new Set(out)]
}

function asString(value: JsonValue | undefined): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function mrCell(row: DigestIssue, base: string): string {
  const numbers = new Set<string>(row.mr)
  for (const n of extractMrNumbers(asString(row.fixdb?.mr))) numbers.add(n)
  for (const n of extractMrNumbers(asString(row.fixdb?.backport_mr))) numbers.add(n)
  if (numbers.size === 0) return '-'
  const link = (n: string): string => (base === '' ? `!${n}` : `[!${n}](${base}${n})`)
  return [...numbers].map(link).join(', ')
}

function cell(value: string): string {
  return value.replaceAll('|', '\\|')
}

function mergeStatus(row: DigestIssue): string {
  if (row.fixdb === null) return '-'
  return asString(row.fixdb.merge_status) ?? 'pending'
}

function fixdbProgress(row: DigestIssue): string {
  if (row.fixdb === null) return '-'
  return asString(row.fixdb.status) ?? '(无状态)'
}

function titleCell(title: string, max: number): string {
  if (title.length <= max) return cell(title)
  return cell(`${title.slice(0, max)}…`)
}

function statsLine(digest: BoardDigestValue): string {
  const prio = Object.entries(digest.byPriority)
    .sort(([a], [b]) => {
      const ia = PRIORITY_ORDER.indexOf(a)
      const ib = PRIORITY_ORDER.indexOf(b)
      return (ia === -1 ? PRIORITY_ORDER.length : ia) - (ib === -1 ? PRIORITY_ORDER.length : ib)
    })
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')
  const fixdb = Object.entries(digest.fixdbByStatus)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')
  const mergeRate = digest.count === 0 ? 0 : Math.round((digest.merged / digest.count) * 100)
  return [
    `优先级: ${prio || '-'} |`,
    `fix-db 已登记: ${digest.fixdbRegistered}/${digest.count} (${fixdb || '-'}) |`,
    `MR 合入: ${digest.merged}/${digest.count} (${mergeRate}%)`,
  ].join(' ')
}

/** 渲染完整看板 (摘要行 + 表格 + 截断提示)。 */
export function renderBoard(digest: BoardDigestValue, opts: FormatOptions = {}): string {
  const maxTitle = opts.maxTitleLength ?? 40
  const base = opts.mrBaseUrl ?? ''
  const lines: string[] = []
  lines.push(`## IPD 看板 (${digest.scope} 共 ${digest.count} 条${digest.truncated ? ', 结果已截断' : ''})`)
  if (digest.count === 0) {
    lines.push('')
    lines.push('暂无待办问题。')
    return lines.join('\n')
  }
  lines.push('')
  lines.push(statsLine(digest))
  lines.push('')
  lines.push(HEADER)
  lines.push(SEPARATOR)
  for (const row of digest.issues) {
    lines.push(
      `| ${row.issId} | ${cell(row.priority) || '-'} | ${cell(row.status) || '-'} | ${fixdbProgress(row)} | `
      + `${mrCell(row, base)} | ${mergeStatus(row)} | ${titleCell(row.title, maxTitle)} |`,
    )
  }
  lines.push('')
  if (digest.issues.length < digest.count) {
    lines.push(`(仅显示前 ${digest.issues.length} 条, 共 ${digest.count} 条)`)
  }
  return lines.join('\n')
}
