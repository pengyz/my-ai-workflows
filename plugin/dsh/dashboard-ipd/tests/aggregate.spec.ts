import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { fetchBoard, countBy, sortByPriority, isMerged, priorityRank } from '../src/aggregate.js'
import type { IssueSource } from '../src/sources.js'
import type { IssueRow } from '../src/types.js'

const issues = JSON.parse(readFileSync(new URL('./fixtures/issues.json', import.meta.url), 'utf8')) as IssueRow[]

function fakeSource(rows: IssueRow[], truncated = false): IssueSource {
  return { fetchIssues: async () => ({ issues: rows, truncated }) }
}

describe('fetchBoard', () => {
  it('computes full-set stats and bounds the issues list by limit', async () => {
    const digest = await fetchBoard(fakeSource(issues), { scope: '待办', limit: 2 })
    expect(digest.count).toBe(4)
    expect(digest.issues).toHaveLength(2)
    expect(digest.issues.map(i => i.issId)).toEqual(['ISS-202608-00047970A', 'ISS-202608-00050958A'])
    expect(digest.byPriority).toEqual({ Critical: 2, Major: 1, Minor: 1 })
    expect(digest.byStatus).toEqual({ Open: 2, Pending: 1, Resolved: 1 })
    expect(digest.fixdbRegistered).toBe(3)
    expect(digest.fixdbByStatus).toEqual({ fixing: 1, conclusion_uploaded: 1, closed: 1 })
    expect(digest.merged).toBe(1)
    expect(digest.truncated).toBe(false)
  })

  it('passes the truncated flag through', async () => {
    const digest = await fetchBoard(fakeSource(issues, true), { scope: '未关闭' })
    expect(digest.truncated).toBe(true)
  })

  it('returns a zero digest for an empty board', async () => {
    const digest = await fetchBoard(fakeSource([]), { scope: '待办' })
    expect(digest.count).toBe(0)
    expect(digest.issues).toEqual([])
    expect(digest.merged).toBe(0)
    expect(digest.fixdbRegistered).toBe(0)
  })

  it('defaults limit to 20 when omitted', async () => {
    const digest = await fetchBoard(fakeSource(issues), { scope: '待办' })
    expect(digest.issues.length).toBeLessThanOrEqual(20)
  })
})

describe('sorting helpers', () => {
  it('ranks known priorities and pushes unknown last', () => {
    expect(priorityRank('Blocker')).toBe(0)
    expect(priorityRank('Trivial')).toBe(4)
    expect(priorityRank('Unknown')).toBe(5)
  })

  it('sorts severity-ascending without mutating the input', () => {
    const input = [issues[3], issues[0], issues[2], issues[1]] as IssueRow[]
    const sorted = sortByPriority(input)
    expect(sorted[0]?.priority).toBe('Critical')
    expect(input[0]?.priority).toBe('Minor')
  })

  it('isMerged only for fix-db entries reporting merged', () => {
    expect(isMerged(issues[3]!)).toBe(true)
    expect(isMerged(issues[1]!)).toBe(false)
  })
})

describe('countBy', () => {
  it('counts by key with literal labels for unknown keys', () => {
    const out = countBy(issues, row => row.priority)
    expect(out).toEqual({ Critical: 2, Major: 1, Minor: 1 })
  })
})
