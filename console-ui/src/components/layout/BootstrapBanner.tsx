import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useBootstrapState } from '../../hooks/useBootstrapState'

const VISIBLE_STAGES = new Set(['error', 'failed', 'retrying', 'nanobot'])

export default function BootstrapBanner() {
  const { state, retry } = useBootstrapState()
  if (!state || !VISIBLE_STAGES.has(state.stage)) return null

  const message = state.error || state.message || 'Ava core is not ready'

  return (
    <div className="flex shrink-0 items-center justify-between gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-100">
      <div className="flex min-w-0 items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-300" />
        <span className="truncate">{message}</span>
      </div>
      <button
        type="button"
        onClick={() => { void retry() }}
        className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-amber-400/40 px-2.5 text-xs font-medium text-amber-100 hover:border-amber-300 hover:bg-amber-400/10"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        Retry Core
      </button>
    </div>
  )
}
