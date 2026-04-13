import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Copy, Check, ExternalLink } from 'lucide-react'
import type { TurnTokenStats } from './types'
import { formatTokenCount } from './utils'

interface TokenInfoPopoverProps {
  stats: TurnTokenStats
  sessionKey?: string
  turnSeq?: number
  isMobile?: boolean
  onClose?: () => void
}

export function TokenInfoPopover({ stats, sessionKey, turnSeq, isMobile, onClose }: TokenInfoPopoverProps) {
  const [copied, setCopied] = useState(false)
  const navigate = useNavigate()

  const handleCopySession = async () => {
    if (!sessionKey) return
    await navigator.clipboard.writeText(sessionKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (isMobile) {
    return (
      <>
        {/* Backdrop */}
        <div className="fixed inset-0 z-[100] bg-black/50" onClick={onClose} />
        {/* Centered popover */}
        <div className="fixed z-[101] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-72 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] shadow-2xl p-4 text-xs">
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-[var(--text-secondary)]">Prompt</span>
              <span className="font-mono text-[var(--text-primary)]">{formatTokenCount(stats.prompt_tokens)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-secondary)]">Completion</span>
              <span className="font-mono text-[var(--text-primary)]">{formatTokenCount(stats.completion_tokens)}</span>
            </div>
            <div className="flex justify-between border-t border-[var(--border)] pt-2">
              <span className="text-[var(--text-secondary)] font-medium">Total</span>
              <span className="font-mono font-medium text-[var(--accent)]">{formatTokenCount(stats.total_tokens)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-secondary)]">LLM Calls</span>
              <span className="font-mono text-[var(--text-primary)]">{stats.llm_calls}</span>
            </div>
            {stats.models && (
              <div className="border-t border-[var(--border)] pt-2 truncate">
                <span className="text-[var(--text-secondary)]">Model: </span>
                <span className="text-[var(--text-primary)]">{stats.models}</span>
              </div>
            )}
          </div>

          {sessionKey && (
            <div className="mt-3 pt-3 border-t border-[var(--border)] flex gap-2">
              <button
                onClick={handleCopySession}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-md bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                title="复制 Session ID"
              >
                {copied ? <Check className="w-3 h-3 text-[var(--success)]" /> : <Copy className="w-3 h-3" />}
                <span>{copied ? '已复制' : '复制 ID'}</span>
              </button>
              <button
                onClick={() => {
                  const params = new URLSearchParams({ session_key: sessionKey })
                  if (stats.conversation_id) params.set('conversation_id', stats.conversation_id)
                  if (turnSeq != null) params.set('turn_seq', String(turnSeq))
                  navigate(`/tokens?${params.toString()}`)
                }}
                className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-md bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                title="在 Token 统计中查看"
              >
                <ExternalLink className="w-3 h-3" />
                <span>Token 统计</span>
              </button>
            </div>
          )}
        </div>
      </>
    )
  }

  return (
    <div className="absolute left-0 bottom-full mb-1 z-50 w-56 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] shadow-lg p-2.5 text-[10px]">
      <div className="space-y-1">
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Prompt</span>
          <span className="font-mono text-[var(--text-primary)]">{formatTokenCount(stats.prompt_tokens)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Completion</span>
          <span className="font-mono text-[var(--text-primary)]">{formatTokenCount(stats.completion_tokens)}</span>
        </div>
        <div className="flex justify-between border-t border-[var(--border)] pt-1">
          <span className="text-[var(--text-secondary)] font-medium">Total</span>
          <span className="font-mono font-medium text-[var(--accent)]">{formatTokenCount(stats.total_tokens)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">LLM Calls</span>
          <span className="font-mono text-[var(--text-primary)]">{stats.llm_calls}</span>
        </div>
        {stats.models && (
          <div className="border-t border-[var(--border)] pt-1 truncate">
            <span className="text-[var(--text-secondary)]">Model: </span>
            <span className="text-[var(--text-primary)]">{stats.models}</span>
          </div>
        )}
      </div>

      {sessionKey && (
        <div className="mt-2 pt-2 border-t border-[var(--border)] flex gap-1.5">
          <button
            onClick={handleCopySession}
            className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded-md bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            title="复制 Session ID"
          >
            {copied ? <Check className="w-3 h-3 text-[var(--success)]" /> : <Copy className="w-3 h-3" />}
            <span>{copied ? '已复制' : '复制 ID'}</span>
          </button>
          <button
            onClick={() => {
              const params = new URLSearchParams({ session_key: sessionKey })
              if (stats.conversation_id) params.set('conversation_id', stats.conversation_id)
              if (turnSeq != null) params.set('turn_seq', String(turnSeq))
              navigate(`/tokens?${params.toString()}`)
            }}
            className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded-md bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            title="在 Token 统计中查看"
          >
            <ExternalLink className="w-3 h-3" />
            <span>Token 统计</span>
          </button>
        </div>
      )}
    </div>
  )
}
