import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare, Loader2, RefreshCw, Copy, Check, ArrowDownToLine, Search, Menu, ExternalLink, FileText } from 'lucide-react'
import type { ChatComposePayload, DirectTaskMessage, DirectTaskSubmitParams, SessionMeta, ConversationMeta, TurnGroup, TurnTokenStats, IterationTokenStats, ChatStreamStatus, ActiveChatTransport } from './types';
import { SCENE_LABELS } from './types'
import { ConnectionBadge } from './ConnectionBadge'
import { TurnGroupComponent } from './TurnGroup'
import { ChatInput } from './ChatInput'
import { SearchModal } from './SearchModal'
import { ContextInspector } from './ContextInspector'
import { InFlightTurnBlock } from './InFlightTurnBlock'
import { TaskStatusCard } from './TaskStatusCard'
import { ChainBubble } from './ChainBubble'
import { HudBar } from './HudBar'
import type { InFlightTurn } from './inFlightTurn'
import { formatTokenCount, getAgentInitial, getAgentLabel, getSessionParticipants, getSessionTitle } from './utils'
import { api } from '../../api/client';
import { buildTokenStatsNavUrl } from '../../lib/tokenStatsNav'

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
  targetTaskId?: string | null
  targetTurnSeq?: number | null
  targetTraceId?: string | null
}

export function MessageArea({ session, conversation, conversationId, turns, inFlightTurn, directTasks, loading, isConsole, isReadOnly, transportStatus, activeTransport, sendDisabled, onSend, onStopCurrentTurn, onSubmitDirectTask, onRefresh, isMobile, onToggleSessionPanel, targetTaskId, targetTurnSeq, targetTraceId }: MessageAreaProps) {
  const navigate = useNavigate()
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isInitialScroll = useRef(true)
  const scrollRafRef = useRef<number | null>(null)
  const [turnTokenStats, setTurnTokenStats] = useState<Map<number, TurnTokenStats>>(new Map());
  const [iterationStats, setIterationStats] = useState<Map<string, IterationTokenStats>>(new Map());
  const [refreshing, setRefreshing] = useState(false)
  const [keyCopied, setKeyCopied] = useState(false)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showInspector, setShowInspector] = useState(false)

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

  useEffect(() => {
    setShowInspector(false)
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
  const headerParticipants = getSessionParticipants(session)
  const headerParticipantLabels = headerParticipants.map(getAgentLabel).filter(Boolean)
  const headerTitle = getSessionTitle(session)
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
    <div className="flex-1 min-w-0 flex flex-col bg-[var(--bg-primary)] relative">
      {/* Session header */}
      <div className="px-4 py-2.5 border-b border-[var(--border)] flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-[var(--text-primary)] flex items-center gap-1.5">
            {isMobile && onToggleSessionPanel && (
              <button
                onClick={onToggleSessionPanel}
                className="p-1 -ml-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                title="会话列表"
              >
                <Menu className="w-4 h-4" />
              </button>
            )}
            <span className="truncate">{headerTitle}</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(session.key)
                setKeyCopied(true)
                setTimeout(() => setKeyCopied(false), 1500)
              }}
              className="p-0.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
              title="Copy session key"
            >
              {keyCopied ? <Check className="w-3 h-3 text-[var(--success)]" /> : <Copy className="w-3 h-3" />}
            </button>
          </h3>
          <div className="flex items-center gap-2 mt-0.5">
            <div className="flex shrink-0 -space-x-1">
              {headerParticipants.slice(0, 4).map((agentId) => (
                <span
                  key={agentId}
                  title={getAgentLabel(agentId)}
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[var(--bg-primary)] bg-[var(--bg-tertiary)] text-[8px] font-semibold text-[var(--text-secondary)]"
                >
                  {getAgentInitial(agentId)}
                </span>
              ))}
            </div>
            <span className="max-w-[220px] truncate text-[10px] text-[var(--text-secondary)]">
              {headerParticipantLabels.join(' / ')}
            </span>
            <span className="text-[10px] text-[var(--text-secondary)]">
              {SCENE_LABELS[session.scene]}
            </span>
            {conversation && (
              <span className="text-[10px] text-[var(--text-secondary)] opacity-70">
                {conversation.is_legacy ? 'Legacy thread' : conversation.is_active ? 'Active thread' : 'Archived thread'}
              </span>
            )}
            <button
              onClick={() => {
                navigate(buildTokenStatsNavUrl({
                  sessionKey: session.key,
                  conversationId,
                }))
              }}
              className="inline-flex items-center gap-1 text-xs text-[var(--text-secondary)] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] hover:text-[var(--accent)] transition-colors"
              title="查看当前会话的 Token 统计"
            >
              <span>⚡ {formatTokenCount(headerTotalTokens)} tokens · {headerLlmCalls} calls</span>
              <ExternalLink className="w-3 h-3" />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <ConnectionBadge transport={activeTransport} status={transportStatus} />
          {(isReadOnly || !isConsole) && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
              {conversation && isReadOnly ? 'History · Read-only' : 'Read-only'}
            </span>
          )}
          <button
            onClick={() => {
              setRefreshing(true)
              onRefresh()
              setTimeout(() => setRefreshing(false), 1000)
            }}
            className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setShowSearch(true)}
            className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            title="Search"
          >
            <Search className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setShowInspector(true)}
            disabled={!session?.key || isReadOnly}
            className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            title={isReadOnly ? '只对当前活跃会话开放 Context Inspector' : 'Context Inspector'}
          >
            <FileText className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

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

      {/* Input (console only) */}
      {isConsole && !isReadOnly && (
        <ChatInput
          onSend={onSend}
          onStopCurrentTurn={onStopCurrentTurn}
          onSubmitDirectTask={onSubmitDirectTask}
          sendDisabled={sendDisabled}
          isMobile={isMobile}
        />
      )}

      {/* Search modal */}
      {showSearch && (
        <SearchModal turns={turns} onClose={() => setShowSearch(false)} />
      )}

      <ContextInspector
        open={showInspector}
        sessionKey={session?.key || null}
        sessionLabel={session ? headerTitle : ''}
        disabled={!!isReadOnly}
        onClose={() => setShowInspector(false)}
      />
    </div>
  );
}
