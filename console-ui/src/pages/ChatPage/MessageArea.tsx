import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { MessageSquare, Loader2, ArrowDownToLine } from 'lucide-react'
import type { ChatComposePayload, DirectTaskMessage, DirectTaskSubmitParams, SessionMeta, ConversationMeta, TurnGroup, TurnTokenStats, IterationTokenStats, ChatStreamStatus, ActiveChatTransport } from './types';
import { TurnGroupComponent } from './TurnGroup'
import { ChatInput } from './ChatInput'
import { ChatHeader } from './ChatHeader'
import { InFlightTurnBlock } from './InFlightTurnBlock'
import { TaskStatusCard } from './TaskStatusCard'
import { ChainBubble } from './ChainBubble'
import { HudBar } from './HudBar'
import type { InFlightTurn } from './inFlightTurn'
import { api } from '../../api/client';

type TaskTimelineItem =
  | { kind: 'chain'; chainId: string; tasks: DirectTaskMessage[] }
  | { kind: 'task'; task: DirectTaskMessage }

function taskSortKey(task: DirectTaskMessage) {
  return task.started_at ?? Number.MAX_SAFE_INTEGER
}

function orderTaskList(tasks: DirectTaskMessage[]) {
  return [...tasks].sort((a, b) => {
    const turnDelta = (a.origin_turn_seq ?? Number.MAX_SAFE_INTEGER) - (b.origin_turn_seq ?? Number.MAX_SAFE_INTEGER)
    if (turnDelta !== 0) return turnDelta
    const startedDelta = taskSortKey(a) - taskSortKey(b)
    if (startedDelta !== 0) return startedDelta
    return a.task_id.localeCompare(b.task_id)
  })
}

function buildTaskTimelineItems(tasks: DirectTaskMessage[]): TaskTimelineItem[] {
  const byChain = new Map<string, DirectTaskMessage[]>()
  const standalone: DirectTaskMessage[] = []
  for (const task of orderTaskList(tasks)) {
    if (task.chain_id) {
      byChain.set(task.chain_id, [...(byChain.get(task.chain_id) || []), task])
    } else {
      standalone.push(task)
    }
  }

  const items: Array<TaskTimelineItem & { order: number; tie: string }> = []
  for (const [chainId, chainTasks] of byChain.entries()) {
    const ordered = orderTaskList(chainTasks)
    items.push({ kind: 'chain', chainId, tasks: ordered, order: Math.min(...ordered.map(taskSortKey)), tie: chainId })
  }
  for (const task of standalone) {
    items.push({ kind: 'task', task, order: taskSortKey(task), tie: task.task_id })
  }

  return items
    .sort((a, b) => (a.order - b.order) || a.tie.localeCompare(b.tie))
    .map(({ order: _order, tie: _tie, ...item }) => item)
}

interface MessageAreaProps {
  session: SessionMeta | null
  conversation: ConversationMeta | null
  conversationId: string | null
  turns: TurnGroup[]
  inFlightTurn: InFlightTurn | null
  directTasks: DirectTaskMessage[]
  loading: boolean
  isConsole: boolean
  isReadOnly?: boolean
  transportStatus: ChatStreamStatus
  activeTransport: ActiveChatTransport
  sendDisabled: boolean
  onSend: (payload: ChatComposePayload) => Promise<void> | void
  onStopCurrentTurn: () => Promise<void> | void
  onSubmitDirectTask: (params: DirectTaskSubmitParams) => Promise<void> | void
  onRefresh: () => void
  isMobile?: boolean
  onToggleSessionPanel?: () => void
  onParticipantsChange?: (participants: string[]) => Promise<void> | void
  targetTaskId?: string | null
  targetTurnSeq?: number | null
  targetTraceId?: string | null
}

