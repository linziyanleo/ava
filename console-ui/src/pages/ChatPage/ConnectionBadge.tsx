import { cn } from '../../lib/utils'
import type { ActiveChatTransport, ChatStreamStatus } from './types'

const STATUS_META: Record<ChatStreamStatus, { color: string; label: string }> = {
  idle: {
    color: 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
    label: '空闲',
  },
  connecting: {
    color: 'bg-amber-500/10 text-amber-400',
    label: '连接中',
  },
  open: {
    color: 'bg-emerald-500/10 text-emerald-400',
    label: '已连接',
  },
  reconnecting: {
    color: 'bg-amber-500/10 text-amber-400',
    label: '重连中',
  },
  closed: {
    color: 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
    label: '已关闭',
  },
  error: {
    color: 'bg-rose-500/10 text-rose-400',
    label: '异常',
  },
}

const TRANSPORT_LABELS: Record<Exclude<ActiveChatTransport, 'none'>, string> = {
  console: 'Console WS',
  observe: 'Observe WS',
}

interface ConnectionBadgeProps {
  transport: ActiveChatTransport
  status: ChatStreamStatus
}

export function ConnectionBadge({ transport, status }: ConnectionBadgeProps) {
  if (transport === 'none') return null

  const meta = STATUS_META[status]
  const isPulsing = status === 'connecting' || status === 'reconnecting' || status === 'error'

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] px-2 py-1 text-[10px] font-medium',
        meta.color,
      )}
      aria-live="polite"
    >
      <span className="relative flex h-1.5 w-1.5" aria-hidden>
        {isPulsing && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
        )}
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
      </span>
      <span>{TRANSPORT_LABELS[transport]}</span>
      <span className="opacity-60">·</span>
      <span>{meta.label}</span>
    </span>
  )
}
