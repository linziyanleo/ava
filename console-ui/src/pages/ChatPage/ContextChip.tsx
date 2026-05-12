import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Loader2, AlertCircle } from 'lucide-react'
import type { ContextPreview } from './types'
import { formatTokenCount } from './utils'
import { api } from '../../api/client'

function toneClass(pct: number): string {
  if (pct > 85) return 'bg-[var(--danger)]'
  if (pct >= 60) return 'bg-[var(--warning)]'
  return 'bg-[var(--success)]'
}

function toneTextClass(pct: number): string {
  if (pct > 85) return 'text-[var(--danger)]'
  if (pct >= 60) return 'text-[var(--warning)]'
  return 'text-[var(--text-secondary)]'
}

interface ContextChipProps {
  sessionKey: string | null
  onOpenInspector: () => void
  isMobile?: boolean
}

export function ContextChip({ sessionKey, onOpenInspector, isMobile }: ContextChipProps) {
  const [preview, setPreview] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [showHover, setShowHover] = useState(false)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const chipRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!sessionKey) {
      setPreview(null)
      setError(false)
      return
    }
    let disposed = false
    const load = () => {
      setLoading(true)
      api<ContextPreview>(`/chat/sessions/${encodeURIComponent(sessionKey)}/context-preview`)
        .then((data) => {
          if (!disposed) {
            setPreview(data)
            setError(false)
          }
        })
        .catch(() => {
          if (!disposed) {
            setPreview(null)
            setError(true)
          }
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    const timer = window.setInterval(load, 10_000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [sessionKey])

  const handleMouseEnter = () => {
    if (isMobile) return
    hoverTimerRef.current = setTimeout(() => setShowHover(true), 200)
  }
  const handleMouseLeave = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    setShowHover(false)
  }

  if (!sessionKey) return null

  const pct = preview?.totals.utilization_pct ?? 0
  const used = preview?.totals.request_total_tokens ?? 0
  const budget = preview?.totals.ctx_budget ?? 0
  const estimateScope = preview?.totals.estimate_scope || 'unknown'

  if (loading && !preview) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)]">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {isMobile ? '...' : 'Loading…'}
      </span>
    )
  }

  if (error && !preview) {
    return (
      <button
        type="button"
        onClick={onOpenInspector}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--danger)]/30 px-2.5 py-1.5 text-xs text-[var(--danger)]"
      >
        <AlertCircle className="h-3.5 w-3.5" />
        Error
      </button>
    )
  }

  if (isMobile) {
    return (
      <button
        type="button"
        onClick={onOpenInspector}
        className={`inline-flex items-center gap-1 rounded-md border border-[var(--border)] px-2 py-1.5 text-xs ${toneTextClass(pct)}`}
      >
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${toneClass(pct)}`} />
        {Math.round(pct)}%
        <ChevronDown className="h-3 w-3" />
      </button>
    )
  }

  return (
    <div className="relative" onMouseLeave={handleMouseLeave}>
      <button
        ref={chipRef}
        type="button"
        onClick={onOpenInspector}
        onMouseEnter={handleMouseEnter}
        className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] transition-colors hover:bg-[var(--bg-tertiary)]"
      >
        <div className="flex h-1 w-10 items-center overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
          <div
            className={`h-full rounded-full transition-all ${toneClass(pct)}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        <span className={toneTextClass(pct)}>{Math.round(pct)}%</span>
        <span className="text-[var(--text-tertiary)]">
          {formatTokenCount(used)}/{formatTokenCount(budget)}
        </span>
        <ChevronDown className="h-2.5 w-2.5 text-[var(--text-tertiary)]" />
      </button>

      {showHover && preview && (
        <div className="absolute left-1/2 top-full z-40 mt-2 w-64 -translate-x-1/2 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3 text-xs shadow-xl">
          <table className="w-full">
            <tbody>
              <HoverRow label="System" tokens={preview.totals.system_tokens} />
              <HoverRow label="Runtime" tokens={preview.totals.runtime_tokens} />
              <HoverRow label="Tools" tokens={preview.totals.tool_tokens} />
              <HoverRow
                label="History"
                tokens={preview.totals.history_tokens}
                suffix={
                  preview.window
                    ? `${preview.window.kept_count} msgs in window`
                    : undefined
                }
              />
            </tbody>
          </table>
          <div className="mt-2 border-t border-[var(--border)] pt-2">
            <div className="flex justify-between text-[var(--text-primary)]">
              <span>Total</span>
              <span>{formatTokenCount(used)} / {formatTokenCount(budget)} budget</span>
            </div>
          </div>
          <div className="mt-1.5 text-[10px] leading-tight text-[var(--text-tertiary)]">
            Scope: {estimateScope.replaceAll('_', ' ')}
          </div>
        </div>
      )}
    </div>
  )
}

function HoverRow({ label, tokens, suffix }: { label: string; tokens: number; suffix?: string }) {
  return (
    <tr>
      <td className="py-0.5 text-[var(--text-secondary)]">{label}</td>
      <td className="py-0.5 text-right text-[var(--text-primary)]">
        {formatTokenCount(tokens)}
        {suffix && (
          <span className="ml-1.5 text-[var(--text-tertiary)]">← {suffix}</span>
        )}
      </td>
    </tr>
  )
}