export function MessageArea({ session, conversation, conversationId, turns, inFlightTurn, directTasks, loading, isConsole, isReadOnly, transportStatus, activeTransport, sendDisabled, onSend, onStopCurrentTurn, onSubmitDirectTask, onRefresh, isMobile, onToggleSessionPanel, onParticipantsChange, targetTaskId, targetTurnSeq, targetTraceId }: MessageAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isInitialScroll = useRef(true)
  const scrollRafRef = useRef<number | null>(null)
  const [turnTokenStats, setTurnTokenStats] = useState<Map<number, TurnTokenStats>>(new Map());
  const [iterationStats, setIterationStats] = useState<Map<string, IterationTokenStats>>(new Map());
  const [showScrollDown, setShowScrollDown] = useState(false)

  const handleSkillSelect = useCallback((skillName: string) => {
    if (sendDisabled || isReadOnly) return
    void onSend({ text: `@${skillName}`, attachments: [] })
  }, [isReadOnly, onSend, sendDisabled])

  useEffect(() => {
    if (!session?.key) {
      setTurnTokenStats(new Map());
      setIterationStats(new Map());
      return;
    }
    const conversationFilter = conversationId !== null
      ? `&conversation_id=${encodeURIComponent(conversationId)}`
      : ''
    api<TurnTokenStats[]>(`/stats/tokens/by-session?session_key=${encodeURIComponent(session.key)}${conversationFilter}`)
      .then(data => {
        const map = new Map<number, TurnTokenStats>();
        for (const item of data) {
          if (item.turn_seq != null) map.set(item.turn_seq, item);
        }
        setTurnTokenStats(map);
      })
      .catch(() => setTurnTokenStats(new Map()));
    api<IterationTokenStats[]>(`/stats/tokens/by-session/detailed?session_key=${encodeURIComponent(session.key)}${conversationFilter}`)
      .then(data => {
        const map = new Map<string, IterationTokenStats>();
        for (const item of data) {
          map.set(`${item.conversation_id || ''}:${item.turn_seq ?? ''}:${item.iteration}`, item);
        }
        setIterationStats(map);
      })
      .catch(() => setIterationStats(new Map()));
  }, [session?.key, conversationId, turns.length]);

  const checkScrollPosition = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const threshold = 100
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    setShowScrollDown(!isAtBottom)
  }, [])

  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const onScroll = () => {
      if (scrollRafRef.current != null) return
      scrollRafRef.current = window.requestAnimationFrame(() => {
        scrollRafRef.current = null
        checkScrollPosition()
      })
    }
    const resizeObserver = new ResizeObserver(checkScrollPosition)
    el.addEventListener('scroll', onScroll, { passive: true })
    resizeObserver.observe(el)
    return () => {
      el.removeEventListener('scroll', onScroll)
      resizeObserver.disconnect()
      if (scrollRafRef.current != null) {
        window.cancelAnimationFrame(scrollRafRef.current)
        scrollRafRef.current = null
      }
    }
  }, [checkScrollPosition])

  useEffect(() => {
    if (loading) return
    if (isInitialScroll.current && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'instant' })
      isInitialScroll.current = false
    } else {
      checkScrollPosition()
    }
  }, [loading, turns, checkScrollPosition])

  // Auto-scroll when streaming new content (if user was near bottom)
  useEffect(() => {
    if (!inFlightTurn) return
    const el = scrollContainerRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
    }
  }, [
    inFlightTurn?.draftAssistant,
    inFlightTurn?.thinkingContent,
    inFlightTurn?.entries.length,
    inFlightTurn,
  ])

  useEffect(() => {
    isInitialScroll.current = true
  }, [session?.key, conversationId])

  const taskLocatedRef = useRef<string | null>(null)

  // Deep-link: scroll to targetTraceId, targetTaskId, or targetTurnSeq after messages render.
  // Retries on each turns update so task result cards appearing later also get located.
  useEffect(() => {
    if (loading) return
    if (!targetTraceId && !targetTaskId && targetTurnSeq == null) return

    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer) return

    if (targetTraceId) {
      const el = scrollContainer.querySelector(`[data-trace-id="${CSS.escape(targetTraceId)}"]`)
      if (el && taskLocatedRef.current !== `trace:${targetTraceId}`) {
        taskLocatedRef.current = `trace:${targetTraceId}`
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        return
      }
    }

    if (targetTaskId) {
      const el = scrollContainer.querySelector(`[data-bg-task-id="${CSS.escape(targetTaskId)}"]`)
      if (el) {
        if (taskLocatedRef.current !== targetTaskId) {
          taskLocatedRef.current = targetTaskId
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        return
      }
    }

    if (targetTurnSeq != null && taskLocatedRef.current !== `task:${targetTaskId}`) {
      const el = scrollContainer.querySelector(`[data-turn-seq="${targetTurnSeq}"]`)
      if (el && taskLocatedRef.current !== `turn:${targetTurnSeq}`) {
        taskLocatedRef.current = `turn:${targetTurnSeq}`
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
  }, [loading, turns, targetTraceId, targetTaskId, targetTurnSeq])

  const scrollToBottom = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    setShowScrollDown(false)
  }, [])

  const { taskItemsByTurn, unanchoredTaskItems, suppressedTaskIds } = useMemo(() => {
    const byTurn = new Map<number, DirectTaskMessage[]>()
    const unanchored: DirectTaskMessage[] = []
    const ids = new Set<string>()
    for (const task of directTasks) {
      ids.add(task.task_id)
      if (typeof task.origin_turn_seq === 'number') {
        byTurn.set(task.origin_turn_seq, [...(byTurn.get(task.origin_turn_seq) || []), task])
      } else {
        unanchored.push(task)
      }
    }
    return {
      taskItemsByTurn: new Map(Array.from(byTurn.entries()).map(([turnSeq, tasks]) => [turnSeq, buildTaskTimelineItems(tasks)])),
      unanchoredTaskItems: buildTaskTimelineItems(unanchored),
      suppressedTaskIds: ids,
    }
  }, [directTasks])

  const renderTaskTimelineItems = useCallback((items: TaskTimelineItem[]) => (
    items.map((item) => {
      if (item.kind === 'chain') {
        return <ChainBubble key={`chain-${item.chainId}`} chainId={item.chainId} tasks={item.tasks} />
      }
      return <TaskStatusCard key={`task-${item.task.task_id}`} task={item.task} />
    })
  ), [])

  if (!session) {
    return (
      <div className="flex-1 min-w-0 flex items-center justify-center text-[var(--text-secondary)] bg-[var(--bg-primary)]">
        <div className="text-center">
          <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>Select a session to view</p>
        </div>
      </div>
    )
  }

  let headerTotalTokens = session.token_stats.total_tokens
  let headerLlmCalls = session.token_stats.llm_calls
  const visibleTurns = isConsole
    && inFlightTurn?.transport === 'console'
    && typeof inFlightTurn.turnSeq === 'number'
    ? turns.filter((turn) => turn.turnSeq !== inFlightTurn.turnSeq)
    : turns
  const hasVisibleStreamingOutput = Boolean(
    inFlightTurn?.draftAssistant
    || inFlightTurn?.thinkingContent
    || inFlightTurn?.entries.length,
  )
  if (turnTokenStats.size > 0) {
    headerTotalTokens = 0
    headerLlmCalls = 0
    for (const stats of turnTokenStats.values()) {
      headerTotalTokens += stats.total_tokens
      headerLlmCalls += stats.llm_calls
    }
  }

  return (
    <div className="flex min-h-0 flex-1 min-w-0 flex-col bg-[var(--bg-primary)] relative">
      <ChatHeader
        session={session}
        conversation={conversation}
        conversationId={conversationId}
        turns={turns}
        isReadOnly={!!isReadOnly}
        isMobile={isMobile}
        transportStatus={transportStatus}
        activeTransport={activeTransport}
        headerTotalTokens={headerTotalTokens}
        headerLlmCalls={headerLlmCalls}
        onRefresh={onRefresh}
        onToggleSessionPanel={onToggleSessionPanel}
        onParticipantsChange={onParticipantsChange}
      />

      {/* Messages */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 space-y-4 relative" ref={scrollContainerRef}>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-[var(--accent)]" />
          </div>
        ) : (
          <>
            {visibleTurns.map((turn, i) => (
              <div key={turn.turnSeq != null ? `turn-${turn.turnSeq}` : `turn-synthetic-${i}`} className="space-y-3">
                <TurnGroupComponent
                  turn={turn}
                  index={i}
                  tokenStats={turn.turnSeq != null ? turnTokenStats.get(turn.turnSeq) : undefined}
                  iterationStats={iterationStats}
                  sessionKey={session?.key}
                  suppressLoadingIndicator={isConsole && i === visibleTurns.length - 1 && hasVisibleStreamingOutput}
                  targetTaskId={targetTaskId}
                  targetTurnSeq={targetTurnSeq}
                  targetTraceId={targetTraceId}
                  suppressedTaskIds={suppressedTaskIds}
                />
                {turn.turnSeq != null && renderTaskTimelineItems(taskItemsByTurn.get(turn.turnSeq) || [])}
              </div>
            ))}
            {inFlightTurn && (
              <InFlightTurnBlock turn={inFlightTurn} />
            )}
            {renderTaskTimelineItems(unanchoredTaskItems)}
          </>
        )}
        {showScrollDown && (
          <div className="sticky bottom-3 z-10 flex justify-center pointer-events-none">
            <button
              onClick={scrollToBottom}
              className="pointer-events-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] shadow-lg shadow-black/20 hover:border-[var(--accent)] hover:text-[var(--accent)]"
              title="Scroll to bottom"
              aria-label="Scroll to bottom"
            >
              <ArrowDownToLine className="h-4 w-4" />
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <HudBar
        session={session}
        directTasks={directTasks}
        activeTransport={activeTransport}
        isReadOnly={!!isReadOnly}
        onSkillSelect={handleSkillSelect}
      />

      {isConsole && !isReadOnly && (
        <ChatInput
          onSend={onSend}
          onStopCurrentTurn={onStopCurrentTurn}
          onSubmitDirectTask={onSubmitDirectTask}
          sendDisabled={sendDisabled}
          isMobile={isMobile}
        />
      )}
    </div>
  );
}
