import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { BoardError, parseIssuesOutput, SubprocessIssueSource } from '../src/sources.js'

const fixture = JSON.parse(readFileSync(new URL('./fixtures/issues.json', import.meta.url), 'utf8'))

describe('parseIssuesOutput', () => {
  it('parses the script JSON into normalized rows', () => {
    const rows = parseIssuesOutput(JSON.stringify(fixture))
    expect(rows).toHaveLength(4)
    expect(rows[0]).toMatchObject({ issId: 'ISS-202608-00047970A', priority: 'Critical', mr: [] })
    expect(rows[1]?.fixdb).toBeNull()
    expect(rows[3]?.fixdb?.merge_status).toBe('merged')
  })

  it('parses the empty-board sentinel', () => {
    expect(parseIssuesOutput('[]')).toEqual([])
  })

  it('rejects malformed JSON with a stable error code', () => {
    let caught: unknown
    try {
      parseIssuesOutput('not json')
    } catch (err) {
      caught = err
    }
    expect(caught).toBeInstanceOf(BoardError)
    expect((caught as BoardError).code).toBe('UNPARSEABLE_OUTPUT')
  })

  it('rejects non-array output', () => {
    let caught: unknown
    try {
      parseIssuesOutput('{"data": []}')
    } catch (err) {
      caught = err
    }
    expect((caught as BoardError).code).toBe('UNPARSEABLE_OUTPUT')
  })

  it('rejects rows without issId', () => {
    expect(() => parseIssuesOutput('[{"title": "x"}]')).toThrowError(/缺少 issId/)
  })
})

describe('SubprocessIssueSource', () => {
  it('throws SCRIPT_MISSING at construction when the script does not exist', () => {
    expect(() => new SubprocessIssueSource({ scriptPath: '/nonexistent/mai-issue-query.py' }))
      .toThrowError(/不存在/)
  })
})
