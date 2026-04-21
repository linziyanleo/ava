import { useEffect, useRef, useState, useCallback } from 'react'
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

const TASK_TYPE_LABELS: Record<string, string> = {
  claude_code: 'Claude Code',
  codex: 'Codex',
  coding: 'Coding',
}

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
          <div className="flex items-center gap-2 mb-1">
            <StatusBadge status={task.status} />
            <span className="text-xs text-[var(--text-secondary)] font-mono">{task.task_id}</span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
              {TASK_TYPE_LABELS[task.task_type] || task.task_type}
            </span>
          </div>

          <p
            className={`text-sm text-[var(--text-primary)] mb-1 ${expanded ? 'whitespace-pre-wrap break-words' : 'truncate'}`}
            title={task.prompt_preview}
          >
            {expanded ? promptText : task.prompt_preview || '(no prompt)'}
          </p>

          <div className="flex items-center gap-4 text-xs text-[var(--text-secondary)]">
            <span>{formatTime(task.started_at)}</span>
            {isActive ? (
              <span className="text-blue-400">{formatElapsed(task.started_at)} elapsed</span>
            ) : task.elapsed_ms > 0 ? (
              <span>{formatDuration(task.elapsed_ms)}</span>
            ) : null}
            {task.project_path && (
              <span className="font-mono truncate max-w-[360px]" title={task.project_path}>
                {task.project_path}
              </span>
            )}
          </div>
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

  const activeTasks = data?.tasks.filter(t => t.status === 'queued' || t.status === 'running') ?? []
  const recentFinished = data?.tasks.filter(t => t.status !== 'queued' && t.status !== 'running') ?? []

  const historyTotalPages = history ? Math.ceil(history.total / PAGE_SIZE) : 0

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
        ) : activeTasks.length === 0 && recentFinished.length === 0 && !showHistory ? (
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
            {activeTasks.length > 0 && (
              <section>
                <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                  进行中 ({activeTasks.length})
                </h2>
                <div className="space-y-2">
                  {activeTasks.map(t => (
                    <TaskCard key={t.task_id} task={t} onCancel={handleCancel} />
                  ))}
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
