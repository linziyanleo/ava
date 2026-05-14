import { AlertTriangle, RefreshCw } from 'lucide-react'
import { StatusBadge, type StatusKind } from '../ui/StatusBadge'
import { useBootstrapState } from '../../hooks/useBootstrapState'

const VISIBLE_STAGES = new Set(['error', 'failed', 'retrying', 'nanobot'])

function stageStatusKind(stage: string): StatusKind {
  if (stage === 'error' || stage === 'failed') return 'failed'
  return 'retrying'
}

export default function BootstrapBanner() {
  const { state, retry } = useBootstrapState()
  if (!state || !VISIBLE_STAGES.has(state.stage)) return null

  const message = state.error || state.message || 'Ava core is not ready'
  const kind = stageStatusKind(state.stage)

  return (
    <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--ava-warning-border)] bg-[var(--ava-warning-soft)] px-4 py-2 text-sm text-[var(--text-primary)]">
      <div className="flex min-w-0 items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--ava-warning)]" />
        <StatusBadge kind={kind} label={state.stage} />
        <span className="truncate">{message}</span>
      </div>
      <button
        type="button"
        onClick={() => { void retry() }}
        className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-[var(--ava-warning-border)] px-2.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--ava-warning-soft)]"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        Retry Core
      </button>
    </div>
  )
}
