import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bot, CheckCircle2, ExternalLink, Image as ImageIcon, Loader2, MessageSquare, Play, Power, RefreshCw, Send, Terminal, X, XCircle, Zap } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { cn } from '../lib/utils'
import { useAuth } from '../stores/auth'

type AgentStatus = 'running' | 'available' | 'unavailable'
type AgentName = 'nanobot' | 'claude_code' | 'codex' | 'image_gen'
type DirectTaskAgentName = Exclude<AgentName, 'nanobot'>
type DirectTaskMode = 'standard' | 'readonly'

interface AgentCapabilities {
  supports_chat: boolean
  supports_task: boolean
  supports_cancel: boolean
  supports_restart: boolean
  supports_streaming: boolean
  supports_artifacts: boolean
  max_concurrent_tasks: number
  supported_artifact_types: string[]
}

interface AgentEvent {
  task_id: string
  timestamp: number | null
  event: string
  detail: string
}

interface AgentArtifact {
  task_id: string
  type: string
  preview: string
}

interface AgentInfo {
  name: AgentName
  instance_id: string
  display_name: string
  kind: 'managed' | 'cli' | 'provider'
  status: AgentStatus
  installed: boolean
  path: string
  version: string
  detail: string
  install_url: string
  active_tasks: number
  recent_events: AgentEvent[]
  recent_artifacts: AgentArtifact[]
  capabilities: AgentCapabilities
}

interface AgentsResponse {
  agents: AgentInfo[]
  summary: {
    total: number
    available: number
    running: number
  }
}

interface CancelAgentTasksResponse {
  cancelled: number
  message: string
}

interface DirectTaskSubmitResponse {
  task_id: string
  status: string
  task_type: DirectTaskAgentName
  trace_id?: string
}

interface TaskDraft {
  agent: AgentInfo
  prompt: string
  project_path: string
  mode: DirectTaskMode
  reference_image: string
}

const AGENT_ICON: Record<AgentName, typeof Bot> = {
  nanobot: Bot,
  claude_code: Terminal,
  codex: Zap,
  image_gen: ImageIcon,
}

const STATUS_STYLE: Record<AgentStatus, { label: string; icon: typeof CheckCircle2; className: string }> = {
  running: { label: 'running', icon: Loader2, className: 'bg-blue-500/10 text-blue-400' },
  available: { label: 'available', icon: CheckCircle2, className: 'bg-emerald-500/10 text-emerald-400' },
  unavailable: { label: 'unavailable', icon: XCircle, className: 'bg-red-500/10 text-red-400' },
}

