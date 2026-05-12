import { useCallback, useEffect, useState } from 'react'
import { X, RefreshCw, Send, Layers, Clock, ChevronDown, ChevronRight, AlertTriangle, Info } from 'lucide-react'
import { api } from '../../api/client'
import type { ContextPreview, ContextPreviewWindow } from './types'
import { formatTokenCount } from './utils'

interface ContextLensDrawerProps {
  open: boolean
  sessionKey: string | null
  sessionLabel?: string
  disabled?: boolean
  isMobile?: boolean
  onClose: () => void
}

type LensTab = 'sending' | 'window' | 'history'

interface CompressionRecord {
  id: string
  created_at: string
  summary_text: string
  messages_compressed: number
  tokens_before: number
  tokens_after: number
}

const TAB_META: Record<LensTab, { label: string; icon: typeof Send }> = {
  sending: { label: 'Now Sending', icon: Send },
  window: { label: 'Window', icon: Layers },
  history: { label: 'History', icon: Clock },
}

function buildPreviewUrl(sessionKey: string, options?: { full?: boolean; reveal?: boolean }) {
  const params = new URLSearchParams()
  if (options?.full) params.set('full', 'true')
  if (options?.reveal) params.set('reveal', 'true')
  return `/chat/sessions/${encodeURIComponent(sessionKey)}/context-preview${params.size ? `?${params.toString()}` : ''}`
}

