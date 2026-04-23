import { useState } from 'react'
import { Brain, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { MarkdownRenderer } from '../../components/markdown/MarkdownRenderer'
import { MessageBubble } from './MessageBubble'
import { ToolCallBlock } from './ToolCallBlock'
import type { InFlightTurn } from './inFlightTurn'

interface InFlightTurnBlockProps {
  turn: InFlightTurn
}

export function InFlightTurnBlock({ turn }: InFlightTurnBlockProps) {
  const [thinkingExpanded, setThinkingExpanded] = useState(false)
  const hasVisibleOutput = Boolean(
    turn.thinkingContent
    || turn.draftAssistant
    || turn.entries.length > 0,
  )

  return (
    <div className="space-y-2">
      <MessageBubble message={turn.userMessage} isUser />

      {turn.entries.map((entry, index) => (
        entry.kind === 'assistant' ? (
          <MessageBubble
            key={`inflight-assistant-${index}`}
            message={entry.message}
            isUser={false}
          />
        ) : (
          <ToolCallBlock
            key={entry.tool.call.id || `inflight-tool-${index}`}
            tc={entry.tool}
            isLoading={entry.tool.isLoading}
          />
        )
      ))}

      {turn.thinkingContent && (
        <div className="flex justify-start">
          <div
            className="max-w-[80%] rounded-2xl rounded-bl-md border border-[var(--border)] text-sm overflow-hidden"
            style={{ background: 'var(--bg-tertiary, var(--bg-secondary))' }}
          >
            <button
              onClick={() => setThinkingExpanded((value) => !value)}
              className="flex items-center gap-1.5 w-full px-3 py-1.5 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Brain className="w-3.5 h-3.5 text-[var(--accent)] animate-pulse" />
              <span className="font-medium">Thinking...</span>
              {thinkingExpanded ? (
                <ChevronDown className="w-3 h-3 ml-auto" />
              ) : (
                <ChevronRight className="w-3 h-3 ml-auto" />
              )}
            </button>
            {thinkingExpanded && (
              <div className="px-3 pb-2 border-t border-[var(--border)]">
                <pre
                  className="whitespace-pre-wrap font-[inherit] text-[12px] text-[var(--text-secondary)] italic leading-relaxed max-h-[200px] overflow-y-auto mt-1.5"
                  style={{ lineHeight: 'var(--cjk-line-height)' }}
                >
                  {turn.thinkingContent}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {turn.draftAssistant && (
        <div className="flex justify-start">
          <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-bl-md bg-[var(--bg-secondary)] border border-[var(--border)] text-sm">
            <MarkdownRenderer content={turn.draftAssistant} />
            <span className="inline-block w-2 h-4 bg-[var(--accent)] animate-pulse ml-0.5" />
          </div>
        </div>
      )}

      {turn.processing && !hasVisibleOutput && (
        <div className="flex justify-start">
          <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-bl-md bg-[var(--bg-secondary)] border border-[var(--border)] text-sm text-[var(--text-secondary)]">
            <span className="inline-flex items-center gap-1.5">
              <Loader2 className="w-4 h-4 animate-spin text-[var(--accent)]" />
              <span>Processing...</span>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
