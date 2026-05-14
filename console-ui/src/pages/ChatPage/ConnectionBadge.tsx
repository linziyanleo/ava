import { cn } from '../../lib/utils'
import { StatusBadge, type StatusKind } from '../../components/ui/StatusBadge'
import type { ActiveChatTransport, ChatStreamStatus } from './types'

const STATUS_META: Record<ChatStreamStatus, { kind: StatusKind; label: string }> = {
  idle: {
    kind: 'idle',
    label: '空闲',
  },
  connecting: {
    kind: 'retrying',
    label: '连接中',
  },
  open: {
    kind: 'available',
    label: '已连接',
  },
  reconnecting: {
    kind: 'retrying',
    label: '重连中',
  },
  closed: {
    kind: 'disconnected',
    label: '已关闭',
  },
  error: {
    kind: 'failed',
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

interface AvaDesktopApi {
  retryCore?: () => Promise<{ ok: boolean; error?: string }>
}

function desktopApi(): AvaDesktopApi | null {
  return (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop || null
}

export function ConnectionBadge({ transport, status }: ConnectionBadgeProps) {
  if (transport === 'none') return null

  const meta = STATUS_META[status]
  const canRetryCore = Boolean(desktopApi()?.retryCore) && (status === 'closed' || status === 'error')

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-2 py-1 text-[10px] font-medium text-[var(--text-secondary)]',
      )}
      aria-live="polite"
    >
      <span>{TRANSPORT_LABELS[transport]}</span>
      <StatusBadge kind={meta.kind} label={meta.label} className="-my-0.5" />
      {canRetryCore && (
        <>
          <span className="opacity-60">·</span>
          <button
            type="button"
            onClick={() => { void desktopApi()?.retryCore?.() }}
            className="rounded px-1 text-[10px] font-semibold text-current underline-offset-2 hover:underline"
          >
            Retry Core
          </button>
        </>
      )}
    </span>
  )
}
