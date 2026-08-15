/**
 * IPD dashboard panel — a `shell.overlay` (root scope) surface: sortable,
 * filterable issue table with rich badges, clickable titles/MR links, per-row
 * spawn actions (analyze/fix via host commands), and the session's spawned
 * agent runs. Pure presentation; data + actions arrive through props.
 * @module dashboard-ipd/client-panel
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { DigestIssue, IpdAgentRunData, IpdAgentRunStatus, IpdBoardChatData } from '../types.js'

/** Actions injected from the plugin's apply closure (host round-trips). */
export interface PanelInjected {
  refresh(sessionId: SessionId | undefined): void
  runAction(sessionId: SessionId | undefined, action: 'analyze' | 'fix', issId: string): void
  stop(sessionId: SessionId | undefined, agentId: string): void
  saveNote(sessionId: SessionId | undefined, issId: string, text: string): void
  openAgent(sessionId: SessionId | undefined, agentId: string): void
}

export type IpdBoardPanelProps = PropsRuntime<'shell.overlay'> & PanelInjected

type SortKey = 'priority' | 'status' | 'issId' | 'title'
type SortDir = 'asc' | 'desc'

const PRIORITY_ORDER = ['Blocker', 'Critical', 'Major', 'Minor', 'Trivial'] as const
const PRIORITY_COLOR: Record<string, string> = {
  Blocker: '#e5484d', Critical: '#f76b15', Major: '#f5a524',
  Minor: '#3b82f6', Trivial: '#8b8d98',
}
const STATUS_COLOR: Record<string, string> = {
  Open: '#30a46c', Pending: '#f5a524', Resolved: '#3b82f6',
  Reopened: '#f76b15', Closed: '#8b8d98',
}

const IPD_ITEM_BASE = 'https://ipd.mioffice.cn/issue-collaboration-platform/issue_info/item/'

