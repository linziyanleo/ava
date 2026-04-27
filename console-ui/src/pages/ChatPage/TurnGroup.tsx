import { Loader2 } from 'lucide-react'
import type { TurnGroup as TurnGroupType, TurnTokenStats, IterationTokenStats } from './types'
import { MessageBubble } from './MessageBubble'
import { ToolCallBlock } from './ToolCallBlock'
import { SubagentResultBlock, isSubagentMessage } from './SubagentResultBlock'
import { BackgroundTaskResultBlock } from './BackgroundTaskResultBlock'
import { isBackgroundTaskMessage } from './backgroundTask'
import { getContentText } from './utils'

interface TurnGroupProps {
  turn: TurnGroupType
  index?: number
  tokenStats?: TurnTokenStats
  iterationStats?: Map<string, IterationTokenStats>
  sessionKey?: string
  suppressLoadingIndicator?: boolean
}

export function TurnGroupComponent({
  turn,
  index,
  tokenStats,
  iterationStats,
  sessionKey,
  suppressLoadingIndicator = false,
}: TurnGroupProps) {
  const turnSeq = turn.turnSeq
  const maxIteration = turn.toolCalls.reduce((max, tc) => Math.max(max, tc.iteration), -1)

  const finalAssistant = turn.assistantSteps.filter(
    (s) => s.role === 'assistant' && !s.tool_calls && s.content !== null,
  )

  const intermediateAssistants = turn.assistantSteps.filter(
    (s) => s.role === 'assistant' && s.tool_calls && getContentText(s.content),
  )

  return (
    <div className="space-y-2" id={index != null ? `turn-${index}` : undefined}>
      {/* User message */}
      {isBackgroundTaskMessage(turn.userMessage.content)
        ? <BackgroundTaskResultBlock
            content={typeof turn.userMessage.content === 'string' ? turn.userMessage.content : ''}
            timestamp={turn.userMessage.timestamp}
          />
        : (turn.userMessage.metadata?.subagent_announce === true || isSubagentMessage(turn.userMessage.content))
        ? <SubagentResultBlock
            content={typeof turn.userMessage.content === 'string' ? turn.userMessage.content : ''}
            metadata={turn.userMessage.metadata}
          />
        : <MessageBubble message={turn.userMessage} isUser />
      }

      {/* Intermediate assistant messages with content before tool calls */}
      {intermediateAssistants.map((msg, i) => (
        isBackgroundTaskMessage(msg.content)
          ? <BackgroundTaskResultBlock
              key={`intermediate-${i}`}
              content={typeof msg.content === 'string' ? msg.content : ''}
              timestamp={msg.timestamp}
            />
          : <MessageBubble key={`intermediate-${i}`} message={msg} isUser={false} />
      ))}

      {/* Tool calls — each rendered at the same level as message bubbles */}
      {turn.toolCalls.map((tc, i) => {
        const iterKey = turnSeq != null ? `${tokenStats?.conversation_id || ''}:${turnSeq}:${tc.iteration}` : null
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
            callTimestamp={tc.callTimestamp}
            resultTimestamp={tc.result?.timestamp}
          />
        )
      })}

      {/* Final assistant response — pass last iteration token stats to the last bubble */}
      {finalAssistant.map((msg, i) => {
        let bubbleStats = i === finalAssistant.length - 1 ? tokenStats : undefined
        // If we have iteration data, use the last iteration (final response after all tool calls)
        if (bubbleStats && iterationStats && turnSeq != null) {
          const lastIterKey = `${bubbleStats.conversation_id || ''}:${turnSeq}:${maxIteration + 1}`
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
	              trace_id: lastIter.trace_id,
	              span_id: lastIter.span_id,
	            }
          }
        }
        return (
          isBackgroundTaskMessage(msg.content)
            ? <BackgroundTaskResultBlock
                key={`final-${i}`}
                content={typeof msg.content === 'string' ? msg.content : ''}
                timestamp={msg.timestamp}
              />
            : <MessageBubble
                key={`final-${i}`}
                message={msg}
                isUser={false}
                tokenStats={bubbleStats}
                sessionKey={sessionKey}
              />
        )
      })}

      {/* Loading indicator for incomplete turns */}
      {!turn.isComplete && !suppressLoadingIndicator && (
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
