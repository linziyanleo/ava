import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import {
  RefreshCw,
  XCircle,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  XOctagon,
  Loader2,
  Clock,
  Ban,
  Wifi,
  WifiOff,
  History,
  Terminal,
  Zap,
  Code,
  FolderOpen,
  GitBranch,
  X,
} from 'lucide-react'
import { api, wsUrl } from '../api/client'
import { useAuth } from '../stores/auth'

interface TimelineEvent {
  timestamp: number
  event: string
  detail: string
}

interface TaskItem {
  task_id: string
  task_type: string
  origin_session_key: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  prompt_preview: string
  started_at: number | null
  finished_at: number | null
  elapsed_ms: number
  result_preview: string
  error_message: string
  timeline: TimelineEvent[]
  phase: string
  last_tool_name: string
  todo_summary: Record<string, number> | null
  project_path: string
  cli_run_id: string
  cli_session_id: string
  repo_root: string
  workdir_relpath: string
  workspace_key: string
  workspace_id: string
  execution_cwd: string
  isolation_mode: 'inplace' | 'worktree'
  branch_name: string
  worktree_path: string
}

interface TasksResponse {
  running: number
  total: number
  tasks: TaskItem[]
}

interface HistoryResponse {
  tasks: TaskItem[]
  total: number
  page: number
  page_size: number
}

// --- Module B: Task type visual config ---

const TASK_TYPE_STYLE: Record<string, {
  icon: typeof Terminal
  accent: string
  accentBg: string
  label: string
}> = {
  claude_code: {
    icon: Terminal,
    accent: 'text-emerald-500',
    accentBg: 'bg-emerald-500/10',
    label: 'Claude Code',
  },
  codex: {
    icon: Zap,
    accent: 'text-sky-500',
    accentBg: 'bg-sky-500/10',
    label: 'Codex',
  },
  coding: {
    icon: Code,
    accent: 'text-violet-500',
    accentBg: 'bg-violet-500/10',
    label: 'Coding',
  },
}

const DEFAULT_TYPE_STYLE = {
  icon: Code,
  accent: 'text-gray-400',
  accentBg: 'bg-gray-400/10',
  label: 'Unknown',
}

const STATUS_CONFIG: Record<
  TaskItem['status'],
  { icon: typeof Clock; color: string; bg: string; label: string }
> = {
  queued: { icon: Clock, color: 'text-yellow-500', bg: 'bg-yellow-500/10', label: '排队中' },
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-500/10', label: '运行中' },
  succeeded: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-500/10', label: '成功' },
  failed: { icon: XOctagon, color: 'text-red-500', bg: 'bg-red-500/10', label: '失败' },
  cancelled: { icon: Ban, color: 'text-gray-400', bg: 'bg-gray-400/10', label: '已取消' },
}

function formatTime(ts: number | null): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const remainS = s % 60
  return `${m}m ${remainS}s`
}

function formatElapsed(startedAt: number | null): string {
  if (!startedAt) return '-'
  const elapsed = Math.floor(Date.now() / 1000 - startedAt)
  if (elapsed < 60) return `${elapsed}s`
  const m = Math.floor(elapsed / 60)
  const s = elapsed % 60
  return `${m}m ${s}s`
}

function repoBasename(repoRoot: string): string {
  if (!repoRoot) return ''
  const parts = repoRoot.replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || repoRoot
}

// --- Module A: Workspace grouping ---

interface WorkspaceGroup {
  key: string
  repoRoot: string
  relpath: string
  isolationMode: string
  tasks: TaskItem[]
}

function groupByWorkspace(tasks: TaskItem[]): WorkspaceGroup[] {
  const map = new Map<string, WorkspaceGroup>()
  for (const task of tasks) {
    const wk = task.workspace_key || ''
    let group = map.get(wk)
    if (!group) {
      group = {
        key: wk,
        repoRoot: task.repo_root || '',
        relpath: task.workdir_relpath || '',
        isolationMode: task.isolation_mode || 'inplace',
        tasks: [],
      }
      map.set(wk, group)
    }
    group.tasks.push(task)
  }
  return Array.from(map.values())
}

// --- Components ---

