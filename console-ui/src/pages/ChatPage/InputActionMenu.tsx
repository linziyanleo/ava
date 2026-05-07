import { useEffect, useMemo, useRef } from 'react'
import { FileUp, Upload } from 'lucide-react'
import type { ChatCommand } from './commands'
import { CHAT_COMMANDS, findCommandsByPrefix } from './commands'

interface InputActionMenuProps {
  open: boolean
  onClose: () => void
  onPickFiles: (files: File[]) => void
  onRunCommand: (command: ChatCommand) => void
  isMobile?: boolean
  anchorRef?: { current: HTMLElement | null }
  filterPrefix?: string
  variant: 'menu' | 'slash-suggest'
  sendDisabled?: boolean
  activeIndex?: number
}

export function InputActionMenu({
  open,
  onClose,
  onPickFiles,
  onRunCommand,
  isMobile,
  anchorRef,
  filterPrefix,
  variant,
  sendDisabled = false,
  activeIndex = 0,
}: InputActionMenuProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const commands = useMemo(
    () => (variant === 'slash-suggest' && filterPrefix ? findCommandsByPrefix(filterPrefix) : CHAT_COMMANDS),
    [filterPrefix, variant],
  )

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (panelRef.current?.contains(target) || anchorRef?.current?.contains(target)) return
      onClose()
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [anchorRef, onClose, open])

  if (!open) return null

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files || [])
    if (files.length > 0) {
      onPickFiles(files)
      onClose()
    }
    event.currentTarget.value = ''
  }

  const body = (
    <div className="space-y-3">
      {variant === 'menu' && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex w-full items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] px-3 py-2 text-left text-sm text-[var(--text-primary)] transition-colors hover:border-[var(--accent)] hover:bg-[var(--bg-primary)]"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--accent)]/10 text-[var(--accent)]">
              <FileUp className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block font-medium">Upload file</span>
              <span className="block truncate text-xs text-[var(--text-secondary)]">Attach images, PDFs, docs, or text</span>
            </span>
            <Upload className="ml-auto h-4 w-4 shrink-0 text-[var(--text-secondary)]" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      )}

      <div className="space-y-1">
        {variant === 'menu' && (
          <div className="px-1 text-[10px] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
            Current turn
          </div>
        )}
        {commands.map((command, index) => {
          const Icon = command.icon
          const disabled = sendDisabled && !command.runWhenBusy
          const active = variant === 'slash-suggest' && index === activeIndex
          return (
            <button
              key={command.id}
              type="button"
              disabled={disabled}
              onClick={() => {
                if (!disabled) onRunCommand(command)
              }}
              className={`flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                disabled
                  ? 'cursor-not-allowed opacity-45'
                  : active
                    ? 'bg-[var(--accent)]/12 text-[var(--text-primary)]'
                    : 'text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
              }`}
              title={disabled ? '当前回复进行中，命令暂不可发送' : command.description}
            >
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                {Icon ? <Icon className="h-3.5 w-3.5" /> : command.id.slice(0, 2)}
              </span>
              <span className="min-w-0">
                <span className="block">
                  <span className="font-mono font-medium">{command.id}</span>
                  <span className="ml-2 text-xs text-[var(--text-secondary)]">{command.label}</span>
                </span>
                <span className="block truncate text-xs text-[var(--text-secondary)]">{command.description}</span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )

  return (
    <div
      ref={panelRef}
      className={`absolute bottom-full left-0 z-50 mb-2 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-2 shadow-xl ${
        variant === 'slash-suggest'
          ? 'w-full min-w-64'
          : isMobile
            ? 'w-[calc(100vw-2rem)] max-w-96'
            : 'w-72'
      }`}
    >
      {body}
    </div>
  )
}
