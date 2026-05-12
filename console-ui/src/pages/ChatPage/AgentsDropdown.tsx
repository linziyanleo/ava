import { useCallback, useEffect, useRef, useState } from 'react'
import { Bot, Check, ChevronDown } from 'lucide-react'

const CHAT_AGENTS = [
  { id: 'nanobot', label: 'Nanobot' },
  { id: 'codex', label: 'Codex' },
  { id: 'claude_code', label: 'Claude Code' },
]

interface AgentsDropdownProps {
  participants: string[]
  defaultResponderId: string
  isReadOnly: boolean
  disabled?: boolean
  onParticipantsChange?: (participants: string[]) => Promise<void> | void
}

function buildTriggerLabel(selected: string[]): string {
  if (selected.length === 0) return '未指定（默认 Nanobot）'
  const labels = selected.map(
    (id) => CHAT_AGENTS.find((a) => a.id === id)?.label || id,
  )
  if (labels.length === 1) return labels[0]
  if (labels.length === 2) return `${labels[0]} · ${labels[1]} (2)`
  return `${labels[0]} · ${labels[1]} +${labels.length - 2} (${labels.length})`
}

export function AgentsDropdown({
  participants,
  defaultResponderId,
  isReadOnly,
  disabled,
  onParticipantsChange,
}: AgentsDropdownProps) {
  const [open, setOpen] = useState(false)
  const [focusIndex, setFocusIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const selected =
    participants.length > 0
      ? participants
      : [defaultResponderId || 'nanobot']

  const handleToggle = useCallback(
    (agentId: string) => {
      if (isReadOnly || disabled || !onParticipantsChange) return
      const isSelected = selected.includes(agentId)
      if (isSelected && selected.length <= 1) return
      const next = isSelected
        ? selected.filter((id) => id !== agentId)
        : [...selected, agentId]
      void onParticipantsChange(next)
    },
    [disabled, isReadOnly, onParticipantsChange, selected],
  )

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!open) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          setOpen(true)
        }
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setOpen(false)
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setFocusIndex((i) => Math.min(i + 1, CHAT_AGENTS.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setFocusIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === ' ') {
        e.preventDefault()
        handleToggle(CHAT_AGENTS[focusIndex].id)
      }
    },
    [focusIndex, handleToggle, open],
  )

  useEffect(() => {
    if (open && listRef.current) {
      const items = listRef.current.querySelectorAll('[role="option"]')
      ;(items[focusIndex] as HTMLElement | undefined)?.focus()
    }
  }, [focusIndex, open])

  const triggerLabel = buildTriggerLabel(selected)
  const triggerMuted = participants.length === 0

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] transition-colors hover:bg-[var(--bg-tertiary)]"
      >
        <Bot className="h-3 w-3 shrink-0 text-[var(--accent)]" />
        <span className={triggerMuted ? 'text-[var(--text-tertiary)]' : 'text-[var(--text-primary)]'}>
          {triggerLabel}
        </span>
        <ChevronDown className={`h-2.5 w-2.5 text-[var(--text-tertiary)] transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          ref={listRef}
          role="listbox"
          aria-multiselectable
          onKeyDown={handleKeyDown}
          className="absolute left-0 top-full z-30 mt-1 w-56 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-1 shadow-xl"
        >
          {CHAT_AGENTS.map((agent, index) => {
            const isChecked = selected.includes(agent.id)
            const isDefault = agent.id === defaultResponderId
            const isLastSelected = isChecked && selected.length <= 1
            const isDisabled = isReadOnly || disabled || (isLastSelected && isChecked)

            return (
              <div
                key={agent.id}
                role="option"
                tabIndex={-1}
                aria-selected={isChecked}
                aria-disabled={isDisabled}
                data-focus={index === focusIndex}
                onClick={() => { if (!isDisabled) handleToggle(agent.id) }}
                className={[
                  'flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-xs transition-colors',
                  'focus-visible:outline-none',
                  index === focusIndex ? 'bg-[var(--bg-tertiary)]' : 'hover:bg-[var(--bg-tertiary)]/60',
                  isDisabled ? 'cursor-not-allowed opacity-50' : '',
                ].join(' ')}
              >
                <span
                  className={[
                    'inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors',
                    isChecked
                      ? 'border-[var(--accent)] bg-[var(--accent)] text-white'
                      : 'border-[var(--border)] bg-[var(--bg-secondary)]',
                  ].join(' ')}
                >
                  {isChecked && <Check className="h-2.5 w-2.5" />}
                </span>
                <span className="flex-1 text-[var(--text-primary)]">{agent.label}</span>
                {isDefault && (
                  <span className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                    Default
                  </span>
                )}
                {isLastSelected && isChecked && (
                  <span className="text-[10px] text-[var(--text-tertiary)]">
                    至少保留 1 个
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
