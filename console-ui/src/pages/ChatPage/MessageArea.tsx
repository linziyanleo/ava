import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare, Loader2, RefreshCw, Copy, Check, ArrowDown, Search, Menu, ExternalLink, FileText } from 'lucide-react'
import type { ChatComposePayload, SessionMeta, ConversationMeta, TurnGroup, TurnTokenStats, IterationTokenStats, ChatStreamStatus, ActiveChatTransport } from './types';
import { SCENE_LABELS } from './types'
import { ConnectionBadge } from './ConnectionBadge'
import { TurnGroupComponent } from './TurnGroup'
import { ChatInput } from './ChatInput'
import { SearchModal } from './SearchModal'
import { ContextInspector } from './ContextInspector'
import { InFlightTurnBlock } from './InFlightTurnBlock'
import type { InFlightTurn } from './inFlightTurn'
import { formatTokenCount } from './utils'
import { api } from '../../api/client';

interface MessageAreaProps {
  session: SessionMeta | null
  conversation: ConversationMeta | null
  conversationId: string | null
  turns: TurnGroup[]
  inFlightTurn: InFlightTurn | null
  loading: boolean
  isConsole: boolean
  isReadOnly?: boolean
  transportStatus: ChatStreamStatus
  activeTransport: ActiveChatTransport
  sendDisabled: boolean
  onSend: (payload: ChatComposePayload) => Promise<void> | void
  onRefresh: () => void
  isMobile?: boolean
  onToggleSessionPanel?: () => void
}

export function MessageArea({ session, conversation, conversationId, turns, inFlightTurn, loading, isConsole, isReadOnly, transportStatus, activeTransport, sendDisabled, onSend, onRefresh, isMobile, onToggleSessionPanel }: MessageAreaProps) {
  const navigate = useNavigate()
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isInitialScroll = useRef(true)
  const [turnTokenStats, setTurnTokenStats] = useState<Map<number, TurnTokenStats>>(new Map());
  const [iterationStats, setIterationStats] = useState<Map<string, IterationTokenStats>>(new Map());
  const [refreshing, setRefreshing] = useState(false)
  const [keyCopied, setKeyCopied] = useState(false)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showInspector, setShowInspector] = useState(false)

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
    el.addEventListener('scroll', checkScrollPosition)
    return () => el.removeEventListener('scroll', checkScrollPosition)
  }, [checkScrollPosition])

  useEffect(() => {
    if (isInitialScroll.current && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'instant' })
      isInitialScroll.current = false
    } else {
      checkScrollPosition()
    }
  }, [turns, checkScrollPosition])

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
  }, [session?.key])

  useEffect(() => {
    setShowInspector(false)
  }, [session?.key, conversationId])

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

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
            <span className="truncate">{session.key}</span>
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
            <span className="text-[10px] text-[var(--text-secondary)]">
              {SCENE_LABELS[session.scene]}
            </span>
            {conversation && (
              <span className="text-[10px] text-[var(--text-secondary)] opacity-70">
                {conversation.is_legacy ? 'Legacy' : conversation.conversation_id}
              </span>
            )}
            <button
              onClick={() => {
                const params = new URLSearchParams({ session_key: session.key })
                if (conversationId) params.set('conversation_id', conversationId)
                navigate(`/tokens?${params.toString()}`)
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
              <TurnGroupComponent
                key={turn.turnSeq != null ? `turn-${turn.turnSeq}` : `turn-synthetic-${i}`}
                turn={turn}
                index={i}
                tokenStats={turn.turnSeq != null ? turnTokenStats.get(turn.turnSeq) : undefined}
                iterationStats={iterationStats}
                sessionKey={session?.key}
                suppressLoadingIndicator={isConsole && i === visibleTurns.length - 1 && hasVisibleStreamingOutput}
              />
            ))}
            {inFlightTurn && (
              <InFlightTurnBlock turn={inFlightTurn} />
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Scroll to bottom floating button */}
      {showScrollDown && (
        <div className={`absolute z-10 ${isMobile ? 'bottom-16 right-4' : 'bottom-20 right-8'}`}>
          <button
            onClick={scrollToBottom}
            className="p-2.5 rounded-full bg-[var(--accent)] text-white shadow-lg hover:bg-[var(--accent-hover)] transition-colors"
            title="Scroll to bottom"
          >
            <ArrowDown className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Input (console only) */}
      {isConsole && !isReadOnly && (
        <ChatInput
          onSend={onSend}
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
        disabled={!!isReadOnly}
        onClose={() => setShowInspector(false)}
      />
    </div>
  );
}
