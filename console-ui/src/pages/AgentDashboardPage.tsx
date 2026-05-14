import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bot, ExternalLink, FileText, Image as ImageIcon, Loader2, MessageSquare, Play, Power, RefreshCw, Send, Settings, Terminal, X, Zap } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { StatusBadge } from '../components/ui/StatusBadge'
import { normalizeStatusKind } from '../lib/statusSemantics'
import { cn } from '../lib/utils'
import { useTaskFloater } from '../stores/taskFloater'

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

const AGENT_STATUS_LABEL: Record<AgentStatus, string> = {
  running: 'running',
  available: 'available',
  unavailable: 'unavailable',
}

const ROUTE_AGENT_NAME: Record<string, AgentName> = {
  nanobot: 'nanobot',
  codex: 'codex',
  'claude-code': 'claude_code',
  claude_code: 'claude_code',
  'image-gen': 'image_gen',
  image_gen: 'image_gen',
}

const AGENT_DETAIL_META: Record<AgentName, {
  configLabel: string
  configPath: string
  configRoute?: string
  docs: string[]
  persona: string
}> = {
  nanobot: {
    configLabel: 'Nanobot config.json',
    configPath: 'config.json',
    configRoute: '/settings/agents-config/nanobot/config',
    docs: ['AGENTS.md', 'MEMORY.md', 'USER.md'],
    persona: 'Nanobot persona and memory are managed by the Nanobot-specific tabs.',
  },
  codex: {
    configLabel: 'Codex config.toml',
    configPath: 'console/agents/codex/config.toml',
    configRoute: '/settings/agents-config/codex/config',
    docs: ['AGENTS.md'],
    persona: 'Codex reads repository instructions and workspace AGENTS.md.',
  },
  claude_code: {
    configLabel: 'Claude Code settings.json',
    configPath: 'console/agents/claude_code/settings.json',
    configRoute: '/settings/agents-config/claude-code/config',
    docs: ['CLAUDE.md'],
    persona: 'Claude Code reads project CLAUDE.md and its local settings.',
  },
  image_gen: {
    configLabel: 'Image generation config',
    configPath: 'console/agents/image_gen/config.json',
    configRoute: '/settings/agents-config/image-gen/config',
    docs: ['Image prompt and media artifact records'],
    persona: 'Image Gen is provider-backed and uses prompt plus optional reference image.',
  },
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
  const { open: openTaskFloater } = useTaskFloater()
  const Icon = AGENT_ICON[agent.name] || Bot
  const statusKind = normalizeStatusKind(agent.status)
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
            <StatusBadge kind={statusKind} label={AGENT_STATUS_LABEL[agent.status]} />
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
          <div className="rounded-lg border border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] px-2 py-1.5 text-xs text-[var(--ava-danger)]">
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
            onClick={() => navigate('/')}
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
            onClick={() => openTaskFloater({ panel: 'background', bgView: 'current' })}
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
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--ava-danger-border)] px-3 text-sm text-[var(--ava-danger)] hover:bg-[var(--ava-danger-soft)]"
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