const s: Record<string, CSSProperties> = {
  fab: {
    position: 'fixed', right: '16px', bottom: '16px', zIndex: 900,
    pointerEvents: 'auto', cursor: 'pointer',
    background: 'var(--dsw-alias-state-business-primary)', color: '#fff',
    border: 'none', borderRadius: '20px', padding: '8px 14px',
    fontSize: '13px', fontWeight: 510, boxShadow: '0 2px 8px rgba(0,0,0,.2)',
  },
  panel: {
    position: 'fixed', inset: '40px 0 0 auto', width: '80vw', height: 'calc(100vh - 40px)',
    background: 'var(--dsw-alias-bg-base)', borderLeft: '1px solid var(--dsw-alias-border-l2)',
    zIndex: 800, display: 'flex', flexDirection: 'column',
    pointerEvents: 'auto', boxShadow: '-8px 0 24px rgba(0,0,0,.18)',
  },
  backdrop: {
    position: 'fixed', inset: 0, zIndex: 799, pointerEvents: 'auto', background: 'transparent',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px',
    borderBottom: '1px solid var(--dsw-alias-border-l2)',
    fontSize: '15px', fontWeight: 510, color: 'var(--dsw-alias-label-primary)',
  },
  headerRight: { marginLeft: 'auto', display: 'flex', gap: '8px' },
  btn: {
    background: 'var(--dsw-alias-bg-module-platform)', border: '1px solid var(--dsw-alias-border-l2)',
    borderRadius: '6px', padding: '4px 10px', fontSize: '12px', cursor: 'pointer',
    color: 'var(--dsw-alias-label-secondary)',
  },
  filters: {
    display: 'flex', gap: '8px', padding: '8px 16px', alignItems: 'center', flexWrap: 'wrap',
    borderBottom: '1px solid var(--dsw-alias-border-l2)', fontSize: '12px',
  },
  select: {
    background: 'var(--dsw-alias-bg-module-platform)', color: 'var(--dsw-alias-label-secondary)',
    border: '1px solid var(--dsw-alias-border-l2)', borderRadius: '6px', padding: '3px 6px', fontSize: '12px',
  },
  scroll: { flex: 1, overflow: 'auto', padding: '8px 16px 24px' },
  stats: {
    display: 'flex', flexWrap: 'wrap', gap: '4px 16px', padding: '8px 0',
    fontSize: '12px', color: 'var(--dsw-alias-label-tertiary)',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '12px', lineHeight: '18px' },
  th: {
    textAlign: 'left', color: 'var(--dsw-alias-label-tertiary)', fontWeight: 510,
    padding: '4px 8px 4px 0', whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none',
    position: 'sticky', top: 0, zIndex: 1, background: 'var(--dsw-alias-bg-base)',
  },
  thNoSort: {
    textAlign: 'left', color: 'var(--dsw-alias-label-tertiary)', fontWeight: 510,
    padding: '4px 8px 4px 0', whiteSpace: 'nowrap',
    position: 'sticky', top: 0, zIndex: 1, background: 'var(--dsw-alias-bg-base)',
  },
  td: { padding: '4px 8px 4px 0', verticalAlign: 'top', whiteSpace: 'nowrap' },
  titleTd: { whiteSpace: 'normal', minWidth: '260px', maxWidth: '380px' },
  link: { color: 'var(--dsw-alias-state-business-primary)', textDecoration: 'none' },
  badge: { borderRadius: '4px', padding: '1px 6px', fontSize: '11px', fontWeight: 510, color: '#fff' },
  action: {
    background: 'transparent', border: '1px solid var(--dsw-alias-border-l2)',
    borderRadius: '4px', padding: '1px 8px', fontSize: '11px', cursor: 'pointer',
    color: 'var(--dsw-alias-label-secondary)', marginRight: '4px',
  },
  actionPrimary: {
    background: 'var(--dsw-alias-state-business-primary)', borderColor: 'transparent', color: '#fff',
  },
  spinner: {
    display: 'inline-block', width: '10px', height: '10px', marginRight: '5px',
    verticalAlign: 'middle', border: '2px solid var(--dsw-alias-border-l3)',
    borderTopColor: 'var(--dsw-alias-state-business-primary)', borderRadius: '50%',
    animation: 'dsh-ipd-spin 0.8s linear infinite',
  },
  running: { color: 'var(--dsw-alias-state-business-primary)', fontSize: '11px', marginRight: '6px' },
  done: { color: 'var(--dsw-alias-label-tertiary)', fontSize: '11px', marginRight: '6px' },
  grey: { color: 'var(--dsw-alias-label-tertiary)', fontSize: '11px' },
  greyBtn: { opacity: 0.5, cursor: 'default' },
  fail: { color: '#e5484d', fontSize: '11px', marginRight: '6px' },
  jump: {
    background: 'transparent', border: '1px solid var(--dsw-alias-border-l2)',
    borderRadius: '4px', padding: '0 6px', fontSize: '12px', cursor: 'pointer',
    color: 'var(--dsw-alias-state-business-primary)', marginLeft: '2px',
  },
  viewBtn: {
    color: 'var(--dsw-alias-state-business-primary)', borderColor: 'var(--dsw-alias-border-l3)',
  },
  note: {
    width: '120px', background: 'transparent', color: 'var(--dsw-alias-label-primary)',
    border: '1px solid transparent', borderRadius: '4px', padding: '2px 4px', fontSize: '11px',
  },
  noteFilled: { borderColor: 'var(--dsw-alias-border-l3)' },
  expand: {
    background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
    color: 'var(--dsw-alias-label-tertiary)', fontSize: '11px', textDecoration: 'underline',
  },
  detail: {
    background: 'var(--dsw-alias-bg-module-platform)', fontSize: '11px', lineHeight: '18px',
    padding: '6px 8px', borderRadius: '4px', color: 'var(--dsw-alias-label-secondary)',
  },
  conclusion: { maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  batchBar: { display: 'flex', gap: '8px', alignItems: 'center', marginLeft: 'auto' },
  agents: {
    marginTop: '16px', border: '1px solid var(--dsw-alias-border-l2)', borderRadius: '8px',
    padding: '8px 12px', fontSize: '12px',
  },
  agentRow: { display: 'flex', gap: '8px', alignItems: 'center', padding: '3px 0' },
  empty: { color: 'var(--dsw-alias-label-tertiary)', padding: '12px 0', fontSize: '13px' },
}

function priorityRank(p: string): number {
  const i = PRIORITY_ORDER.indexOf(p as (typeof PRIORITY_ORDER)[number])
  return i === -1 ? PRIORITY_ORDER.length : i
}

function badgeColor(map: Record<string, string>, value: string): string {
  return map[value] ?? '#8b8d98'
}

function mrNumbers(row: DigestIssue): string[] {
  const out = new Set<string>(row.mr)
  const fixdbMr = typeof row.fixdb?.mr === 'string' ? row.fixdb.mr : ''
  for (const m of fixdbMr.matchAll(/(?:merge_requests\/|!)(\d+)/g)) {
    const n = m[1]
    if (n !== undefined) out.add(n)
  }
  return [...out]
}

function mergeCell(row: DigestIssue): string {
  if (row.fixdb === null) return '-'
  return typeof row.fixdb.merge_status === 'string' ? row.fixdb.merge_status : 'pending'
}

function progressCell(row: DigestIssue): string {
  if (row.fixdb === null) return '-'
  return typeof row.fixdb.status === 'string' ? row.fixdb.status : '(无状态)'
}

/** Sortable/filterable IPD board + spawned-agent list in a docked panel. */
/** 操作确认窗口: 点击后 UI 变灰, 超时未确认则回退。 */
const CONFIRM_MS = 5000

export function IpdBoardPanel({ useSessions, refresh, runAction, stop, saveNote, openAgent }: IpdBoardPanelProps): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('priority')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterPriority, setFilterPriority] = useState('')
  /** issId → 启动中的动作 (点击"开始分析/修复"后, agent-run 确认前). */
  const [starting, setStarting] = useState<ReadonlyMap<string, 'analyze' | 'fix'>>(new Map())
  /** agentId → 请求停止中 (点击"停止"后, 子 agent 停止确认前). */
  const [stopping, setStopping] = useState<ReadonlySet<string>>(new Set())
  /** 批量操作选中的 issId 集合。 */
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  /** fix-db 详情展开的 issId 集合。 */
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  /** 刷新进行中 (按钮转圈). */
  const [refreshing, setRefreshing] = useState(false)
  const refreshCount = useRef(0)
  const doRefresh = (): void => {
    const count = ++refreshCount.current
    setRefreshing(true)
    refresh(current)
    window.setTimeout(() => {
      if (refreshCount.current === count) setRefreshing(false)
    }, CONFIRM_MS + 3000)
  }
  useEffect(() => {
    const tag = document.createElement('style')
    tag.textContent = '@keyframes dsh-ipd-spin { to { transform: rotate(360deg) } }'
    document.head.appendChild(tag)
    return () => { tag.remove() }
  }, [])
  const panelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape' || (panelRef.current !== null && !panelRef.current.contains(e.target as Node))) {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])
  const current = useSessions(st => st.current)
  const summary = useSessions(st => (st.current === undefined ? undefined : st.byId[st.current]))
  const byId = useSessions(st => st.byId)
  // projectionValues 键由 server 侧 events.ts 的 SessionProjectionMap merge 声明;
  // client 程序不加载 host merge, 此处按已知形状定向读取。
  const projection = summary?.projectionValues as
    | { ipdBoard?: IpdBoardChatData | null; ipdAgents?: readonly IpdAgentRunData[] | null }
    | undefined
  const board = projection?.ipdBoard ?? null
  const agents = projection?.ipdAgents ?? null
  useEffect(() => {
    // 板数据更新 (requestId 变化) 即视为刷新完成。
    setRefreshing(false)
  }, [board?.requestId])
  // 子 agent 从运行中转为终态时自动刷新看板, 让 fix-db 结论/状态即时生效。
  const prevAgentStatuses = useRef<ReadonlyMap<string, IpdAgentRunStatus>>(new Map())
  useEffect(() => {
    const current = new Map<string, IpdAgentRunStatus>()
    for (const run of agents ?? []) current.set(run.agentId, run.status)
    let finished = false
    for (const [agentId, status] of current) {
      if (prevAgentStatuses.current.get(agentId) === 'running' && status !== 'running') {
        finished = true
        break
      }
    }
    prevAgentStatuses.current = current
    if (finished) {
      const timer = window.setTimeout(doRefresh, 300)
      return () => window.clearTimeout(timer)
    }
    return undefined
  }, [agents])
  // 每问题单最新的 agent-run (后写覆盖).
  const runByIssue = useMemo(() => {
    const map = new Map<string, IpdAgentRunData>()
    for (const run of agents ?? []) map.set(run.issueId, run)
    return map
  }, [agents])

  const startAction = (issId: string, action: 'analyze' | 'fix'): void => {
    setStarting(m => new Map(m).set(issId, action))
    runAction(current, action, issId)
    window.setTimeout(() => {
      setStarting(m => {
        if (!m.has(issId)) return m
        const next = new Map(m)
        next.delete(issId)
        return next
      })
    }, CONFIRM_MS)
  }
  const stopAction = (agentId: string): void => {
    setStopping(s => new Set(s).add(agentId))
    stop(current, agentId)
    window.setTimeout(() => {
      setStopping(s => {
        if (!s.has(agentId)) return s
        const next = new Set(s)
        next.delete(agentId)
        return next
      })
    }, CONFIRM_MS)
  }
  const toggleSelected = (issId: string): void => {
    setSelected(s => {
      const next = new Set(s)
      if (next.has(issId)) next.delete(issId)
      else next.add(issId)
      return next
    })
  }
  const batchAction = (action: 'analyze' | 'fix'): void => {
    for (const issId of selected) startAction(issId, action)
    setSelected(new Set())
  }

  const rows = useMemo(() => {
    if (board === null) return []
    let list = [...board.issues]
    if (filterStatus !== '') list = list.filter(r => r.status === filterStatus)
    if (filterPriority !== '') list = list.filter(r => r.priority === filterPriority)
    const dir = sortDir === 'asc' ? 1 : -1
    list.sort((a, b) => {
      switch (sortKey) {
        case 'priority': return (priorityRank(a.priority) - priorityRank(b.priority)) * dir
        case 'status': return a.status.localeCompare(b.status) * dir
        case 'issId': return a.issId.localeCompare(b.issId) * dir
        default: return a.title.localeCompare(b.title) * dir
      }
    })
    return list
  }, [board, filterStatus, filterPriority, sortKey, sortDir])

  const toggleSort = (key: SortKey): void => {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }
  const sortArrow = (key: SortKey): string => (sortKey === key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '')

  const statuses = board === null ? [] : [...new Set(board.issues.map(r => r.status))]
  const priorities = board === null ? [] : [...new Set(board.issues.map(r => r.priority))].sort(priorityRank)

  /** 行操作状态机: 启动确认中(灰) → 运行中(分析中+停止+查看) → 完成(查看) | 意外结束(失败提示+可重试). */
  const renderActions = (row: DigestIssue): React.JSX.Element => {
    const run = runByIssue.get(row.issId)
    const running = run?.status === 'running'
    const startingAction = starting.get(row.issId)
    const isStopping = run !== undefined && stopping.has(run.agentId)
    // 修复需 fix-db 已有分析结论 (conclusion 非空) 才允许。
    const canFix = row.fixdb != null
      && typeof row.fixdb.conclusion === 'string'
      && row.fixdb.conclusion.trim() !== ''
    const fixBtn = (
      <button style={{ ...s.action, ...(canFix ? {} : s.greyBtn) }} disabled={!canFix}
        title={canFix ? '' : '需先完成分析 (fix-db 已有结论)'}
        onClick={() => startAction(row.issId, 'fix')}>开始修复</button>
    )
    if (startingAction !== undefined) {
      return <span style={s.grey}>{startingAction === 'analyze' ? '启动分析中…' : '启动修复中…'}</span>
    }
    if (run === undefined) {
      return (
        <>
          <button style={{ ...s.action, ...s.actionPrimary }} onClick={() => startAction(row.issId, 'analyze')}>开始分析</button>
          {fixBtn}
        </>
      )
    }
    if (running) {
      return (
        <>
          <span style={s.spinner} />
          <span style={s.running}>{run.action === 'analyze' ? '分析中…' : '修复中…'}</span>
          <button style={{ ...s.action, ...(isStopping ? s.greyBtn : {}) }} disabled={isStopping}
            onClick={() => stopAction(run.agentId)}>{isStopping ? '停止中…' : '停止'}</button>
          <button style={{ ...s.action, ...s.viewBtn }} title={run.agentId}
            onClick={() => { openAgent(current, run.agentId); setOpen(false) }}>查看进展 ↗</button>
        </>
      )
    }
    if (run.status === 'completed') {
      return (
        <>
          <span style={s.done}>{run.action === 'analyze' ? '分析完成' : '修复完成'}</span>
          {run.action === 'analyze' ? fixBtn : null}
          <button style={s.action} onClick={() => startAction(row.issId, 'analyze')}>重新分析</button>
          <button style={{ ...s.action, ...s.viewBtn }} title={run.agentId}
            onClick={() => { openAgent(current, run.agentId); setOpen(false) }}>查看 ↗</button>
        </>
      )
    }
    // 意外结束 (aborted/failed): 失败提示 + 回退到可重试按钮。
    return (
      <>
        <span style={s.fail}>{run.status === 'aborted' ? '已停止' : '失败'}</span>
        <button style={{ ...s.action, ...s.actionPrimary }} onClick={() => startAction(row.issId, 'analyze')}>开始分析</button>
        {fixBtn}
      </>
    )
  }

  // 仅主会话显示打开按钮; 子 agent 会话 (origin: subagent) 不展示。
  const isSubagent = current !== undefined && byId[current]?.origin === 'subagent'

  return (
    <>
      {isSubagent ? null : (
        <button style={s.fab} onClick={() => setOpen(o => !o)}>
          {open ? '关闭看板' : 'IPD 看板'}
        </button>
      )}
      {open ? <div style={s.backdrop} onClick={() => setOpen(false)} /> : null}
      {open ? (
        <div style={s.panel} ref={panelRef}>
          <div style={s.header}>
            <span>IPD 看板</span>
            <span style={{ color: 'var(--dsw-alias-label-tertiary)', fontSize: '12px' }}>
              {board !== null ? `${board.scope} · 共 ${board.count} 条${board.truncated ? ' · 已截断' : ''}` : '未加载'}
            </span>
            <div style={s.headerRight}>
              <button style={s.btn} onClick={doRefresh} disabled={refreshing}>
                {refreshing ? <span style={s.spinner} /> : null}
                刷新
              </button>
            </div>
          </div>
          {board !== null ? (
            <>
              <div style={s.filters}>
                <select style={s.select} value={filterStatus} onChange={e => setFilterStatus(e.currentTarget.value)}>
                  <option value="">状态: 全部</option>
                  {statuses.map(st => <option key={st} value={st}>{st}</option>)}
                </select>
                <select style={s.select} value={filterPriority} onChange={e => setFilterPriority(e.currentTarget.value)}>
                  <option value="">等级: 全部</option>
                  {priorities.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
                {selected.size > 0 ? (
                  <div style={s.batchBar}>
                    <span style={{ color: 'var(--dsw-alias-label-tertiary)', fontSize: '12px' }}>已选 {selected.size} 项</span>
                    <button style={{ ...s.btn, ...s.actionPrimary }} onClick={() => batchAction('analyze')}>批量开始分析</button>
                    <button style={s.btn} onClick={() => batchAction('fix')}>批量开始修复</button>
                    <button style={s.btn} onClick={() => setSelected(new Set())}>清空</button>
                  </div>
                ) : null}
              </div>
              <div style={s.scroll}>
                <div style={s.stats}>
                  <span>优先级: {Object.entries(board.byPriority).map(([k, v]) => `${k}=${v}`).join(' ') || '-'}</span>
                  <span>fix-db 已登记: {board.fixdbRegistered}/{board.count}</span>
                  <span>MR 合入: {board.merged}/{board.count}</span>
                  <span>{new Date(board.fetchedAt).toLocaleString()}</span>
                </div>
                <table style={s.table}>
                  <thead>
                    <tr>
                      <th style={s.thNoSort}>#</th>
                      <th style={s.thNoSort}><input type="checkbox" checked={selected.size === rows.length && rows.length > 0}
                        onChange={() => {
                          if (selected.size === rows.length) setSelected(new Set())
                          else setSelected(new Set(rows.map(r => r.issId)))
                        }} /></th>
                      <th style={s.th} onClick={() => toggleSort('issId')}>issId{sortArrow('issId')}</th>
                      <th style={s.th} onClick={() => toggleSort('priority')}>优先级{sortArrow('priority')}</th>
                      <th style={s.th} onClick={() => toggleSort('status')}>状态{sortArrow('status')}</th>
                      <th style={s.th}>fix-db</th>
                      <th style={s.th}>MR</th>
                      <th style={s.th}>合入</th>
                      <th style={s.th} onClick={() => toggleSort('title')}>标题{sortArrow('title')}</th>
                      <th style={s.th}>标注</th>
                      <th style={s.th}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => {
                      const noteValue = row.fixdb !== null && typeof row.fixdb.note === 'string' ? row.fixdb.note : ''
                      const f = row.fixdb
                      const conclusion = f !== null && typeof f.conclusion === 'string' ? f.conclusion : ''
                      const timeline = f !== null && Array.isArray(f.timeline) ? f.timeline as string[] : []
                      return (
                        <tr key={row.issId}>
                          <td style={s.td}>{index + 1}</td>
                          <td style={s.td}>
                            <input type="checkbox" checked={selected.has(row.issId)} onChange={() => toggleSelected(row.issId)} />
                          </td>
                          <td style={s.td}>
                            {row.issueId !== undefined ? (
                              <a style={s.link} href={`${IPD_ITEM_BASE}${row.issueId}`} target="_blank" rel="noreferrer">{row.issId}</a>
                            ) : row.issId}
                          </td>
                          <td style={s.td}>
                            <span style={{ ...s.badge, background: badgeColor(PRIORITY_COLOR, row.priority) }}>{row.priority || '-'}</span>
                          </td>
                          <td style={s.td}>
                            <span style={{ ...s.badge, background: badgeColor(STATUS_COLOR, row.status) }}>{row.status || '-'}</span>
                          </td>
                          <td style={s.td}>
                            {f === null ? <span style={s.grey}>-</span> : (
                              <div>
                                <span style={s.grey}>{typeof f.status === 'string' ? f.status : '-'}</span>
                                {conclusion !== '' ? <div style={s.conclusion} title={conclusion}>{conclusion}</div> : null}
                                {expanded.has(row.issId) ? (
                                  <div style={s.detail}>
                                    {conclusion !== '' ? <div><b>结论:</b> {conclusion}</div> : null}
                                    <div><b>更新时间:</b> {typeof f.updated_at === 'string' ? f.updated_at : '-'}</div>
                                    {timeline.length > 0 ? (
                                      <div><b>记录:</b>{timeline.slice(-8).map((t, i) => <div key={i}>· {t}</div>)}</div>
                                    ) : null}
                                  </div>
                                ) : null}
                                <div>
                                  <button style={s.expand} onClick={() => setExpanded(s => {
                                    const next = new Set(s)
                                    if (next.has(row.issId)) next.delete(row.issId)
                                    else next.add(row.issId)
                                    return next
                                  })}>{expanded.has(row.issId) ? '收起' : '详情'}</button>
                                </div>
                              </div>
                            )}
                          </td>
                          <td style={s.td}>
                            {mrNumbers(row).map(n => (
                              <a key={n} style={s.link} href={`${board.mrBaseUrl}${n}`} target="_blank" rel="noreferrer">!{n} </a>
                            ))}
                          </td>
                          <td style={s.td}>{mergeCell(row)}</td>
                          <td style={s.titleTd} title={row.title}>
                            {row.issueId !== undefined ? (
                              <a style={s.link} href={`${IPD_ITEM_BASE}${row.issueId}`} target="_blank" rel="noreferrer">{row.title}</a>
                            ) : row.title}
                          </td>
                          <td style={s.td}>
                            <input
                              style={{ ...s.note, ...(noteValue !== '' ? s.noteFilled : {}) }}
                              defaultValue={noteValue}
                              placeholder="标注…"
                              onBlur={e => {
                                const v = e.currentTarget.value.trim()
                                if (v !== '' && v !== noteValue) saveNote(current, row.issId, v)
                              }}
                            />
                          </td>
                          <td style={s.td}>
                            {renderActions(row)}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {rows.length === 0 ? <div style={s.empty}>暂无待办问题。</div> : null}
                {rows.length < board.count ? (
                  <div style={{ ...s.empty, padding: '4px 0' }}>仅显示前 {rows.length} 条, 共 {board.count} 条</div>
                ) : null}
              </div>
            </>
          ) : (
            <div style={{ ...s.empty, padding: '24px 16px' }}>
              看板未加载 — 点"刷新"运行 /ipd-board 拉取数据, 或先在聊天里敲 /ipd-board。
            </div>
          )}
        </div>
      ) : null}
    </>
  )
}
