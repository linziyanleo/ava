import { useEffect } from 'react'
import { RefreshCw, Search, Zap, Radio, Lock, X } from 'lucide-react'
import type { ActiveChatTransport, ChatStreamStatus } from './types'

interface HeaderOverflowSheetProps {
  open: boolean
  onClose: () => void
  onRefresh: () => void
  onSearch: () => void
  onTokenStats: () => void
  transportStatus: ChatStreamStatus
  activeTransport: ActiveChatTransport
  isReadOnly: boolean
  tokenSummary: string
}

const TRANSPORT_LABELS: Record<ActiveChatTransport, string> = {
  console: 'Console WebSocket',
  observe: 'Observe WebSocket',
  none: 'Disconnected',
}
const STATUS_LABELS: Record<ChatStreamStatus, string> = {
  idle: 'Idle',
  connecting: 'Connecting…',
  open: 'Connected',
  reconnecting: 'Reconnecting…',
  closed: 'Closed',
  error: 'Error',
}

export function HeaderOverflowSheet({
  open,
  onClose,
  onRefresh,
  onSearch,
  onTokenStats,
  transportStatus,
  activeTransport,
  isReadOnly,
  tokenSummary,
}: HeaderOverflowSheetProps) {
  useEffect(() => {
    if (!open) return
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [onClose, open])

  if (!open) return null

  const actionItem = (icon: React.ReactNode, label: string, onClick: () => void) => (
    <button
      type="button"
      onClick={() => { onClick(); onClose() }}
      className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm text-[var(--text-primary)] transition-colors active:bg-[var(--bg-tertiary)]"
    >
      <span className="text-[var(--text-secondary)]">{icon}</span>
      {label}
    </button>
  )

  const infoItem = (icon: React.ReactNode, label: string, value: string) => (
    <div className="flex items-center gap-3 px-4 py-3 text-sm">
      <span className="text-[var(--text-secondary)]">{icon}</span>
      <span className="flex-1 text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  )

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-x-0 bottom-0 z-50 animate-slide-in-bottom rounded-t-2xl border-t border-[var(--border)] bg-[var(--bg-primary)] pb-[env(safe-area-inset-bottom)]">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <span className="text-sm font-medium text-[var(--text-primary)]">More</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {actionItem(<RefreshCw className="h-4 w-4" />, 'Refresh', onRefresh)}
          {actionItem(<Search className="h-4 w-4" />, 'Search', onSearch)}
          {actionItem(<Zap className="h-4 w-4" />, `Token stats · ${tokenSummary}`, onTokenStats)}
          {infoItem(
            <Radio className="h-4 w-4" />,
            'Connection',
            `${TRANSPORT_LABELS[activeTransport]} · ${STATUS_LABELS[transportStatus]}`,
          )}
          {isReadOnly && infoItem(
            <Lock className="h-4 w-4" />,
            'Mode',
            'Read-only',
          )}
        </div>
      </div>
    </>
  )
}
