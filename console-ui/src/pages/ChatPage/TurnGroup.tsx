import { useState, useRef, useEffect } from 'react'
import { Loader2, Clock, Info } from 'lucide-react'
import type { TurnGroup as TurnGroupType, TurnTokenStats, IterationTokenStats } from './types'
import { MessageBubble } from './MessageBubble'
import { ToolCallBlock } from './ToolCallBlock'
import { SubagentResultBlock, isSubagentMessage } from './SubagentResultBlock'
import { TokenInfoPopover } from './TokenInfoPopover'
import { formatTimestamp, calcDuration, getContentText, formatTokenCount } from './utils'

interface TurnGroupProps {
  turn: TurnGroupType
  index?: number
  tokenStats?: TurnTokenStats
  iterationStats?: Map<string, IterationTokenStats>
  sessionKey?: string
}

export function TurnGroupComponent({ turn, index, tokenStats, iterationStats, sessionKey }: TurnGroupProps) {
  const duration = calcDuration(turn.startTime, turn.endTime)
  const hasToolCalls = turn.toolCalls.length > 0
  const turnSeq = turn.turnSeq
  const [showTokenInfo, setShowTokenInfo] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showTokenInfo) return
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setShowTokenInfo(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showTokenInfo])

  const finalAssistant = turn.assistantSteps.filter(
    (s) => s.role === 'assistant' && !s.tool_calls && s.content !== null,
  )

  const hasFinalText = finalAssistant.some((s) => getContentText(s.content))

  const intermediateAssistants = turn.assistantSteps.filter(
    (s) => s.role === 'assistant' && s.tool_calls && getContentText(s.content),
  )

  return (
    <div className="space-y-2" id={index != null ? `turn-${index}` : undefined}>
      {/* User message */}
      {(turn.userMessage.metadata?.subagent_announce === true || isSubagentMessage(turn.userMessage.content))
        ? <SubagentResultBlock
            content={typeof turn.userMessage.content === 'string' ? turn.userMessage.content : ''}
            metadata={turn.userMessage.metadata}
          />
        : <MessageBubble message={turn.userMessage} isUser />
      }

      {/* Intermediate assistant messages with content before tool calls */}
      {intermediateAssistants.map((msg, i) => (
        <MessageBubble key={`intermediate-${i}`} message={msg} isUser={false} />
      ))}

      {/* Tool calls */}
      {hasToolCalls && (
        <div className="ml-2 pl-3 border-l-2 border-[var(--border)] space-y-1">
          <div className="flex items-center gap-1.5 text-[10px] text-[var(--text-secondary)] py-0.5">
            <Clock className="w-3 h-3" />
            <span>{formatTimestamp(turn.startTime)}</span>
            {duration && <span className="text-[var(--accent)]">({duration})</span>}
            <span>{turn.toolCalls.length} tool call{turn.toolCalls.length > 1 ? 's' : ''}</span>
            {tokenStats && !hasFinalText && (
              <div className="relative" ref={popoverRef}>
                <button
                  onClick={() => setShowTokenInfo(!showTokenInfo)}
                  className="flex items-center gap-0.5 hover:text-[var(--accent)] transition-colors"
                  title="Token usage"
                >
                  <Info className="w-3 h-3" />
                  <span>{formatTokenCount(tokenStats.total_tokens)}</span>
                </button>
                {showTokenInfo && <TokenInfoPopover stats={tokenStats} sessionKey={sessionKey} turnSeq={tokenStats.turn_seq ?? undefined} />}
              </div>
            )}
          </div>
          {turn.toolCalls.map((tc, i) => {
            // iteration 0 = initial assistant response, iteration 1+ = after each tool result
            // Tool call at index i corresponds to iteration i (the LLM call that produced it)
            const iterKey = turnSeq != null ? `${tokenStats?.conversation_id || ''}:${turnSeq}:${i}` : null
            const iterStat = iterKey ? iterationStats?.get(iterKey) : undefined
            return (
              <ToolCallBlock
                key={tc.call.id || i}
                tc={tc}
                isLoading={!turn.isComplete && !tc.result}
                tokenStats={tokenStats}
                iterationStats={iterStat}
                sessionKey={sessionKey}
                conversationId={tokenStats?.conversation_id}
                turnSeq={turnSeq}
              />
            )
          })}
        </div>
      )}

      {/* Final assistant response — pass last iteration token stats to the last bubble */}
      {finalAssistant.map((msg, i) => {
        let bubbleStats = i === finalAssistant.length - 1 ? tokenStats : undefined
        // If we have iteration data, use the last iteration (final response after all tool calls)
        if (bubbleStats && iterationStats && turnSeq != null) {
          const lastIterKey = `${bubbleStats.conversation_id || ''}:${turnSeq}:${turn.toolCalls.length}`
          const lastIter = iterationStats.get(lastIterKey)
          if (lastIter) {
            bubbleStats = {
              conversation_id: lastIter.conversation_id,
              turn_seq: lastIter.turn_seq,
              prompt_tokens: lastIter.prompt_tokens,
              completion_tokens: lastIter.completion_tokens,
              total_tokens: lastIter.total_tokens,
              llm_calls: 1,
              models: lastIter.model,
            }
          }
        }
        return (
          <MessageBubble
            key={`final-${i}`}
            message={msg}
            isUser={false}
            tokenStats={bubbleStats}
            sessionKey={sessionKey}
          />
        )
      })}

      {/* Loading indicator for incomplete turns */}
      {!turn.isComplete && (
        <div className="flex justify-start">
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-2xl rounded-bl-md bg-[var(--bg-secondary)] border border-[var(--border)] text-sm text-[var(--text-secondary)]">
            <Loader2 className="w-4 h-4 animate-spin text-[var(--accent)]" />
            <span>Processing...</span>
          </div>
        </div>
      )}
    </div>
  )
}
