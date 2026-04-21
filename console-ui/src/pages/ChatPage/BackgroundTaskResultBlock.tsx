import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'
import { Bot, CheckCircle, ChevronDown, ChevronRight, Clock3, XCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '../../lib/utils'
import { formatTimestamp } from './utils'
import { parseBackgroundTaskMessage } from './backgroundTask'

function formatDuration(durationMs: number | null): string {
  if (durationMs == null || Number.isNaN(durationMs)) return 'unknown'
  if (durationMs < 1000) return `${durationMs}ms`
  if (durationMs < 60_000) return `${(durationMs / 1000).toFixed(1)}s`

  const minutes = Math.floor(durationMs / 60_000)
  const seconds = Math.round((durationMs % 60_000) / 1000)
  return `${minutes}m ${seconds}s`
}

// eslint-disable-next-line react-refresh/only-export-components
export function getBackgroundTaskPreview(content: string): string {
  const parsed = parseBackgroundTaskMessage(content)
  if (!parsed?.body) return ''
  const firstLine = parsed.body.split('\n').find((line) => line.trim())
  if (!firstLine) return ''
  return firstLine.length > 90 ? `${firstLine.slice(0, 90)}...` : firstLine
}

interface BackgroundTaskResultBlockProps {
  content: string
  timestamp?: string
}

export function BackgroundTaskResultBlock({ content, timestamp }: BackgroundTaskResultBlockProps) {
  const parsed = parseBackgroundTaskMessage(content)
  const [expanded, setExpanded] = useState(() => (parsed?.body.length || 0) <= 220)
  const preview = useMemo(() => getBackgroundTaskPreview(content), [content])
  const markdownComponents = useMemo(() => ({
    code({ className, children, ...props }: { className?: string; children?: ReactNode; [key: string]: unknown }) {
      const isInline = !className?.includes('language-') && !String(children).includes('\n')
      if (isInline) {
        return (
          <code className="rounded bg-black/20 px-1 py-0.5 text-[0.85em] text-[var(--accent)]" {...props}>
            {children}
          </code>
        )
      }
      return (
        <pre className="my-2 overflow-x-auto rounded-md bg-[var(--bg-secondary)] p-3">
          <code {...props}>{children}</code>
        </pre>
      )
    },
    a({ children, href }: { children?: ReactNode; href?: string }) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent)] underline hover:opacity-80"
        >
          {children}
        </a>
      )
    },
    table({ children }: { children?: ReactNode }) {
      return (
        <div className="my-2 overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">{children}</table>
        </div>
      )
    },
    th({ children }: { children?: ReactNode }) {
      return (
        <th className="border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-1.5 text-left font-semibold">
          {children}
        </th>
      )
    },
    td({ children }: { children?: ReactNode }) {
      return (
        <td className="border border-[var(--border)] px-3 py-1.5">
          {children}
        </td>
      )
    },
  }), [])

  if (!parsed) return null

  const isSuccess = parsed.status === 'SUCCESS'
  const statusLabel = isSuccess ? 'success' : parsed.status.toLowerCase()

  return (
    <div className="my-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-xs overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--border)] bg-[var(--bg-tertiary,var(--bg-secondary))]">
        <Bot className="w-3.5 h-3.5 shrink-0 text-[var(--text-secondary)]" />
        <span className="font-medium text-[var(--text-primary)]">Background Task</span>
        <span className="shrink-0 rounded bg-[var(--bg-secondary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] border border-[var(--border)]">
          {parsed.taskType}
        </span>
        <span className={cn(
          'shrink-0 flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium',
          isSuccess
            ? 'bg-emerald-500/15 text-emerald-400'
            : 'bg-rose-500/15 text-rose-400',
        )}>
          {isSuccess
            ? <CheckCircle className="w-3 h-3" />
            : <XCircle className="w-3 h-3" />}
          {statusLabel}
        </span>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-[var(--text-secondary)]">
          <Clock3 className="w-3 h-3" />
          {formatDuration(parsed.durationMs)}
        </span>
      </div>

      <div className="px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-secondary)]">
          <span>Task {parsed.taskType}:{parsed.taskId}</span>
          {timestamp && <span>{formatTimestamp(timestamp)}</span>}
        </div>

        {parsed.body && (
          <div className="mt-2">
            <button
              onClick={() => setExpanded((value) => !value)}
              className="flex w-full items-center gap-1 text-left text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              {expanded
                ? <ChevronDown className="w-3 h-3 shrink-0" />
                : <ChevronRight className="w-3 h-3 shrink-0" />}
              <span className="font-medium">Details</span>
              {!expanded && preview && (
                <span className="ml-1.5 truncate text-[var(--text-secondary)]">- {preview}</span>
              )}
            </button>

            {expanded && (
              <div className="mt-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)]">
                <div className="markdown-body">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownComponents as never}
                  >
                    {parsed.body}
                  </ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
