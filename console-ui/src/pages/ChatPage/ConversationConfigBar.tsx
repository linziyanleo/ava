import { useEffect, useState } from 'react'
import { Bot, HardDrive, Loader2, Radio, Settings2, X } from 'lucide-react'
import type { SceneType, SessionMeta } from './types'
import { SCENE_LABELS } from './types'
import { formatTokenCount } from './utils'
import { api } from '../../api/client'

const CONTEXT_LIMIT = 200_000
const CHAT_AGENTS = [
  { id: 'nanobot', label: 'Nanobot' },
  { id: 'codex', label: 'Codex' },
  { id: 'claude_code', label: 'Claude Code' },
]

interface ContextSizeData {
  used_tokens: number
  model_limit: number
  breakdown: Record<string, number>
  compression_preview?: string
  before_after_diff?: CompressionDiff | null
}

interface CompressionDiff {
  before?: Array<{ role?: string; content?: string }>
  after?: Array<{ role?: string; content?: string }>
  summary_text?: string
  kept_messages?: Array<{ role?: string; content?: string }>
}

interface CompressionResult extends ContextSizeData {
  before_tokens: number
  after_tokens: number
  compression_preview: string
  before_after_diff: CompressionDiff
}

function contextToneClass(contextPercent: number) {
  if (contextPercent > 85) return 'bg-[var(--danger)]'
  if (contextPercent >= 60) return 'bg-[var(--warning)]'
  return 'bg-[var(--success)]'
}