function StatusBadge({ status }: { status: TaskItem['status'] }) {
  const cfg = STATUS_CONFIG[status]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.color}`}>
      <Icon className={`w-3 h-3 ${status === 'running' ? 'animate-spin' : ''}`} />
      {cfg.label}
    </span>
  )
}

// --- Module C: Todo progress bar ---

function TodoProgressBar({ summary }: { summary: Record<string, number> }) {
  const done = summary.done || 0
  const doing = summary.doing || 0
  const todo = summary.todo || 0
  const total = done + doing + todo
  if (total === 0) return null

  const donePct = (done / total) * 100
  const doingPct = (doing / total) * 100

  return (
    <div className="flex items-center gap-2 mt-1.5">
      <div className="flex-1 h-1.5 rounded-full bg-[var(--bg-tertiary)] overflow-hidden flex">
        {donePct > 0 && (
          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${donePct}%` }} />
        )}
        {doingPct > 0 && (
          <div className="h-full bg-blue-500 transition-all" style={{ width: `${doingPct}%` }} />
        )}
      </div>
      <span className="text-[10px] text-[var(--text-secondary)] whitespace-nowrap">
        {done}/{total} done
      </span>
    </div>
  )
}

// --- Module D: Filter bar ---

type TypeFilter = 'all' | 'claude_code' | 'codex' | 'coding'
type StatusFilter = 'all' | 'running' | 'succeeded' | 'failed'