export function ContextLensDrawer({ open, sessionKey, sessionLabel, isMobile, onClose }: ContextLensDrawerProps) {
  const [activeTab, setActiveTab] = useState<LensTab>('sending')
  const [preview, setPreview] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [compressions, setCompressions] = useState<CompressionRecord[]>([])
  const [compressionsLoading, setCompressionsLoading] = useState(false)

  const fetchPreview = useCallback(async () => {
    if (!sessionKey) return
    setLoading(true)
    setError('')
    try {
      const data = await api<ContextPreview>(buildPreviewUrl(sessionKey))
      setPreview(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load context preview')
    } finally {
      setLoading(false)
    }
  }, [sessionKey])

  const fetchCompressions = useCallback(async () => {
    if (!sessionKey) return
    const sessionId = sessionKey.replace(/^console:/, '')
    setCompressionsLoading(true)
    try {
      const data = await api<CompressionRecord[]>(`/chat/sessions/${encodeURIComponent(sessionId)}/compressions`)
      setCompressions(data)
    } catch {
      setCompressions([])
    } finally {
      setCompressionsLoading(false)
    }
  }, [sessionKey])

  useEffect(() => {
    if (open && sessionKey) {
      fetchPreview()
    }
  }, [open, sessionKey, fetchPreview])

  useEffect(() => {
    if (open && activeTab === 'history' && sessionKey) {
      fetchCompressions()
    }
  }, [open, activeTab, sessionKey, fetchCompressions])

  useEffect(() => {
    if (!open) return
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [onClose, open])

  if (!open) return null

  const drawerClass = isMobile
    ? 'fixed inset-0 z-50 flex flex-col bg-[var(--bg-primary)]'
    : 'fixed right-0 top-0 bottom-0 z-50 flex w-[520px] flex-col border-l border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl'

  return (
    <>
      {!isMobile && <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />}
      <div className={drawerClass}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-[var(--accent)]" />
            <span className="text-sm font-medium text-[var(--text-primary)]">
              Context Lens
            </span>
            {sessionLabel && (
              <span className="text-xs text-[var(--text-tertiary)]">· {sessionLabel}</span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={fetchPreview}
              disabled={loading}
              className="rounded-md p-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors disabled:opacity-40"
              title="Refresh"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--border)]">
          {(Object.keys(TAB_META) as LensTab[]).map((tab) => {
            const { label, icon: Icon } = TAB_META[tab]
            const isActive = activeTab === tab
            return (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={[
                  'flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-colors',
                  isActive
                    ? 'border-b-2 border-[var(--accent)] text-[var(--accent)]'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
                ].join(' ')}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            )
          })}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto">
          {error && (
            <div className="m-4 flex items-center gap-2 rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/5 p-3 text-xs text-[var(--danger)]">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              {error}
            </div>
          )}
          {activeTab === 'sending' && <NowSendingTab preview={preview} loading={loading} />}
          {activeTab === 'window' && <WindowTab preview={preview} loading={loading} />}
          {activeTab === 'history' && <HistoryTab compressions={compressions} loading={compressionsLoading} />}
        </div>

        {/* Footer: scope badge */}
        {preview && (
          <div className="flex items-center gap-2 border-t border-[var(--border)] px-4 py-2">
            <Info className="h-3 w-3 text-[var(--text-tertiary)]" />
            <span className="text-[10px] text-[var(--text-tertiary)]">
              Scope: {(preview.totals.estimate_scope || 'unknown').replaceAll('_', ' ')}
            </span>
            <span className="text-[10px] text-[var(--text-tertiary)]">·</span>
            <span className="text-[10px] text-[var(--text-tertiary)]">
              {preview.snapshot_ts ? new Date(preview.snapshot_ts).toLocaleTimeString() : ''}
            </span>
          </div>
        )}
      </div>
    </>
  )
}

/* ═══════════ Tab 1: Now Sending ═══════════ */

function NowSendingTab({ preview, loading }: { preview: ContextPreview | null; loading: boolean }) {
  if (loading && !preview) return <TabLoading />
  if (!preview) return <TabEmpty message="No context data available" />

  const { totals, system_sections, runtime_context, messages, tools } = preview
  const sections = [
    { key: 'system', label: 'System', tokens: totals.system_tokens, color: 'text-sky-400', items: system_sections },
    { key: 'runtime', label: 'Runtime', tokens: totals.runtime_tokens, color: 'text-emerald-400' },
    { key: 'history', label: 'History', tokens: totals.history_tokens, color: 'text-amber-400', count: messages.length },
    { key: 'tools', label: 'Tools', tokens: totals.tool_tokens, color: 'text-fuchsia-400', count: tools.count },
  ]

  return (
    <div className="space-y-1 p-4">
      {/* Totals bar */}
      <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="text-[var(--text-secondary)]">Total tokens</span>
          <span className="font-mono text-[var(--text-primary)]">
            {formatTokenCount(totals.request_total_tokens)} / {formatTokenCount(totals.ctx_budget)}
          </span>
        </div>
        <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
          <BarSegment pct={(totals.system_tokens / totals.ctx_budget) * 100} color="bg-sky-500" />
          <BarSegment pct={(totals.runtime_tokens / totals.ctx_budget) * 100} color="bg-emerald-500" />
          <BarSegment pct={(totals.history_tokens / totals.ctx_budget) * 100} color="bg-amber-500" />
          <BarSegment pct={(totals.tool_tokens / totals.ctx_budget) * 100} color="bg-fuchsia-500" />
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-[10px]">
          <Legend color="bg-sky-500" label="System" />
          <Legend color="bg-emerald-500" label="Runtime" />
          <Legend color="bg-amber-500" label="History" />
          <Legend color="bg-fuchsia-500" label="Tools" />
        </div>
      </div>

      {/* Section breakdown */}
      {sections.map((section) => (
        <CollapsibleSection key={section.key} label={section.label} tokens={section.tokens} color={section.color}>
          {section.key === 'system' && system_sections.map((s) => (
            <div key={s.name} className="mt-1.5 rounded border border-[var(--border)] bg-[var(--bg-primary)] p-2">
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-[var(--text-secondary)]">{s.name.replaceAll('_', ' ')}</span>
                <span className="font-mono text-[var(--text-tertiary)]">{formatTokenCount(s.tokens)}</span>
              </div>
              {s.content && (
                <div className="mt-1 max-h-32 overflow-y-auto text-[10px] text-[var(--text-tertiary)] whitespace-pre-wrap break-all">
                  {s.content.slice(0, 500)}{s.content.length > 500 ? '…' : ''}
                </div>
              )}
            </div>
          ))}
          {section.key === 'runtime' && runtime_context.content && (
            <div className="mt-1.5 max-h-40 overflow-y-auto rounded border border-[var(--border)] bg-[var(--bg-primary)] p-2 text-[10px] text-[var(--text-tertiary)] whitespace-pre-wrap break-all">
              {runtime_context.content.slice(0, 800)}{runtime_context.content.length > 800 ? '…' : ''}
            </div>
          )}
          {section.key === 'history' && (
            <div className="mt-1.5 text-[10px] text-[var(--text-tertiary)]">
              {messages.length} messages in replay window
              {messages.length > 0 && (
                <div className="mt-1 space-y-0.5">
                  {messages.slice(-6).map((m, i) => (
                    <div key={i} className="flex gap-2 truncate">
                      <span className="shrink-0 w-14 text-right font-mono opacity-60">{m.role}</span>
                      <span className="truncate">{typeof m.content === 'string' ? m.content.slice(0, 80) : '[blocks]'}</span>
                    </div>
                  ))}
                  {messages.length > 6 && <div className="opacity-50">… {messages.length - 6} more</div>}
                </div>
              )}
            </div>
          )}
          {section.key === 'tools' && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {tools.names.slice(0, 20).map((name) => (
                <span key={name} className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">
                  {name}
                </span>
              ))}
              {tools.names.length > 20 && (
                <span className="text-[10px] text-[var(--text-tertiary)]">+{tools.names.length - 20} more</span>
              )}
            </div>
          )}
        </CollapsibleSection>
      ))}
    </div>
  )
}

/* ═══════════ Tab 2: Window ═══════════ */

function WindowTab({ preview, loading }: { preview: ContextPreview | null; loading: boolean }) {
  if (loading && !preview) return <TabLoading />
  if (!preview) return <TabEmpty message="No context data available" />

  const window = preview.window
  const totals = preview.totals

  return (
    <div className="space-y-4 p-4">
      {/* Utilization gauge */}
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
        <div className="text-center">
          <div className="text-3xl font-semibold text-[var(--text-primary)]">
            {Math.round(totals.utilization_pct)}%
          </div>
          <div className="mt-1 text-xs text-[var(--text-secondary)]">Context utilization</div>
        </div>
        <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
          <div
            className={`rounded-full transition-all ${utilGaugeColor(totals.utilization_pct)}`}
            style={{ width: `${Math.min(totals.utilization_pct, 100)}%` }}
          />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
          <StatCell label="Used" value={formatTokenCount(totals.request_total_tokens)} />
          <StatCell label="Budget" value={formatTokenCount(totals.ctx_budget)} />
          <StatCell label="Context window" value={formatTokenCount(totals.context_window)} />
          <StatCell label="Max completion" value={formatTokenCount(totals.max_completion_tokens)} />
        </div>
      </div>

      {/* Window details */}
      {window && <WindowDetails window={window} />}

      {/* Scope notice */}
      <div className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-3 text-xs text-[var(--text-secondary)]">
        <div className="flex items-start gap-2">
          <Info className="h-3.5 w-3.5 shrink-0 text-[var(--warning)] mt-0.5" />
          <div>
            <span className="font-medium text-[var(--text-primary)]">Estimate scope</span>
            <p className="mt-0.5">
              {(totals.estimate_scope || 'unknown').replaceAll('_', ' ')}
              — this is not equivalent to the actual provider request.
              The runner may further trim history before sending.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function WindowDetails({ window }: { window: ContextPreviewWindow }) {
  return (
    <div className="rounded-lg border border-[var(--border)] p-4">
      <h4 className="text-xs font-medium text-[var(--text-primary)]">Replay Window</h4>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <StatCell label="Kept messages" value={String(window.kept_count)} />
        <StatCell label="Dropped (est.)" value={String(window.dropped_count)} />
        <StatCell label="Kept tokens" value={formatTokenCount(window.kept_tokens)} />
        <StatCell label="Strategy" value={window.strategy} />
      </div>
      {window.consolidated_count != null && window.consolidated_count > 0 && (
        <div className="mt-2 text-[10px] text-[var(--text-tertiary)]">
          {window.consolidated_count} messages consolidated (not in replay window)
        </div>
      )}
      {window.dropped_count > 0 && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-[var(--warning)]">
          <AlertTriangle className="h-3 w-3" />
          Some messages are outside the replay window and won't be sent to the model
        </div>
      )}
    </div>
  )
}

/* ═══════════ Tab 3: History ═══════════ */

function HistoryTab({ compressions, loading }: { compressions: CompressionRecord[]; loading: boolean }) {
  if (loading) return <TabLoading />
  if (compressions.length === 0) {
    return (
      <TabEmpty message="No compression records. The sliding window manages context automatically without explicit compression." />
    )
  }

  return (
    <div className="space-y-3 p-4">
      <p className="text-xs text-[var(--text-secondary)]">
        Legacy compression records (read-only). These were created by the old compress button
        and are not used by the current sliding window.
      </p>
      {compressions.map((record) => (
        <CompressionCard key={record.id} record={record} />
      ))}
    </div>
  )
}

function CompressionCard({ record }: { record: CompressionRecord }) {
  const [expanded, setExpanded] = useState(false)
  const date = new Date(record.created_at)
  const savings = record.tokens_before > 0
    ? Math.round(((record.tokens_before - record.tokens_after) / record.tokens_before) * 100)
    : 0

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-[var(--text-primary)]">
          {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
        <div className="text-[10px] text-[var(--text-tertiary)]">
          {record.messages_compressed} msgs · −{savings}%
        </div>
      </div>
      <div className="mt-1.5 flex gap-3 text-[10px] text-[var(--text-tertiary)]">
        <span>{formatTokenCount(record.tokens_before)} → {formatTokenCount(record.tokens_after)}</span>
      </div>
      {record.summary_text && (
        <>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="mt-2 flex items-center gap-1 text-[10px] text-[var(--accent)] hover:underline"
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {expanded ? 'Hide summary' : 'Show summary'}
          </button>
          {expanded && (
            <div className="mt-2 max-h-40 overflow-y-auto rounded border border-[var(--border)] bg-[var(--bg-primary)] p-2 text-[10px] text-[var(--text-tertiary)] whitespace-pre-wrap">
              {record.summary_text}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/* ═══════════ Shared components ═══════════ */

function TabLoading() {
  return (
    <div className="flex items-center justify-center py-12">
      <RefreshCw className="h-5 w-5 animate-spin text-[var(--accent)]" />
    </div>
  )
}

function TabEmpty({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Layers className="h-8 w-8 text-[var(--text-tertiary)] opacity-50" />
      <p className="mt-3 max-w-[280px] text-xs text-[var(--text-tertiary)]">{message}</p>
    </div>
  )
}

function CollapsibleSection({
  label,
  tokens,
  color,
  children,
}: {
  label: string
  tokens: number
  color: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left"
      >
        {open ? <ChevronDown className="h-3 w-3 text-[var(--text-tertiary)]" /> : <ChevronRight className="h-3 w-3 text-[var(--text-tertiary)]" />}
        <span className={`text-xs font-medium ${color}`}>{label}</span>
        <span className="ml-auto font-mono text-[10px] text-[var(--text-tertiary)]">{formatTokenCount(tokens)}</span>
      </button>
      {open && <div className="border-t border-[var(--border)] px-3 py-2">{children}</div>}
    </div>
  )
}

function BarSegment({ pct, color }: { pct: number; color: string }) {
  if (pct <= 0) return null
  return <div className={`${color} transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block h-2 w-2 rounded-sm ${color}`} />
      <span className="text-[var(--text-tertiary)]">{label}</span>
    </span>
  )
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] text-[var(--text-tertiary)]">{label}</div>
      <div className="font-mono text-[var(--text-primary)]">{value}</div>
    </div>
  )
}

function utilGaugeColor(pct: number): string {
  if (pct > 85) return 'bg-[var(--danger)]'
  if (pct >= 60) return 'bg-[var(--warning)]'
  return 'bg-[var(--success)]'
}