export function ConversationConfigBar({
  session,
  activeScene,
  isReadOnly,
  isMobile,
  onParticipantsChange,
}: {
  session: SessionMeta | null
  activeScene: SceneType
  isReadOnly: boolean
  isMobile?: boolean
  onParticipantsChange?: (participants: string[]) => Promise<void> | void
}) {
  const [contextSize, setContextSize] = useState<ContextSizeData | null>(null)
  const [compressionPreview, setCompressionPreview] = useState<CompressionResult | null>(null)
  const [compressionDiffOpen, setCompressionDiffOpen] = useState(false)
  const [mobileExpanded, setMobileExpanded] = useState(false)
  const [compressing, setCompressing] = useState(false)
  const [compressError, setCompressError] = useState('')
  const sessionId = session?.key.startsWith('console:') ? session.key.replace(/^console:/, '') : ''
  const usedTokens = contextSize?.used_tokens ?? session?.token_stats.total_tokens ?? 0
  const modelLimit = contextSize?.model_limit ?? CONTEXT_LIMIT
  const selectedParticipants = session?.participants?.length
    ? session.participants
    : [session?.default_responder_agent_id || 'nanobot']
  const contextPercent = modelLimit > 0 ? Math.min(Math.round((usedTokens / modelLimit) * 100), 100) : 0
  const contextTone = contextToneClass(contextPercent)
  const participantLabel = selectedParticipants
    .map((id) => CHAT_AGENTS.find((agent) => agent.id === id)?.label || id)
    .join(' / ')

  useEffect(() => {
    if (!sessionId) {
      setContextSize(null)
      return
    }
    let disposed = false
    api<ContextSizeData>(`/chat/sessions/${encodeURIComponent(sessionId)}/context-size`)
      .then((data) => {
        if (!disposed) setContextSize(data)
      })
      .catch(() => {
        if (!disposed) setContextSize(null)
      })
    return () => {
      disposed = true
    }
  }, [sessionId, session?.updated_at, session?.message_count, session?.token_stats.total_tokens])

  const handleCompress = async () => {
    if (!sessionId || isReadOnly || compressing) return
    setCompressing(true)
    setCompressError('')
    try {
      const result = await api<CompressionResult>(`/chat/sessions/${encodeURIComponent(sessionId)}/compress`, {
        method: 'POST',
      })
      setCompressionPreview(result)
      setCompressionDiffOpen(true)
      setContextSize({
        used_tokens: result.after_tokens,
        model_limit: result.model_limit,
        breakdown: result.breakdown || {},
        compression_preview: result.compression_preview,
        before_after_diff: result.before_after_diff,
      })
    } catch (err) {
      setCompressError(err instanceof Error ? err.message : 'Compress failed')
    } finally {
      setCompressing(false)
    }
  }

  if (isMobile && !mobileExpanded) {
    return (
      <div className="flex min-h-12 items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2">
        <span className="inline-flex min-w-0 flex-1 items-center gap-1.5 rounded-md border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-secondary)]">
          <Bot className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
          <span className="truncate">{participantLabel || 'Agent'}</span>
        </span>
        <span className="inline-flex shrink-0 items-center gap-1 rounded-md border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-secondary)]">
          <HardDrive className="h-3.5 w-3.5" />
          {contextPercent}%
        </span>
        <button
          type="button"
          onClick={() => setMobileExpanded(true)}
          className="shrink-0 rounded-md border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          展开
        </button>
      </div>
    )
  }

  return (
    <div className="flex min-h-12 flex-wrap items-center gap-3 border-b border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-[var(--bg-tertiary)] text-[var(--accent)]">
          <Bot className="h-4 w-4" />
        </span>
        <div className="flex flex-wrap gap-1">
          {CHAT_AGENTS.map((agent) => {
            const selected = selectedParticipants.includes(agent.id)
            return (
              <button
                key={agent.id}
                type="button"
                disabled={isReadOnly || !session || !onParticipantsChange}
                aria-pressed={selected}
                onClick={() => {
                  const next = selected
                    ? selectedParticipants.filter((id) => id !== agent.id)
                    : [...selectedParticipants, agent.id]
                  if (next.length > 0) {
                    void onParticipantsChange?.(next)
                  }
                }}
                className={
                  selected
                    ? 'rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-2 py-1 text-xs text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-70'
                    : 'rounded-md border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50'
                }
                title={selected ? '参与当前会话' : '加入当前会话'}
              >
                {agent.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex min-w-52 flex-1 items-center gap-2">
        <HardDrive className="h-4 w-4 text-[var(--text-secondary)]" />
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center justify-between gap-3 text-[10px] text-[var(--text-secondary)]">
            <span>Context Size</span>
            <span>{formatTokenCount(usedTokens)} / {formatTokenCount(modelLimit)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
            <div className={`h-full rounded-full ${contextTone}`} style={{ width: `${contextPercent}%` }} />
          </div>
          {compressError && (
            <div className="mt-1 truncate text-[10px] text-[var(--danger)]">{compressError}</div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-md border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-secondary)]">
          <Radio className="h-3.5 w-3.5" />
          {SCENE_LABELS[activeScene]}
        </span>
        <button
          type="button"
          disabled={isReadOnly || !sessionId || compressing}
          onClick={() => { void handleCompress() }}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border)] px-2.5 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {compressing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Settings2 className="h-3.5 w-3.5" />}
          压缩
        </button>
        {compressionPreview && (
          <button
            type="button"
            onClick={() => setCompressionDiffOpen(true)}
            className="inline-flex h-8 items-center rounded-md border border-[var(--border)] px-2.5 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            查看压缩后上下文
          </button>
        )}
        {isMobile && (
          <button
            type="button"
            onClick={() => setMobileExpanded(false)}
            className="inline-flex h-8 items-center rounded-md border border-[var(--border)] px-2.5 text-xs text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          >
            收起
          </button>
        )}
      </div>
      {compressionPreview && compressionDiffOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[80vh] w-full max-w-5xl overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
              <div>
                <div className="text-sm font-medium text-[var(--text-primary)]">查看压缩后上下文</div>
                <div className="text-xs text-[var(--text-secondary)]">
                  {formatTokenCount(compressionPreview.before_tokens)} → {formatTokenCount(compressionPreview.after_tokens)}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setCompressionDiffOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="grid max-h-[64vh] overflow-y-auto md:grid-cols-2">
              <div className="border-b border-[var(--border)] p-4 md:border-b-0 md:border-r">
                <div className="mb-2 text-xs font-medium uppercase text-[var(--text-tertiary)]">Before</div>
                <div className="space-y-2">
                  {(compressionPreview.before_after_diff.before || []).map((item, index) => (
                    <div key={`before-${index}`} className="rounded-md bg-red-500/5 px-3 py-2 text-xs text-[var(--text-secondary)]">
                      <span className="font-medium text-[var(--text-primary)]">{item.role || 'message'}: </span>
                      {item.content}
                    </div>
                  ))}
                </div>
              </div>
              <div className="p-4">
                <div className="mb-2 text-xs font-medium uppercase text-[var(--text-tertiary)]">After</div>
                <div className="space-y-2">
                  {(compressionPreview.before_after_diff.after || []).map((item, index) => (
                    <div key={`after-${index}`} className="rounded-md bg-emerald-500/5 px-3 py-2 text-xs text-[var(--text-secondary)]">
                      <span className="font-medium text-[var(--text-primary)]">{item.role || 'message'}: </span>
                      {item.content}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
