import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { renderBoard, extractMrNumbers } from '../src/format.js'
import type { BoardDigestValue } from '../src/types.js'

const fixture = JSON.parse(readFileSync(new URL('./fixtures/issues.json', import.meta.url), 'utf8'))

const MR_BASE = 'https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/'

function digest(overrides: Partial<BoardDigestValue> = {}): BoardDigestValue {
  return {
    scope: '待办',
    count: 4,
    truncated: false,
    byStatus: { Open: 2, Pending: 1, Resolved: 1 },
    byPriority: { Critical: 2, Major: 1, Minor: 1 },
    fixdbByStatus: { fixing: 1, conclusion_uploaded: 1, closed: 1 },
    fixdbRegistered: 3,
    merged: 1,
    issues: fixture,
    ...overrides,
  }
}

describe('renderBoard', () => {
  it('renders header, separator, stats, and MR links', () => {
    const text = renderBoard(digest(), { mrBaseUrl: MR_BASE })
    expect(text).toContain('## IPD 看板 (待办 共 4 条)')
    expect(text).toContain('| issId | 优先级 | IPD状态 | fix-db进度 | MR | 合入 | 标题 |')
    expect(text).toContain('Critical=2')
    expect(text).toContain('fix-db 已登记: 3/4')
    expect(text).toContain('MR 合入: 1/4 (25%)')
    expect(text).toContain(`[!6233](${MR_BASE}6233)`)
    expect(text).toContain(`[!6270](${MR_BASE}6270)`)
    expect(text).toContain('| merged |')
  })

  it('escapes pipe characters in titles', () => {
    const row = { ...fixture[0]!, title: '含 | 管道符的标题' }
    const text = renderBoard(digest({ issues: [row] }), {})
    expect(text).toContain('含 \\| 管道符的标题')
  })

  it('renders an empty board message', () => {
    const text = renderBoard(digest({ count: 0, issues: [], byPriority: {}, byStatus: {}, fixdbByStatus: {}, fixdbRegistered: 0, merged: 0 }))
    expect(text).toContain('共 0 条')
    expect(text).toContain('暂无待办问题。')
  })

  it('notes bounded output when issues exceed the limit', () => {
    const text = renderBoard(digest({ issues: fixture.slice(0, 2) }))
    expect(text).toContain('(仅显示前 2 条, 共 4 条)')
  })

  it('renders plain !N when no base URL is configured', () => {
    const text = renderBoard(digest(), {})
    expect(text).toContain('!6233')
    expect(text).not.toContain('](')
  })

  it('marks truncated boards', () => {
    const text = renderBoard(digest({ truncated: true }))
    expect(text).toContain('结果已截断')
  })
})

describe('extractMrNumbers', () => {
  it('extracts from merge_requests URLs and !N forms', () => {
    expect(extractMrNumbers('https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/6270')).toEqual(['6270'])
    expect(extractMrNumbers('!6270 !6271')).toEqual(['6270', '6271'])
    expect(extractMrNumbers('!6270, !6271')).toEqual(['6270', '6271'])
  })

  it('returns empty for undefined or empty text', () => {
    expect(extractMrNumbers(undefined)).toEqual([])
    expect(extractMrNumbers('')).toEqual([])
  })

  it('deduplicates', () => {
    expect(extractMrNumbers('!6270 merge_requests/6270')).toEqual(['6270'])
  })
})