function AgentCard({
  agent,
  canRunTasks,
  canRestart,
  onCancelTasks,
  onStartTask,
  onRestart,
}: {
  agent: AgentInfo
  canRunTasks: boolean
  canRestart: boolean
  onCancelTasks: (agent: AgentInfo) => void
  onStartTask: (agent: AgentInfo) => void
  onRestart: (agent: AgentInfo) => void
}) {
  const navigate = useNavigate()
  const Icon = AGENT_ICON[agent.name] || Bot
  const status = STATUS_STYLE[agent.status]
  const StatusIcon = status.icon
  const artifacts = agent.capabilities.supported_artifact_types

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
      <div className="mb-4 flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-tertiary)] text-[var(--accent)]">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">{agent.display_name}</h2>
            <span className={cn('inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium', status.className)}>
              <StatusIcon className={cn('h-3.5 w-3.5', agent.status === 'running' && 'animate-spin')} />
              {status.label}
            </span>
          </div>
          <p className="mt-1 break-all font-mono text-xs text-[var(--text-secondary)]">{agent.instance_id}</p>
        </div>
      </div>

      <div className="grid gap-2 text-sm">
        <div className="flex justify-between gap-3">
          <span className="text-[var(--text-secondary)]">Kind</span>
          <span className="font-mono text-[var(--text-primary)]">{agent.kind}</span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-[var(--text-secondary)]">Active tasks</span>
          <span className="font-mono text-[var(--text-primary)]">{agent.active_tasks}</span>
        </div>
        {agent.version && (
          <div className="flex justify-between gap-3">
            <span className="text-[var(--text-secondary)]">Version</span>
            <span className="min-w-0 truncate font-mono text-[var(--text-primary)]">{agent.version}</span>
          </div>
        )}
        {agent.path && (
          <div className="grid gap-1">
            <span className="text-[var(--text-secondary)]">Path</span>
            <span className="break-all rounded-lg bg-[var(--bg-primary)] px-2 py-1 font-mono text-xs text-[var(--text-primary)]">{agent.path}</span>
          </div>
        )}
        {agent.detail && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-xs text-red-300">
            {agent.detail}
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {agent.capabilities.supports_chat && <span className="rounded bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)]">chat</span>}
        {agent.capabilities.supports_task && <span className="rounded bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)]">task</span>}
        {agent.capabilities.supports_cancel && <span className="rounded bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)]">cancel</span>}
        {artifacts.map((artifact) => (
          <span key={artifact} className="rounded bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)]">{artifact}</span>
        ))}
      </div>

      {(agent.recent_events.length > 0 || agent.recent_artifacts.length > 0) && (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {agent.recent_events.length > 0 && (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
              <p className="mb-2 text-xs font-medium text-[var(--text-secondary)]">Recent events</p>
              <div className="space-y-2">
                {agent.recent_events.map((event) => (
                  <div key={`${event.task_id}-${event.event}-${event.timestamp}`} className="text-xs">
                    <div className="flex items-center gap-2 text-[var(--text-primary)]">
                      <span className="font-mono">{event.event}</span>
                      <span className="truncate text-[var(--text-secondary)]">{event.task_id}</span>
                    </div>
                    {event.detail && <p className="mt-0.5 line-clamp-2 text-[var(--text-secondary)]">{event.detail}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {agent.recent_artifacts.length > 0 && (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
              <p className="mb-2 text-xs font-medium text-[var(--text-secondary)]">Artifacts</p>
              <div className="space-y-2">
                {agent.recent_artifacts.map((artifact) => (
                  <div key={`${artifact.task_id}-${artifact.type}`} className="text-xs">
                    <div className="flex items-center gap-2 text-[var(--text-primary)]">
                      <span className="font-mono">{artifact.type}</span>
                      <span className="truncate text-[var(--text-secondary)]">{artifact.task_id}</span>
                    </div>
                    <p className="mt-0.5 line-clamp-3 text-[var(--text-secondary)]">{artifact.preview}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {agent.installed && (agent.capabilities.supports_chat || agent.capabilities.supports_task) && (
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <MessageSquare className="h-4 w-4" />
            Chat
          </button>
        )}
        {agent.installed && agent.capabilities.supports_task && canRunTasks && (
          <button
            type="button"
            onClick={() => onStartTask(agent)}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <Play className="h-4 w-4" />
            Run Task
          </button>
        )}
        {agent.active_tasks > 0 && (
          <button
            type="button"
            onClick={() => navigate('/bg-tasks')}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <ExternalLink className="h-4 w-4" />
            Tasks
          </button>
        )}
        {agent.active_tasks > 0 && agent.capabilities.supports_cancel && (
          <button
            type="button"
            onClick={() => onCancelTasks(agent)}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-red-500/30 px-3 text-sm text-red-300 hover:bg-red-500/10"
          >
            Cancel
          </button>
        )}
        {canRestart && agent.capabilities.supports_restart && (
          <button
            type="button"
            onClick={() => onRestart(agent)}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <Power className="h-4 w-4" />
            Restart
          </button>
        )}
        {!agent.installed && agent.install_url && (
          <a
            href={agent.install_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            <ExternalLink className="h-4 w-4" />
            Install
          </a>
        )}
      </div>
    </section>
  )
}

function TaskModal({
  draft,
  submitting,
  onChange,
  onClose,
  onSubmit,
}: {
  draft: TaskDraft
  submitting: boolean
  onChange: (draft: TaskDraft) => void
  onClose: () => void
  onSubmit: () => void
}) {
  const isImageTask = draft.agent.name === 'image_gen'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <section className="w-full max-w-xl rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4 shadow-xl">
        <div className="mb-4 flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">Run {draft.agent.display_name} Task</h2>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">{draft.agent.instance_id}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            onSubmit()
          }}
        >
          <textarea
            rows={5}
            value={draft.prompt}
            onChange={(event) => onChange({ ...draft, prompt: event.currentTarget.value })}
            placeholder={isImageTask ? 'Image prompt' : 'Task prompt'}
            className="block w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
          />

          {isImageTask ? (
            <input
              type="text"
              value={draft.reference_image}
              onChange={(event) => onChange({ ...draft, reference_image: event.currentTarget.value })}
              placeholder="Reference image path"
              className="block h-10 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <input
                type="text"
                value={draft.project_path}
                onChange={(event) => onChange({ ...draft, project_path: event.currentTarget.value })}
                placeholder="Project path"
                className="block h-10 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
              />
              <select
                value={draft.mode}
                onChange={(event) => onChange({ ...draft, mode: event.currentTarget.value as DirectTaskMode })}
                className="h-10 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
              >
                <option value="standard">standard</option>
                <option value="readonly">readonly</option>
              </select>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="h-9 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !draft.prompt.trim()}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-[var(--accent)] px-3 text-sm text-white hover:bg-[var(--accent-hover)] disabled:opacity-40"
            >
              <Send className="h-3.5 w-3.5" />
              Submit
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}

export default function AgentDashboardPage() {
  const [data, setData] = useState<AgentsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [taskDraft, setTaskDraft] = useState<TaskDraft | null>(null)
  const [submittingTask, setSubmittingTask] = useState(false)
  const { isAdmin, user } = useAuth()
  const canRestart = isAdmin()
  const canRunTasks = user?.role === 'admin' || user?.role === 'editor'

  const loadAgents = useCallback(() => {
    setLoading(true)
    setError('')
    api<AgentsResponse>('/agents')
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load agents'))
      .finally(() => setLoading(false))
  }, [])

  const handleCancelTasks = useCallback(async (agent: AgentInfo) => {
    if (!window.confirm(`Cancel active ${agent.display_name} task(s)?`)) return
    setError('')
    setMessage('')
    try {
      const result = await api<CancelAgentTasksResponse>(`/agents/${encodeURIComponent(agent.name)}/tasks/cancel`, {
        method: 'POST',
      })
      setMessage(result.message || `Cancelled ${result.cancelled} task(s).`)
      loadAgents()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel tasks')
    }
  }, [loadAgents])

  const handleStartTask = useCallback((agent: AgentInfo) => {
    if (!agent.capabilities.supports_task) return
    setTaskDraft({
      agent,
      prompt: '',
      project_path: '',
      mode: 'standard',
      reference_image: '',
    })
    setError('')
    setMessage('')
  }, [])

  const handleSubmitTask = useCallback(async () => {
    if (!taskDraft) return
    const prompt = taskDraft.prompt.trim()
    if (!prompt) return
    setSubmittingTask(true)
    setError('')
    setMessage('')
    try {
      const params = taskDraft.agent.name === 'image_gen'
        ? {
            ...(taskDraft.reference_image.trim()
              ? { reference_image: taskDraft.reference_image.trim() }
              : {}),
          }
        : { mode: taskDraft.mode }
      const result = await api<DirectTaskSubmitResponse>('/console/direct-tasks', {
        method: 'POST',
        body: JSON.stringify({
          task_type: taskDraft.agent.name,
          prompt,
          session_key: 'console:agent-dashboard',
          conversation_id: 'agent-dashboard',
          project_path: taskDraft.project_path.trim() || undefined,
          params,
        }),
      })
      setMessage(`${taskDraft.agent.display_name} task ${result.task_id} submitted.`)
      setTaskDraft(null)
      loadAgents()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit task')
    } finally {
      setSubmittingTask(false)
    }
  }, [loadAgents, taskDraft])

  const handleRestart = useCallback(async (agent: AgentInfo) => {
    if (agent.name !== 'nanobot') return
    if (!window.confirm('Restart Nanobot gateway?')) return
    setError('')
    setMessage('')
    try {
      await api('/gateway/restart', {
        method: 'POST',
        body: JSON.stringify({ delay_ms: 5000, force: false }),
      })
      setMessage('Nanobot gateway restart scheduled.')
      loadAgents()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restart agent')
    }
  }, [loadAgents])

  useEffect(() => {
    loadAgents()
    const timer = window.setInterval(loadAgents, 10000)
    return () => window.clearInterval(timer)
  }, [loadAgents])

  const agents = data?.agents ?? []
  const running = data?.summary.running ?? 0
  const available = data?.summary.available ?? 0
  const unavailable = useMemo(
    () => agents.filter((agent) => !agent.installed).length,
    [agents],
  )

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Agent Dashboard</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Runtime registry and direct-control readiness.</p>
        </div>
        <button
          type="button"
          onClick={loadAgents}
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          Refresh
        </button>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <p className="text-xs uppercase text-[var(--text-secondary)]">Available</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{available}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <p className="text-xs uppercase text-[var(--text-secondary)]">Running</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{running}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <p className="text-xs uppercase text-[var(--text-secondary)]">Unavailable</p>
          <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{unavailable}</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">{error}</div>
      )}
      {message && (
        <div className="mb-4 rounded-lg bg-[var(--success)]/10 p-3 text-sm text-[var(--success)]">{message}</div>
      )}

      {loading && !data ? (
        <div className="flex items-center justify-center py-16 text-[var(--text-secondary)]">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {agents.map((agent) => (
            <AgentCard
              key={agent.instance_id}
              agent={agent}
              canRunTasks={canRunTasks}
              canRestart={canRestart}
              onCancelTasks={handleCancelTasks}
              onStartTask={handleStartTask}
              onRestart={handleRestart}
            />
          ))}
        </div>
      )}

      {taskDraft && (
        <TaskModal
          draft={taskDraft}
          submitting={submittingTask}
          onChange={setTaskDraft}
          onClose={() => setTaskDraft(null)}
          onSubmit={handleSubmitTask}
        />
      )}
    </div>
  )
}