function FilterBar({
  typeFilter,
  statusFilter,
  onTypeChange,
  onStatusChange,
  onClear,
}: {
  typeFilter: TypeFilter
  statusFilter: StatusFilter
  onTypeChange: (v: TypeFilter) => void
  onStatusChange: (v: StatusFilter) => void
  onClear: () => void
}) {
  const hasFilter = typeFilter !== 'all' || statusFilter !== 'all'

  const typeOptions: { value: TypeFilter; label: string }[] = [
    { value: 'all', label: '全部' },
    { value: 'claude_code', label: 'Claude Code' },
    { value: 'codex', label: 'Codex' },
    { value: 'coding', label: 'Coding' },
  ]

  const statusOptions: { value: StatusFilter; label: string }[] = [
    { value: 'all', label: '全部' },
    { value: 'running', label: '运行中' },
    { value: 'succeeded', label: '成功' },
    { value: 'failed', label: '失败' },
  ]

  return (
    <div className="flex items-center gap-3 mb-4 flex-wrap">
      <div className="flex items-center gap-1 rounded-lg bg-[var(--bg-secondary)] p-0.5">
        {typeOptions.map(opt => (
          <button
            key={opt.value}
            onClick={() => onTypeChange(opt.value)}
            className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
              typeFilter === opt.value
                ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] font-medium'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1 rounded-lg bg-[var(--bg-secondary)] p-0.5">
        {statusOptions.map(opt => (
          <button
            key={opt.value}
            onClick={() => onStatusChange(opt.value)}
            className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
              statusFilter === opt.value
                ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] font-medium'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {hasFilter && (
        <button
          onClick={onClear}
          className="flex items-center gap-1 px-2 py-1 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <X className="w-3 h-3" />
          清除筛选
        </button>
      )}
    </div>
  )
}

// --- Workspace group header (Module A) ---

function WorkspaceGroupHeader({ group, collapsed, onToggle }: {
  group: WorkspaceGroup
  collapsed: boolean
  onToggle: () => void
}) {
  const name = repoBasename(group.repoRoot)
  const isUnclassified = !group.key

  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-2 w-full text-left py-1.5 px-2 rounded-lg hover:bg-[var(--bg-secondary)] transition-colors group"
    >
      {collapsed ? <ChevronRight className="w-3.5 h-3.5 text-[var(--text-secondary)]" /> : <ChevronDown className="w-3.5 h-3.5 text-[var(--text-secondary)]" />}
      <FolderOpen className="w-3.5 h-3.5 text-[var(--accent)]" />
      {isUnclassified ? (
        <span className="text-xs font-medium text-[var(--text-secondary)]">未分类</span>
      ) : (
        <>
          <span className="text-xs font-medium text-[var(--text-primary)]">{name}</span>
          {group.relpath && group.relpath !== '.' && (
            <span className="text-xs text-[var(--text-secondary)] font-mono">: {group.relpath}</span>
          )}
        </>
      )}
      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
        group.isolationMode === 'worktree'
          ? 'bg-amber-500/10 text-amber-500'
          : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
      }`}>
        {group.isolationMode}
      </span>
      <span className="text-[10px] text-[var(--text-secondary)] ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
        {group.tasks.length} 个任务
      </span>
    </button>
  )
}

// --- TaskCard with Module B + C + D ---

interface TaskDetail {
  full_prompt: string
  full_result: string
}

function TaskCard({
  task,
  onCancel,
}: {
  task: TaskItem
  onCancel: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const isActive = task.status === 'queued' || task.status === 'running'

  const typeStyle = TASK_TYPE_STYLE[task.task_type] || DEFAULT_TYPE_STYLE
  const TypeIcon = typeStyle.icon

  const handleToggle = () => {
    const next = !expanded
    setExpanded(next)
    if (next && !detail && !detailLoading) {
      setDetailLoading(true)
      api<TaskDetail>(`/bg-tasks/${task.task_id}/detail`)
        .then(d => setDetail(d))
        .catch(() => {})
        .finally(() => setDetailLoading(false))
    }
  }

  const promptText = detail?.full_prompt || task.prompt_preview || '(no prompt)'
  const resultText = detail?.full_result || task.result_preview || ''

  return (
    <div
      className={`rounded-xl border transition-all ${
        isActive ? 'border-blue-500/30 bg-blue-500/5 shadow-sm' : 'border-[var(--border)] bg-[var(--bg-secondary)]'
      }`}
    >
      <div className="flex items-start gap-3 p-4 cursor-pointer select-none" onClick={handleToggle}>
        <div className="pt-0.5 text-[var(--text-secondary)]">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </div>

        <div className="flex-1 min-w-0">
          {/* Module B: type icon + accent badge */}
          <div className="flex items-center gap-2 mb-1">
            <StatusBadge status={task.status} />
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${typeStyle.accentBg} ${typeStyle.accent}`}>
              <TypeIcon className="w-3 h-3" />
              {typeStyle.label}
            </span>
            <span className="text-xs text-[var(--text-secondary)] font-mono">{task.task_id}</span>
          </div>

          <p
            className={`text-sm text-[var(--text-primary)] mb-1 ${expanded ? 'whitespace-pre-wrap break-words' : 'truncate'}`}
            title={task.prompt_preview}
          >
            {expanded ? promptText : task.prompt_preview || '(no prompt)'}
          </p>

          <div className="flex items-center gap-4 text-xs text-[var(--text-secondary)]">
            <span>{formatTime(task.started_at)}</span>
            {/* Module C: elapsed badge */}
            {isActive ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 font-medium">
                <Clock className="w-3 h-3" />
                {formatElapsed(task.started_at)}
              </span>
            ) : task.elapsed_ms > 0 ? (
              <span>{formatDuration(task.elapsed_ms)}</span>
            ) : null}
            {task.phase && isActive && (
              <span className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                {task.phase}
              </span>
            )}
            {task.repo_root && (
              <span className="inline-flex items-center gap-1 font-mono truncate max-w-[240px]" title={task.workspace_key}>
                <FolderOpen className="w-3 h-3 shrink-0" />
                {repoBasename(task.repo_root)}
                {task.workdir_relpath && task.workdir_relpath !== '.' && <>:{task.workdir_relpath}</>}
              </span>
            )}
            {task.branch_name && (
              <span className="inline-flex items-center gap-1" title={task.branch_name}>
                <GitBranch className="w-3 h-3 shrink-0" />
                {task.branch_name}
              </span>
            )}
          </div>

          {/* Module C: progress bar */}
          {isActive && task.todo_summary && (
            <TodoProgressBar summary={task.todo_summary} />
          )}
        </div>

        {isActive && (
          <button
            onClick={e => {
              e.stopPropagation();
              onCancel(task.task_id);
            }}
            className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
            title="取消任务"
          >
            <XCircle className="w-3.5 h-3.5" />
            取消
          </button>
        )}
      </div>

      {expanded && (
        <div className="px-4 pb-4 border-t border-[var(--border)]">
          <div className="pt-3 space-y-3">
            {resultText && (
              <div>
                <h4 className="text-xs font-medium text-[var(--text-secondary)] mb-1">结果</h4>
                <pre className="text-xs bg-[var(--bg-primary)] rounded-lg p-3 overflow-x-auto text-[var(--text-primary)] whitespace-pre-wrap break-all">
                  {resultText}
                </pre>
              </div>
            )}
            {task.error_message && (
              <div>
                <h4 className="text-xs font-medium text-red-400 mb-1">错误</h4>
                <pre className="text-xs bg-red-500/5 border border-red-500/20 rounded-lg p-3 overflow-x-auto text-red-300 whitespace-pre-wrap break-all">
                  {task.error_message}
                </pre>
              </div>
            )}

            {/* Module D: workspace metadata row */}
            {task.workspace_key && (
              <div>
                <h4 className="text-xs font-medium text-[var(--text-secondary)] mb-1">Workspace</h4>
                <div className="flex items-center gap-3 flex-wrap text-xs bg-[var(--bg-primary)] rounded-lg px-3 py-2">
                  <span className="inline-flex items-center gap-1 font-mono text-[var(--text-primary)]">
                    <FolderOpen className="w-3 h-3 text-[var(--accent)]" />
                    {task.workspace_id}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded font-medium ${
                    task.isolation_mode === 'worktree'
                      ? 'bg-amber-500/10 text-amber-500'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
                  }`}>
                    {task.isolation_mode}
                  </span>
                  {task.branch_name && (
                    <span className="inline-flex items-center gap-1 text-[var(--text-secondary)]">
                      <GitBranch className="w-3 h-3" />
                      {task.branch_name}
                    </span>
                  )}
                  {task.execution_cwd && (
                    <span className="text-[var(--text-secondary)] font-mono truncate max-w-[300px]" title={task.execution_cwd}>
                      CWD: {task.execution_cwd}
                    </span>
                  )}
                  {task.worktree_path && (
                    <span className="text-[var(--text-secondary)] font-mono truncate max-w-[300px]" title={task.worktree_path}>
                      WT: {task.worktree_path}
                    </span>
                  )}
                </div>
              </div>
            )}

            <div>
              <h4 className="text-xs font-medium text-[var(--text-secondary)] mb-1">详情</h4>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                <div>
                  <span className="text-[var(--text-secondary)]">Session: </span>
                  <span className="font-mono">{task.origin_session_key}</span>
                </div>
                <div>
                  <span className="text-[var(--text-secondary)]">CLI Run: </span>
                  <span className="font-mono">{task.cli_run_id || task.cli_session_id || '-'}</span>
                </div>
                <div>
                  <span className="text-[var(--text-secondary)]">Phase: </span>
                  {task.phase || '-'}
                </div>
                <div>
                  <span className="text-[var(--text-secondary)]">Last Tool: </span>
                  {task.last_tool_name || '-'}
                </div>
              </div>
            </div>

            {task.timeline && task.timeline.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-[var(--text-secondary)] mb-2">Timeline</h4>
                <div className="relative pl-4">
                  <div className="absolute left-1.5 top-1 bottom-1 w-px bg-[var(--border)]" />
                  {task.timeline.map((ev, i) => (
                    <div key={i} className="relative flex items-start gap-2 pb-2 last:pb-0">
                      <div className="absolute left-[-13px] top-1.5 w-2 h-2 rounded-full bg-[var(--accent)] border-2 border-[var(--bg-secondary)]" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-[var(--text-primary)]">{ev.event}</span>
                          <span className="text-[10px] text-[var(--text-secondary)]">{formatTime(ev.timestamp)}</span>
                        </div>
                        {ev.detail && (
                          <p className="text-[11px] text-[var(--text-secondary)] whitespace-pre-wrap break-words">
                            {ev.detail}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {detailLoading && (
              <div className="text-xs text-[var(--text-secondary)] flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> 加载完整内容...
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number
  totalPages: number
  onPageChange: (p: number) => void
}) {
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-2 pt-4">
      <button
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="p-1.5 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30 transition-colors"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>
      <span className="text-xs text-[var(--text-secondary)]">
        {page} / {totalPages}
      </span>
      <button
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="p-1.5 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30 transition-colors"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  )
}

export default function BgTasksPage() {
  const [data, setData] = useState<TasksResponse | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [historyPage, setHistoryPage] = useState(1)
  const [historyLoading, setHistoryLoading] = useState(false)
  const PAGE_SIZE = 15
  const { isMockTester } = useAuth()
  const mockMode = isMockTester()

  // Module D: filter state
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // Module A: workspace collapse state
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const connectWs = useCallback(() => {
    if (mockMode) {
      setWsConnected(false)
      return
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    try {
      const ws = new WebSocket(wsUrl('/bg-tasks/ws'))
      wsRef.current = ws
      ws.onopen = () => setWsConnected(true)
      ws.onclose = () => {
        setWsConnected(false)
        reconnectTimer.current = setTimeout(connectWs, 3000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'update') {
            setData({ running: msg.running, total: msg.total, tasks: msg.tasks })
          } else if (msg.type === 'error') {
            setError(msg.message)
          }
        } catch { /* ignore parse errors */ }
      }
    } catch {
      setWsConnected(false)
    }
  }, [mockMode])

  const fetchOnce = useCallback(async () => {
    try {
      const res = await api<TasksResponse>('/bg-tasks?include_finished=false')
      setData(res)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    }
  }, [])

  const fetchHistory = useCallback(async (page: number) => {
    setHistoryLoading(true)
    try {
      const res = await api<HistoryResponse>(`/bg-tasks/history?page=${page}&page_size=${PAGE_SIZE}`)
      setHistory({
        tasks: Array.isArray(res.tasks) ? res.tasks : [],
        total: res.total ?? 0,
        page: res.page ?? page,
        page_size: res.page_size ?? PAGE_SIZE,
      })
      setHistoryPage(page)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载历史失败')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchOnce()
    if (!mockMode) {
      connectWs()
    }
    return () => {
      wsRef.current?.close()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [fetchOnce, connectWs, mockMode])

  useEffect(() => {
    if (showHistory && !history) fetchHistory(1)
  }, [showHistory, history, fetchHistory])

  useEffect(() => {
    if (data && data.running > 0) {
      const timer = setInterval(() => setData(d => d ? { ...d } : d), 1000)
      return () => clearInterval(timer)
    }
  }, [data?.running])

  const handleCancel = async (taskId: string) => {
    try {
      await api(`/bg-tasks/${taskId}/cancel`, { method: 'POST' })
      fetchOnce()
    } catch (err) {
      setError(err instanceof Error ? err.message : '取消失败')
    }
  }

  const clearFilters = useCallback(() => {
    setTypeFilter('all')
    setStatusFilter('all')
  }, [])

  const applyFilters = useCallback((tasks: TaskItem[]) => {
    let filtered = tasks
    if (typeFilter !== 'all') {
      filtered = filtered.filter(t => t.task_type === typeFilter)
    }
    if (statusFilter !== 'all') {
      if (statusFilter === 'running') {
        filtered = filtered.filter(t => t.status === 'queued' || t.status === 'running')
      } else {
        filtered = filtered.filter(t => t.status === statusFilter)
      }
    }
    return filtered
  }, [typeFilter, statusFilter])

  const allTasks = data?.tasks ?? []
  const filteredTasks = useMemo(() => applyFilters(allTasks), [allTasks, applyFilters])

  const activeTasks = filteredTasks.filter(t => t.status === 'queued' || t.status === 'running')
  const recentFinished = filteredTasks.filter(t => t.status !== 'queued' && t.status !== 'running')

  // Module A: group active tasks by workspace
  const workspaceGroups = useMemo(() => groupByWorkspace(activeTasks), [activeTasks])

  const historyTotalPages = history ? Math.ceil(history.total / PAGE_SIZE) : 0

  const hasFilter = typeFilter !== 'all' || statusFilter !== 'all'

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">后台任务</h1>
          {data && data.running > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              {data.running} 运行中
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 text-xs ${wsConnected ? 'text-green-400' : 'text-[var(--text-secondary)]'}`}>
            {mockMode ? <Clock className="w-3 h-3" /> : wsConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {mockMode ? 'Mock' : wsConnected ? 'Live' : 'Offline'}
          </span>
          <button
            onClick={fetchOnce}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> 刷新
          </button>
        </div>
      </div>

      {/* Module D: filter bar */}
      {data && (allTasks.length > 0 || hasFilter) && (
        <FilterBar
          typeFilter={typeFilter}
          statusFilter={statusFilter}
          onTypeChange={setTypeFilter}
          onStatusChange={setStatusFilter}
          onClear={clearFilters}
        />
      )}

      {error && (
        <div className="mb-3 p-3 rounded-lg text-sm bg-[var(--danger)]/10 text-[var(--danger)]">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-6 pb-8">
        {!data ? (
          <div className="text-center py-20 text-[var(--text-secondary)]">
            <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
            加载中...
          </div>
        ) : activeTasks.length === 0 && recentFinished.length === 0 && !showHistory && !hasFilter ? (
          <div className="text-center py-20 text-[var(--text-secondary)]">
            <Clock className="w-8 h-8 mx-auto mb-3 opacity-40" />
            <p>暂无活跃任务</p>
            <p className="text-xs mt-1">通过 Claude Code 或 Codex 工具提交的异步编程任务将显示在这里</p>
            <button
              onClick={() => setShowHistory(true)}
              className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <History className="w-3.5 h-3.5" /> 查看历史任务
            </button>
          </div>
        ) : (
          <>
            {/* Module A: workspace-grouped active tasks */}
            {workspaceGroups.length > 0 && (
              <section>
                <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                  活跃 Workspace ({workspaceGroups.length})
                </h2>
                <div className="space-y-3">
                  {workspaceGroups.map(group => {
                    const isCollapsed = collapsedGroups.has(group.key)
                    return (
                      <div key={group.key || '__unclassified__'} className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)]/50 overflow-hidden">
                        <WorkspaceGroupHeader
                          group={group}
                          collapsed={isCollapsed}
                          onToggle={() => toggleGroup(group.key)}
                        />
                        {!isCollapsed && (
                          <div className="px-2 pb-2 space-y-2">
                            {group.tasks.map(t => (
                              <TaskCard key={t.task_id} task={t} onCancel={handleCancel} />
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {recentFinished.length > 0 && (
              <section>
                <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-2">
                  最近完成 ({recentFinished.length})
                </h2>
                <div className="space-y-2">
                  {recentFinished.map(t => (
                    <TaskCard key={t.task_id} task={t} onCancel={handleCancel} />
                  ))}
                </div>
              </section>
            )}

            {hasFilter && activeTasks.length === 0 && recentFinished.length === 0 && (
              <div className="text-center py-12 text-[var(--text-secondary)]">
                <p className="text-sm">无匹配任务</p>
                <button onClick={clearFilters} className="mt-2 text-xs text-[var(--accent)] hover:underline">
                  清除筛选条件
                </button>
              </div>
            )}
          </>
        )}

        {/* History section */}
        <section className="border-t border-[var(--border)] pt-4">
          <button
            onClick={() => setShowHistory(v => !v)}
            className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors mb-3"
          >
            {showHistory ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            <History className="w-4 h-4" />
            历史任务
            {history && <span className="text-xs font-normal">({history.total})</span>}
          </button>

          {showHistory && (
            <>
              {historyLoading ? (
                <div className="text-center py-8 text-[var(--text-secondary)]">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-1" />
                  加载中...
                </div>
              ) : history && history.tasks.length > 0 ? (
                <>
                  <div className="space-y-2">
                    {history.tasks.map(t => (
                      <TaskCard key={t.task_id} task={t} onCancel={handleCancel} />
                    ))}
                  </div>
                  <Pagination
                    page={historyPage}
                    totalPages={historyTotalPages}
                    onPageChange={p => fetchHistory(p)}
                  />
                </>
              ) : (
                <div className="text-center py-8 text-[var(--text-secondary)] text-sm">
                  暂无历史任务
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
