import { useEffect, useMemo, useState } from 'react'
import { Check, Copy, X } from 'lucide-react'
import { getTrace, type TraceDetail, type TraceSpanRecord } from '../api/client'
import { cn } from '../lib/utils'

function formatDuration(ms: number | null): string {
  if (ms == null) return 'running'
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`
  if (ms < 1000) return `${ms.toFixed(1)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function statusClass(status: string): string {
  if (status === 'error') return 'bg-rose-500 text-white'
  if (status === 'interrupted') return 'bg-zinc-500 text-white'
  if (status === 'running') return 'bg-amber-500 text-zinc-950'
  return 'bg-emerald-500 text-zinc-950'
}

function spanBarClass(status: string): string {
  if (status === 'error') return 'bg-rose-500/80'
  if (status === 'interrupted') return 'bg-zinc-500/80'
  if (status === 'running') return 'bg-amber-500/80'
  return 'bg-emerald-500/80'
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={async e => {
        e.stopPropagation()
        await navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1200)
      }}
      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      title="复制"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-[var(--success)]" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}

function SpanRow({
  span,
  rangeStart,
  rangeMs,
  selected,
  onSelect,
}: {
  span: TraceSpanRecord
  rangeStart: number
  rangeMs: number
  selected: boolean
  onSelect: () => void
}) {
  const startOffsetMs = Math.max(0, (span.start_ns - rangeStart) / 1_000_000)
  const left = Math.min(96, Math.max(0, (startOffsetMs / rangeMs) * 100))
  const width = Math.max(1.5, Math.min(100 - left, ((span.duration_ms ?? 0) / rangeMs) * 100))

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'grid w-full grid-cols-[minmax(180px,280px)_1fr_72px] items-center gap-3 border-b border-[var(--border)]/60 px-3 py-2 text-left text-xs hover:bg-[var(--bg-tertiary)]/60',
        selected && 'bg-[var(--bg-tertiary)]',
      )}
    >
      <div className="min-w-0" style={{ paddingLeft: `${Math.min(span.depth, 6) * 14}px` }}>
        <div className="flex min-w-0 items-center gap-2">
          <span className={cn('h-2 w-2 rounded-full', spanBarClass(span.status))} />
          <span className="truncate font-medium text-[var(--text-primary)]" title={span.name}>
            {span.name}
          </span>
        </div>
        <div className="mt-0.5 truncate font-mono text-[10px] text-[var(--text-secondary)]">
          {span.operation_name} · {span.span_id}
        </div>
      </div>
      <div className="relative h-6 rounded bg-[var(--bg-primary)]">
        <div
          className={cn('absolute top-1 h-4 rounded', spanBarClass(span.status))}
          style={{ left: `${left}%`, width: `${width}%` }}
        />
      </div>
      <div className="text-right font-mono text-[11px] text-[var(--text-secondary)]">
        {formatDuration(span.duration_ms)}
      </div>
    </button>
  )
}

export default function TraceTimelineDrawer({ traceId, onClose }: { traceId: string; onClose: () => void }) {
  const [trace, setTrace] = useState<TraceDetail | null>(null)
  const [selectedSpanId, setSelectedSpanId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    getTrace(traceId)
      .then(result => {
        if (cancelled) return
        setTrace(result)
        setSelectedSpanId(result.spans[0]?.span_id ?? '')
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || 'Trace load failed')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [traceId])

  const range = useMemo(() => {
    const spans = trace?.spans ?? []
    const start = Math.min(...spans.map(span => span.start_ns))
    const end = Math.max(...spans.map(span => span.end_ns ?? span.start_ns))
    return {
      start: Number.isFinite(start) ? start : 0,
      ms: Math.max(1, Number.isFinite(end - start) ? (end - start) / 1_000_000 : 1),
    }
  }, [trace])

  const selected = trace?.spans.find(span => span.span_id === selectedSpanId) ?? null

  return (
    <div className="fixed inset-0 z-50 flex bg-black/45" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-5xl flex-col border-l border-[var(--border)] bg-[var(--bg-secondary)] shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Trace Timeline</h2>
            <div className="mt-1 flex items-center gap-2">
              <code className="truncate text-xs text-[var(--text-secondary)]">{traceId}</code>
              <CopyButton text={traceId} />
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            title="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-h-0 overflow-auto">
            {loading ? (
              <div className="p-6 text-sm text-[var(--text-secondary)]">加载中...</div>
            ) : error ? (
              <div className="p-6 text-sm text-rose-400">{error}</div>
            ) : trace && trace.spans.length > 0 ? (
              <div>
                <div className="grid grid-cols-[minmax(180px,280px)_1fr_72px] gap-3 border-b border-[var(--border)] px-3 py-2 text-[10px] uppercase text-[var(--text-secondary)]">
                  <div>Span</div>
                  <div>Waterfall</div>
                  <div className="text-right">Duration</div>
                </div>
                {trace.spans.map(span => (
                  <SpanRow
                    key={span.span_id}
                    span={span}
                    rangeStart={range.start}
                    rangeMs={range.ms}
                    selected={selectedSpanId === span.span_id}
                    onSelect={() => setSelectedSpanId(span.span_id)}
                  />
                ))}
              </div>
            ) : (
              <div className="p-6 text-sm text-[var(--text-secondary)]">暂无 trace span</div>
            )}
          </div>

          <div className="min-h-0 overflow-auto border-t border-[var(--border)] bg-[var(--bg-primary)] p-4 lg:border-l lg:border-t-0">
            {selected ? (
              <div className="space-y-4 text-xs">
                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">{selected.name}</h3>
                    <span className={cn('rounded px-2 py-0.5 text-[10px] font-medium', statusClass(selected.status))}>
                      {selected.status}
                    </span>
                  </div>
                  {selected.status_message && <p className="text-rose-300">{selected.status_message}</p>}
                </div>

                <div className="space-y-1 font-mono text-[11px] text-[var(--text-secondary)]">
                  <div>span: {selected.span_id}</div>
                  <div>parent: {selected.parent_span_id || '-'}</div>
                  <div>duration: {formatDuration(selected.duration_ms)}</div>
                </div>

                {selected.token_usage.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-[11px] font-semibold uppercase text-[var(--text-secondary)]">Token Usage</h4>
                    <div className="space-y-1">
                      {selected.token_usage.map(row => (
                        <div key={row.id} className="rounded border border-[var(--border)] bg-[var(--bg-secondary)] p-2">
                          <div className="font-medium text-[var(--text-primary)]">{row.model}</div>
                          <div className="text-[var(--text-secondary)]">
                            P {row.prompt_tokens} · C {row.completion_tokens} · Total {row.total_tokens}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <h4 className="mb-2 text-[11px] font-semibold uppercase text-[var(--text-secondary)]">Attributes</h4>
                  <pre className="max-h-72 overflow-auto rounded border border-[var(--border)] bg-[var(--bg-secondary)] p-3 text-[11px] text-[var(--text-primary)]">
                    {formatJson(selected.attributes)}
                  </pre>
                </div>

                {selected.events.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-[11px] font-semibold uppercase text-[var(--text-secondary)]">Events</h4>
                    <pre className="max-h-48 overflow-auto rounded border border-[var(--border)] bg-[var(--bg-secondary)] p-3 text-[11px] text-[var(--text-primary)]">
                      {formatJson(selected.events)}
                    </pre>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-[var(--text-secondary)]">选择一个 span 查看详情</div>
            )}
          </div>
        </div>
      </aside>
    </div>
  )
}
