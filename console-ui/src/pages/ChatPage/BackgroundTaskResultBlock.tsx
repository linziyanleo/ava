import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, CheckCircle, ChevronDown, ChevronRight, Clock3, ExternalLink, XCircle } from 'lucide-react'
import { MarkdownRenderer } from '../../components/markdown/MarkdownRenderer'
import { cn } from '../../lib/utils'
import { displayImagePath, extractImagePaths, formatTimestamp, imageUrl } from './utils'
import { parseBackgroundTaskMessage } from './backgroundTask'
import { ImageCarousel } from './ImageCarousel'

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
  taskId?: string
  sessionKey?: string
  conversationId?: string | null
  highlighted?: boolean
}

export function BackgroundTaskResultBlock({ content, timestamp, taskId: taskIdProp, highlighted }: BackgroundTaskResultBlockProps) {
  const navigate = useNavigate()
  const parsed = parseBackgroundTaskMessage(content)
  const [expanded, setExpanded] = useState(() => (parsed?.body.length || 0) <= 220)
  const [isHighlighted, setIsHighlighted] = useState(false)
  const preview = useMemo(() => getBackgroundTaskPreview(content), [content])
  const imagePaths = useMemo(
    () => parsed?.taskType === 'image_gen' ? extractImagePaths(parsed.body) : [],
    [parsed?.body, parsed?.taskType],
  )

  const effectiveTaskId = taskIdProp ?? parsed?.taskId

  const prevHighlightedRef = useRef(highlighted)
  useEffect(() => {
    if (highlighted && !prevHighlightedRef.current) {
      setIsHighlighted(true)
      const timer = setTimeout(() => setIsHighlighted(false), 2000)
      return () => clearTimeout(timer)
    }
    prevHighlightedRef.current = highlighted
  }, [highlighted])

  const handleViewBgTask = useCallback(() => {
    if (!effectiveTaskId) return
    navigate(`/bg-tasks?task_id=${encodeURIComponent(effectiveTaskId)}`)
  }, [navigate, effectiveTaskId])

  if (!parsed) return null

  const isSuccess = parsed.status === 'SUCCESS'
  const statusLabel = isSuccess ? 'success' : parsed.status.toLowerCase()

  return (
    <div
      data-bg-task-id={effectiveTaskId}
      id={effectiveTaskId ? `bg-task-result-${effectiveTaskId}` : undefined}
      className={cn(
        'my-1.5 rounded-lg border text-xs overflow-hidden transition-all duration-500',
        isHighlighted
          ? 'border-[var(--accent)] bg-[var(--accent)]/5 ring-1 ring-[var(--accent)]/30'
          : 'border-[var(--border)] bg-[var(--bg-secondary)]',
      )}
    >
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
        <span className="ml-auto flex items-center gap-1.5 text-[10px] text-[var(--text-secondary)]">
          <Clock3 className="w-3 h-3" />
          {formatDuration(parsed.durationMs)}
          {effectiveTaskId && (
            <button
              onClick={handleViewBgTask}
              title="查看后台任务"
              className="ml-1 flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors"
            >
              <ExternalLink className="w-3 h-3" />
              <span>后台任务</span>
            </button>
          )}
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
                {imagePaths.length > 0 && (
                  <div className="mb-2 space-y-1.5">
                    <ImageCarousel urls={imagePaths.map((path) => imageUrl(path))} alt="Generated image" maxHeight={220} />
                    <div className="flex flex-wrap gap-1.5">
                      {imagePaths.map((path) => (
                        <span
                          key={path}
                          className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--text-secondary)]"
                          title={path}
                        >
                          {displayImagePath(path)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <MarkdownRenderer content={parsed.body} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
