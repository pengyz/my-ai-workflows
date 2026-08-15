/**
 * Data-source seam for the IPD dashboard. A tool/command fetches through an
 * {@link IssueSource}; the production implementation spawns
 * `mai-issue-query.py` as a child process, and tests substitute a fixture
 * provider. Child processes are single-programs (python / glab) with no
 * grandchild tree, so abort handling is a plain Node signal kill.
 * @module dashboard-ipd/sources
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname } from 'node:path'
import type { BoardQuery, IssueRow } from './types.js'

/** Stable error identity for dashboard failures, surfaced to the model as `isError`. */
export type BoardErrorCode = 'CONFIG_INVALID' | 'SCRIPT_MISSING' | 'QUERY_FAILED' | 'UNPARSEABLE_OUTPUT' | 'TIMEOUT'

export class BoardError extends Error {
  constructor(
    readonly code: BoardErrorCode,
    message: string,
  ) {
    super(message)
    this.name = 'BoardError'
  }
}

/** One fetchable IPD issue list; tests implement this interface instead of spawning. */
export interface IssueSource {
  fetchIssues(query: BoardQuery, signal?: AbortSignal): Promise<{ issues: IssueRow[]; truncated: boolean }>
}

/** Options for the child-process source. */
export interface SubprocessSourceOptions {
  /** Absolute path to `mai-issue-query.py`. */
  scriptPath: string
  /** Python executable, default `python3`. */
  pythonBin?: string
  /** Child working directory, default the script's directory. */
  cwd?: string
  /** In-memory stdout cap in bytes, default 1 MiB (a 500-issue board is ~140 KB). */
  maxOutputBytes?: number
  /** Per-call timeout in ms, default 150 000 (the script pages up to 500 issues). */
  timeoutMs?: number
}

/**
 * Production source: spawns the personal IPD query script with `--json` and
 * parses its output. Nonzero exit, missing script, malformed JSON, and timeout
 * each map to one stable {@link BoardError}.
 */
export class SubprocessIssueSource implements IssueSource {
  private readonly pythonBin: string
  private readonly cwd: string
  private readonly maxOutputBytes: number
  private readonly timeoutMs: number

  constructor(private readonly opts: SubprocessSourceOptions) {
    this.pythonBin = opts.pythonBin ?? 'python3'
    this.cwd = opts.cwd ?? dirname(opts.scriptPath)
    this.maxOutputBytes = opts.maxOutputBytes ?? 1024 * 1024
    this.timeoutMs = opts.timeoutMs ?? 150_000
    if (!existsSync(opts.scriptPath)) {
      throw new BoardError('SCRIPT_MISSING', `mai-issue-query.py 不存在: ${opts.scriptPath}`)
    }
  }

  async fetchIssues(query: BoardQuery, signal?: AbortSignal): Promise<{ issues: IssueRow[]; truncated: boolean }> {
    const args = [
      this.opts.scriptPath,
      query.scope,
      '--json',
      ...(query.priority !== undefined ? ['--priority', query.priority] : []),
    ]
    const { stdout, stderr, timedOut, exitCode } = await runCollect(this.pythonBin, args, this.cwd, {
      maxOutputBytes: this.maxOutputBytes,
      timeoutMs: this.timeoutMs,
      ...(signal !== undefined ? { signal } : {}),
    })
    if (timedOut) {
      throw new BoardError('TIMEOUT', `IPD 查询超时 (${this.timeoutMs}ms)`)
    }
    if (exitCode !== 0) {
      const tail = stderr.trim().slice(-500)
      throw new BoardError('QUERY_FAILED', `mai-issue-query.py 退出码 ${exitCode}${tail ? `: ${tail}` : ''}`)
    }
    return { issues: parseIssuesOutput(stdout), truncated: stderr.includes('(截断)') }
  }
}

/** Spawn one command, collect bounded stdout/stderr, honor the abort signal. */
async function runCollect(
  exe: string,
  args: readonly string[],
  cwd: string,
  opts: { maxOutputBytes: number; timeoutMs: number; signal?: AbortSignal },
): Promise<{ stdout: string; stderr: string; timedOut: boolean; exitCode: number }> {
  return await new Promise((resolvePromise, reject) => {
    const child = spawn(exe, [...args], {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      ...(opts.signal !== undefined ? { signal: opts.signal } : {}),
    })
    let stdout = ''
    let stderr = ''
    let timedOut = false
    const cap = (collected: string, chunk: Buffer, max: number): string => {
      const next = collected.length + chunk.length
      return next <= max ? collected + chunk.toString() : collected + chunk.toString().slice(0, Math.max(0, max - collected.length))
    }
    child.stdout?.on('data', (chunk: Buffer) => {
      stdout = cap(stdout, chunk, opts.maxOutputBytes)
    })
    child.stderr?.on('data', (chunk: Buffer) => {
      stderr = cap(stderr, chunk, 64 * 1024)
    })
    const timer = setTimeout(() => {
      timedOut = true
      child.kill('SIGTERM')
    }, opts.timeoutMs)
    child.on('error', (err: NodeJS.ErrnoException) => {
      clearTimeout(timer)
      if (opts.signal?.aborted) {
        // spawn 的 signal 中止以 ABORT_ERR 触发 error 而非 close。
        reject(new BoardError('TIMEOUT', 'IPD 查询已取消'))
        return
      }
      const code = err.code === 'ENOENT' ? 'SCRIPT_MISSING' : 'QUERY_FAILED'
      reject(new BoardError(code, `${exe} 启动失败: ${err.message}`))
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (opts.signal?.aborted) {
        reject(new BoardError('TIMEOUT', 'IPD 查询已取消'))
        return
      }
      resolvePromise({ stdout, stderr, timedOut, exitCode: code ?? 1 })
    })
  })
}

/**
 * Parse the script's `--json` stdout into issue rows. Exported separately so
 * unit tests cover the boundary without spawning a process.
 */
export function parseIssuesOutput(stdout: string): IssueRow[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(stdout)
  } catch (err) {
    throw new BoardError('UNPARSEABLE_OUTPUT', `IPD 查询输出不是合法 JSON: ${err instanceof Error ? err.message : String(err)}`)
  }
  if (!Array.isArray(parsed)) {
    throw new BoardError('UNPARSEABLE_OUTPUT', 'IPD 查询输出应为 JSON 数组')
  }
  return parsed.map(normalizeRow)
}

function normalizeRow(raw: unknown): IssueRow {
  const r = (raw ?? {}) as Record<string, unknown>
  if (typeof r.issId !== 'string' || r.issId.length === 0) {
    throw new BoardError('UNPARSEABLE_OUTPUT', 'IPD 查询输出缺少 issId')
  }
  return {
    issId: r.issId,
    ...(typeof r.issueId === 'number' ? { issueId: r.issueId } : {}),
    title: typeof r.title === 'string' ? r.title : '',
    priority: typeof r.priority === 'string' ? r.priority : '',
    status: typeof r.status === 'string' ? r.status : '',
    component: typeof r.component === 'string' ? r.component : '',
    mr: Array.isArray(r.mr) ? r.mr.filter((m): m is string => typeof m === 'string') : [],
    fixdb: isFixDb(r.fixdb) ? r.fixdb : null,
  }
}

function isFixDb(value: unknown): value is IssueRow['fixdb'] {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
