import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Box, Gauge, MemoryStick, Puzzle, type LucideIcon } from 'lucide-react'
import { api } from '../../api/client'
import type { ActiveChatTransport, DirectTaskMessage, SessionMeta } from './types'
import { formatTokenCount } from './utils'
import { buildTokenStatsNavUrl } from '../../lib/tokenStatsNav'
import { useTaskFloater } from '../../stores/taskFloater'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { useResponsiveMode } from '../../hooks/useResponsiveMode'

interface SkillSummary {
  name: string
  source?: string
  enabled?: boolean
  description?: string
}

interface GatewayStatusData {
  memory_rss_bytes?: number | null
}

interface HudWidget {
  id: string
  label: string
  value: string
  icon: LucideIcon
  onClick: () => void
}

function chipClass() {
  return 'inline-flex shrink-0 items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-2.5 py-1 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]'
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${Math.round(bytes / 1024 / 1024)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

export function HudBar({
  session,
  directTasks,
  onSkillSelect,
}: {
  session: SessionMeta | null
  directTasks: DirectTaskMessage[]
  activeTransport: ActiveChatTransport
  isReadOnly: boolean
  onSkillSelect?: (skillName: string) => void
}) {
  const navigate = useNavigate()
  const { open: openTaskFloater } = useTaskFloater()
  const { isMobile } = useResponsiveMode()
  const [skills, setSkills] = useState<SkillSummary[] | null>(null)
  const [skillsOpen, setSkillsOpen] = useState(false)
  const [memoryBytes, setMemoryBytes] = useState<number | null>(null)
  const artifacts = useWorkflowStore((state) => state.artifacts)
  const fetchArtifacts = useWorkflowStore((state) => state.fetchArtifacts)
  const artifactCount = useMemo(
    () => artifacts.length || directTasks.filter((task) => task.result_preview).length,
    [artifacts.length, directTasks],
  )

  useEffect(() => {
    let disposed = false
    api<{ skills: SkillSummary[] }>('/skills/list')
      .then((response) => {
        if (!disposed) setSkills(response.skills)
      })
      .catch(() => {
        if (!disposed) {
          setSkills(null)
          setSkillsOpen(false)
        }
      })
    return () => {
      disposed = true
    }
  }, [])

  const insertSkillTrigger = (skillName: string) => {
    if (onSkillSelect) {
      onSkillSelect(skillName)
      setSkillsOpen(false)
      return
    }
    navigate('/settings/tools/skills')
  }

  useEffect(() => {
    void fetchArtifacts()
  }, [fetchArtifacts])

  useEffect(() => {
    let disposed = false
    const updateMemory = () => {
      api<GatewayStatusData>('/gateway/status')
        .then((status) => {
          if (!disposed) setMemoryBytes(typeof status.memory_rss_bytes === 'number' ? status.memory_rss_bytes : null)
        })
        .catch(() => {
          if (!disposed) setMemoryBytes(null)
        })
    }
    updateMemory()
    const timer = window.setInterval(updateMemory, 10_000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [])

  const widgets = useMemo(() => {
    const next: Array<HudWidget | null> = [
      session
        ? {
            id: 'token',
            label: 'Token',
            value: formatTokenCount(session.token_stats.total_tokens),
            icon: Gauge,
            onClick: () => navigate(buildTokenStatsNavUrl({ sessionKey: session.key })),
          }
        : null,
      {
        id: 'skills',
        label: 'Skills',
        value: String(skills?.length ?? 0),
        icon: Puzzle,
        onClick: () => setSkillsOpen((open) => !open),
      },
      {
        id: 'artifacts',
        label: 'Artifacts',
        value: String(artifactCount),
        icon: Box,
        onClick: () => openTaskFloater({ panel: 'artifacts' }),
      },
      memoryBytes !== null
        ? {
            id: 'memory',
            label: 'Memory',
            value: formatBytes(memoryBytes),
            icon: MemoryStick,
            onClick: () => navigate('/settings/system/gateway'),
          }
        : null,
    ]
    return next.filter((widget): widget is HudWidget => widget !== null)
  }, [artifactCount, memoryBytes, navigate, openTaskFloater, session, skills?.length])

  return (
    <div className="border-t border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="flex snap-x gap-2 overflow-x-auto scrollbar-none">
        {widgets.map((widget) => {
          const Icon = widget.icon
          return (
            <button
              key={widget.id}
              type="button"
              onClick={widget.onClick}
              className={`${chipClass()} snap-start`}
            >
              <Icon className="h-3.5 w-3.5" />
              {widget.label} {widget.value}
            </button>
          )
        })}
      </div>
      {skillsOpen && skills && !isMobile && (
        <div className="mt-2 max-h-48 overflow-y-auto rounded-md border border-[var(--border)] bg-[var(--bg-primary)] p-2 shadow-lg">
          <div className="grid min-w-80 grid-cols-1 gap-2 sm:grid-cols-2">
            {skills.map((skill) => (
              <button
                key={`${skill.source || 'skill'}:${skill.name}`}
                type="button"
                onClick={() => insertSkillTrigger(skill.name)}
                className="rounded-md border border-[var(--border)] px-2 py-1.5 text-left text-xs hover:border-[var(--accent)]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium text-[var(--text-primary)]">{skill.name}</span>
                  <span className="shrink-0 text-[10px] uppercase text-[var(--text-tertiary)]">
                    {skill.enabled === false ? 'off' : 'on'}
                  </span>
                </div>
                <div className="truncate text-[var(--text-tertiary)]">{skill.description || skill.source || 'skill'}</div>
              </button>
            ))}
          </div>
        </div>
      )}
      {skillsOpen && skills && isMobile && (
        <div className="fixed inset-x-0 bottom-0 z-50 max-h-[70vh] overflow-y-auto border-t border-[var(--border)] bg-[var(--bg-primary)] p-3 shadow-2xl">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-[var(--text-primary)]">Skills</div>
            <button type="button" onClick={() => setSkillsOpen(false)} className="rounded-md border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-secondary)]">Close</button>
          </div>
          <div className="grid gap-2">
            {skills.map((skill) => (
              <button
                key={`${skill.source || 'skill'}:${skill.name}`}
                type="button"
                onClick={() => insertSkillTrigger(skill.name)}
                className="rounded-md border border-[var(--border)] px-3 py-2 text-left text-xs hover:border-[var(--accent)]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium text-[var(--text-primary)]">{skill.name}</span>
                  <span className="shrink-0 text-[10px] uppercase text-[var(--text-tertiary)]">
                    {skill.enabled === false ? 'off' : 'on'}
                  </span>
                </div>
                <div className="truncate text-[var(--text-tertiary)]">{skill.description || skill.source || 'skill'}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