function AgentDetail({
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
  const { open: openTaskFloater } = useTaskFloater()
  const Icon = AGENT_ICON[agent.name] || Bot
  const statusKind = normalizeStatusKind(agent.status)
  const meta = AGENT_DETAIL_META[agent.name]

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <div className="flex flex-wrap items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-tertiary)] text-[var(--accent)]">
            <Icon className="h-6 w-6" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-[var(--text-primary)]">{agent.display_name}</h1>
              <StatusBadge kind={statusKind} label={AGENT_STATUS_LABEL[agent.status]} size="md" />
            </div>
            <p className="mt-1 break-all font-mono text-xs text-[var(--text-secondary)]">{agent.instance_id}</p>
          </div>
          <button
            type="button"
            onClick={() => navigate('/settings/agents-config')}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            Overview
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
            <p className="text-xs text-[var(--text-secondary)]">Version</p>
            <p className="mt-1 min-h-5 truncate font-mono text-sm text-[var(--text-primary)]">{agent.version || '-'}</p>
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
            <p className="text-xs text-[var(--text-secondary)]">Kind</p>
            <p className="mt-1 font-mono text-sm text-[var(--text-primary)]">{agent.kind}</p>
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
            <p className="text-xs text-[var(--text-secondary)]">Active tasks</p>
            <p className="mt-1 font-mono text-sm text-[var(--text-primary)]">{agent.active_tasks}</p>
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
            <p className="text-xs text-[var(--text-secondary)]">Startup</p>
            <p className="mt-1 text-sm text-[var(--text-primary)]">{agent.status === 'running' ? 'current process' : '-'}</p>
          </div>
        </div>

        {agent.path && (
          <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
            <p className="text-xs text-[var(--text-secondary)]">Path</p>
            <p className="mt-1 break-all font-mono text-xs text-[var(--text-primary)]">{agent.path}</p>
          </div>
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <div className="mb-3 flex items-center gap-2">
            <Settings className="h-4 w-4 text-[var(--accent)]" />
            <h2 className="text-base font-semibold text-[var(--text-primary)]">Configuration</h2>
          </div>
          <div className="grid gap-2 text-sm">
            <div className="flex justify-between gap-3">
              <span className="text-[var(--text-secondary)]">Source</span>
              <span className="font-medium text-[var(--text-primary)]">{meta.configLabel}</span>
            </div>
            <div className="grid gap-1">
              <span className="text-[var(--text-secondary)]">Path</span>
              <span className="break-all rounded-lg bg-[var(--bg-primary)] px-2 py-1 font-mono text-xs text-[var(--text-primary)]">{meta.configPath}</span>
            </div>
            {meta.configRoute ? (
              <button
                type="button"
                onClick={() => navigate(meta.configRoute!)}
                className="mt-2 inline-flex h-9 w-fit items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                <FileText className="h-4 w-4" />
                Edit Config
              </button>
            ) : null}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <div className="mb-3 flex items-center gap-2">
            <FileText className="h-4 w-4 text-[var(--accent)]" />
            <h2 className="text-base font-semibold text-[var(--text-primary)]">Docs & Instructions</h2>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {meta.docs.map((doc) => (
              <span key={doc} className="rounded bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)]">
                {doc}
              </span>
            ))}
          </div>
          <p className="mt-3 text-sm text-[var(--text-secondary)]">{meta.persona}</p>
          {agent.name === 'nanobot' && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => navigate('/settings/agents-config/nanobot/memory')}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                Memory
              </button>
              <button
                type="button"
                onClick={() => navigate('/settings/agents-config/nanobot/persona')}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-primary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                Persona
              </button>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">Actions</h2>
        <div className="flex flex-wrap gap-2">
          {agent.installed && (agent.capabilities.supports_chat || agent.capabilities.supports_task) && (
            <button
              type="button"
              onClick={() => navigate('/')}
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
              onClick={() => openTaskFloater({ panel: 'background', bgView: 'current' })}
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
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--ava-danger-border)] px-3 text-sm text-[var(--ava-danger)] hover:bg-[var(--ava-danger-soft)]"
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
        </div>
      </section>

      {(agent.recent_events.length > 0 || agent.recent_artifacts.length > 0) && (
        <section className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
            <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">Recent Events</h2>
            <div className="space-y-2">
              {agent.recent_events.length > 0 ? agent.recent_events.map((event) => (
                <div key={`${event.task_id}-${event.event}-${event.timestamp}`} className="rounded-lg bg-[var(--bg-primary)] p-3 text-xs">
                  <div className="flex items-center gap-2 text-[var(--text-primary)]">
                    <span className="font-mono">{event.event}</span>
                    <span className="truncate text-[var(--text-secondary)]">{event.task_id}</span>
                  </div>
                  {event.detail && <p className="mt-1 line-clamp-2 text-[var(--text-secondary)]">{event.detail}</p>}
                </div>
              )) : <p className="text-sm text-[var(--text-secondary)]">No recent events.</p>}
            </div>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
            <h2 className="mb-3 text-base font-semibold text-[var(--text-primary)]">Artifacts</h2>
            <div className="space-y-2">
              {agent.recent_artifacts.length > 0 ? agent.recent_artifacts.map((artifact) => (
                <div key={`${artifact.task_id}-${artifact.type}`} className="rounded-lg bg-[var(--bg-primary)] p-3 text-xs">
                  <div className="flex items-center gap-2 text-[var(--text-primary)]">
                    <span className="font-mono">{artifact.type}</span>
                    <span className="truncate text-[var(--text-secondary)]">{artifact.task_id}</span>
                  </div>
                  <p className="mt-1 line-clamp-3 text-[var(--text-secondary)]">{artifact.preview}</p>
                </div>
              )) : <p className="text-sm text-[var(--text-secondary)]">No recent artifacts.</p>}
            </div>
          </div>
        </section>
      )}
    </div>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 sm:p-4">
      <section className="max-h-[calc(100vh-2rem)] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4 shadow-xl">
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
  const { agentKind } = useParams()
  const [data, setData] = useState<AgentsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [taskDraft, setTaskDraft] = useState<TaskDraft | null>(null)
  const [submittingTask, setSubmittingTask] = useState(false)
  const canRestart = true
  const canRunTasks = true

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
  const detailAgentName = agentKind ? ROUTE_AGENT_NAME[agentKind] : undefined
  const detailAgent = detailAgentName ? agents.find((agent) => agent.name === detailAgentName) : null
  const running = data?.summary.running ?? 0
  const available = data?.summary.available ?? 0
  const unavailable = useMemo(
    () => agents.filter((agent) => !agent.installed).length,
    [agents],
  )

  if (detailAgentName) {
    return (
      <div>
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
        ) : detailAgent ? (
          <AgentDetail
            agent={detailAgent}
            canRunTasks={canRunTasks}
            canRestart={canRestart}
            onCancelTasks={handleCancelTasks}
            onStartTask={handleStartTask}
            onRestart={handleRestart}
          />
        ) : (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-6 text-sm text-[var(--text-secondary)]">
            Agent not found: {agentKind}
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

  return (
    <div className="p-4 md:p-6">
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
