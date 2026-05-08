import { useEffect, useMemo, useRef, useState, useCallback, type TouchEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, wsUrl } from '../../api/client'
import { useAuth } from '../../stores/auth'
import { useResponsiveMode } from '../../hooks/useResponsiveMode'
import type { ChatComposePayload, ChatFileUpload, DirectTaskMessage, DirectTaskStatus, DirectTaskSubmitParams, DirectTaskType, SceneType, SessionMeta, ConversationMeta, RawMessage, TurnGroup, ChatStreamStatus, ActiveChatTransport } from './types'
import { getNextTurnSeq, groupTurns } from './utils'
import {
  appendInFlightAssistantChunk,
  appendInFlightThinking,
  appendInFlightToolHint,
  applyInFlightStreamEnd,
  createInFlightTurn,
  markInFlightProcessing,
  upsertInFlightTurn,
  type InFlightTurn,
} from './inFlightTurn'
import { SessionSidebar } from './SessionSidebar'
import { MessageArea } from './MessageArea'
import { ConversationConfigBar } from './ConversationConfigBar'
import { TaskPreviewBar } from '../../components/tasks/TaskPreviewBar'
import { TaskOverlay } from './TaskOverlay'

const SESSION_LIST_POLL_MS = 30_000
const DIRECT_TASK_POLL_MS = 2_000
const MAX_RECONNECT_DELAY_MS = 15_000
const SEND_WATCHDOG_MS = 120_000
const FINAL_DIRECT_TASK_STATUSES = new Set<DirectTaskStatus>(['succeeded', 'failed', 'cancelled', 'interrupted', 'skipped'])
const AGENT_MENTION_RE = /(?:^|\s)@(nanobot|codex|claude_code|claude-code|image_gen|image-gen)(?=\s|$)/gi

function extractAgentMentions(text: string): string[] {
  const ids: string[] = []
  for (const match of text.matchAll(AGENT_MENTION_RE)) {
    const id = match[1].replace('-', '_').toLowerCase()
    if (!ids.includes(id)) {
      ids.push(id)
    }
  }
  return ids
}

interface DirectTaskSubmitResponse {
  task_id: string
  status: DirectTaskStatus
  task_type: DirectTaskType
  origin_conversation_id?: string
  origin_turn_seq?: number | null
  trace_id?: string
}

interface BackgroundTaskListItem {
  task_id: string
  task_type: DirectTaskType | string
  origin_session_key: string
  status: DirectTaskStatus
  prompt_preview: string
  started_at: number | null
  elapsed_ms: number
  result_preview?: string
  error_message?: string
  origin_conversation_id?: string
  origin_turn_seq?: number | null
  trace_id?: string
  chain_id?: string
  parent_task_ids?: string[]
  node_kind?: string
  skill_name?: string
  matched_by?: 'natural_language' | 'explicit'
}

function sortDirectTasks(tasks: DirectTaskMessage[]) {
  return [...tasks].sort((a, b) => {
    const sessionDelta = a.session_key.localeCompare(b.session_key)
    if (sessionDelta !== 0) return sessionDelta
    const turnDelta = (a.origin_turn_seq ?? Number.MAX_SAFE_INTEGER) - (b.origin_turn_seq ?? Number.MAX_SAFE_INTEGER)
    if (turnDelta !== 0) return turnDelta
    const startedDelta = (a.started_at ?? Number.MAX_SAFE_INTEGER) - (b.started_at ?? Number.MAX_SAFE_INTEGER)
    if (startedDelta !== 0) return startedDelta
    return a.task_id.localeCompare(b.task_id)
  })
}

function upsertDirectTask(prev: DirectTaskMessage[], task: DirectTaskMessage) {
  return sortDirectTasks([task, ...prev.filter((item) => item.task_id !== task.task_id)]).slice(0, 100)
}

interface BackgroundTaskListResponse {
  tasks: BackgroundTaskListItem[]
}

function getReconnectDelay(attempt: number): number {
  return Math.min(500 * 2 ** attempt, MAX_RECONNECT_DELAY_MS)
}

function disposeSocket(socket: WebSocket | null, onDispose?: () => void) {
  if (!socket) {
    onDispose?.()
    return
  }
  socket.onopen = null
  socket.onmessage = null
  socket.onerror = null
  socket.onclose = null
  socket.close()
  onDispose?.()
}

export default function ChatPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const deepLinkSessionKey = searchParams.get('session_key') || searchParams.get('session_id') || null
  const deepLinkConversationId = searchParams.get('conversation_id') || null
  const deepLinkTaskId = searchParams.get('task_id') || null
  const deepLinkChainId = searchParams.get('chain_id') || null
  const view = searchParams.get('view') || null
  const taskView = searchParams.get('task_view') || null
  const deepLinkTraceId = searchParams.get('trace_id') || null
  const deepLinkTurnSeq = useMemo(() => {
    const raw = searchParams.get('turn_seq')
    if (raw == null) return null
    const n = parseInt(raw, 10)
    return Number.isFinite(n) ? n : null
  }, [searchParams])

  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [conversationLists, setConversationLists] = useState<Record<string, ConversationMeta[]>>({})
  const [activeScene, setActiveScene] = useState<SceneType>('console')
  const [activeSession, setActiveSession] = useState('')
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [currentMeta, setCurrentMeta] = useState<SessionMeta | null>(null)
  const [turns, setTurns] = useState<TurnGroup[]>([])
  const [inFlightTurn, setInFlightTurn] = useState<InFlightTurn | null>(null)
  const [directTasks, setDirectTasks] = useState<DirectTaskMessage[]>([])
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [transportStatus, setTransportStatus] = useState<ChatStreamStatus>('idle')
  const [activeTransport, setActiveTransport] = useState<ActiveChatTransport>('none')
  const [mobileSessionOpen, setMobileSessionOpen] = useState(false)
  const [error, setError] = useState('')
  const [deepLinkNotice, setDeepLinkNotice] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const wsReconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wsReconnectAttempts = useRef(0)
  const wsSessionId = useRef<string>('')
  const sendWatchdogTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const observeWsRef = useRef<WebSocket | null>(null)
  const observeReconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const observeReconnectAttempts = useRef(0)
  const observeSessionKey = useRef<string>('')
  const initializedRef = useRef(false)
  const mobileSessionSwipeStart = useRef<{ x: number; y: number } | null>(null)
  const { isMobile } = useResponsiveMode()
  const { isMockTester, canEdit } = useAuth()
  const mockMode = isMockTester()
  const canMutateChat = canEdit()
  const activeTransportRef = useRef<ActiveChatTransport>(activeTransport)
  activeTransportRef.current = activeTransport
  const consoleBusyRef = useRef(false)
  consoleBusyRef.current = sending || inFlightTurn?.transport === 'console'

  const clearSendWatchdog = useCallback(() => {
    if (sendWatchdogTimer.current) {
      clearTimeout(sendWatchdogTimer.current)
      sendWatchdogTimer.current = null
    }
  }, [])

  const clearConsoleInFlight = useCallback(() => {
    clearSendWatchdog()
    setSending(false)
    setInFlightTurn(null)
  }, [clearSendWatchdog])

  const finalizeConsoleInFlight = useCallback(() => {
    clearSendWatchdog()
    setSending(false)
    setInFlightTurn((prev) => {
      if (prev?.transport === 'console') {
        setTurns((currentTurns) => upsertInFlightTurn(currentTurns, prev))
      }
      return null
    })
  }, [clearSendWatchdog])

  const armSendWatchdog = useCallback(() => {
    clearSendWatchdog()
    sendWatchdogTimer.current = setTimeout(() => {
      if (!consoleBusyRef.current) return
      clearConsoleInFlight()
      setTransportStatus('error')
      setError('响应超时，请检查连接后重试')
    }, SEND_WATCHDOG_MS)
  }, [clearConsoleInFlight, clearSendWatchdog])

  const loadConversations = useCallback(async (sessionKey: string) => {
    try {
      const conversations = await api<ConversationMeta[]>(`/chat/conversations?session_key=${encodeURIComponent(sessionKey)}`)
      setConversationLists((prev) => ({ ...prev, [sessionKey]: conversations }))
      return conversations
    } catch (err) {
      console.error('Failed to load conversations:', err)
      setConversationLists((prev) => ({ ...prev, [sessionKey]: [] }))
      return [] as ConversationMeta[]
    }
  }, [])

  const pickConversationId = useCallback((
    meta: SessionMeta | null,
    conversations: ConversationMeta[],
    preferredConversationId?: string | null,
  ) => {
    if (preferredConversationId !== undefined && preferredConversationId !== null) {
      if (conversations.some((item) => item.conversation_id === preferredConversationId)) {
        return preferredConversationId
      }
    }
    if (meta && conversations.some((item) => item.conversation_id === meta.conversation_id)) {
      return meta.conversation_id
    }
    if (conversations.length > 0) {
      return conversations[0].conversation_id
    }
    return meta?.conversation_id ?? null
  }, [])

  const loadSessionMessagesWithMeta = useCallback(async (
    sessionKey: string,
    meta: SessionMeta | null,
    conversationId: string | null,
    silent = false,
  ) => {
    if (!silent) setLoadingMessages(true)
    try {
      const conversationQuery = conversationId !== null
        ? `&conversation_id=${encodeURIComponent(conversationId)}`
        : ''
      const messages = await api<RawMessage[]>(`/chat/messages?session_key=${encodeURIComponent(sessionKey)}${conversationQuery}`)
      setCurrentMeta(meta)
      setActiveConversationId(conversationId)
      setTurns(groupTurns(messages))
    } catch (err) {
      console.error('Failed to load messages:', err)
      if (!silent) setTurns([])
    } finally {
      if (!silent) setLoadingMessages(false)
    }
  }, [])

  const loadSessionMessages = useCallback(async (
    sessionKey: string,
    conversationId: string | null = null,
    silent = false,
  ) => {
    const meta = sessions.find((s) => s.key === sessionKey) || null
    return loadSessionMessagesWithMeta(sessionKey, meta, conversationId, silent)
  }, [sessions, loadSessionMessagesWithMeta])

  const activeConversationIdRef = useRef<string | null>(activeConversationId)
  activeConversationIdRef.current = activeConversationId
  const turnsRef = useRef(turns)
  turnsRef.current = turns
  const directTasksRef = useRef(directTasks)
  directTasksRef.current = directTasks
  const refreshedDirectTaskIdsRef = useRef<Set<string>>(new Set())

  const refreshSessionView = useCallback(async (
    sessionKey: string,
    opts?: {
      preferredConversationId?: string | null
      forceActiveConversation?: boolean
      silent?: boolean
    },
  ) => {
    const metas = await loadSessionListRef.current()
    const meta = metas.find((m) => m.key === sessionKey) || null
    const conversations = await loadConversationsRef.current(sessionKey)
    const preferredConversationId = opts?.forceActiveConversation
      ? meta?.conversation_id ?? null
      : opts?.preferredConversationId
    const nextConversationId = pickConversationId(meta, conversations, preferredConversationId)
    await loadSessionMessagesWithMetaRef.current(
      sessionKey,
      meta,
      nextConversationId,
      opts?.silent ?? false,
    )
  }, [pickConversationId])

  const disconnectConsoleWs = useCallback((nextStatus: ChatStreamStatus = 'idle') => {
    if (wsReconnectTimer.current) {
      clearTimeout(wsReconnectTimer.current)
      wsReconnectTimer.current = null
    }
    wsReconnectAttempts.current = 0
    const socket = wsRef.current
    wsRef.current = null
    wsSessionId.current = ''
    disposeSocket(socket)
    clearConsoleInFlight()
    if (activeTransportRef.current === 'console') {
      setActiveTransport('none')
      setTransportStatus(nextStatus)
    }
  }, [clearConsoleInFlight])

  const connectWs = useCallback((sid: string, isReconnect = false) => {
    if (wsReconnectTimer.current) {
      clearTimeout(wsReconnectTimer.current)
      wsReconnectTimer.current = null
    }
    disposeSocket(wsRef.current)
    wsRef.current = null
    wsSessionId.current = sid
    const sessionKey = `console:${sid}`
    setActiveTransport('console')
    setTransportStatus(isReconnect ? 'reconnecting' : 'connecting')
    const ws = new WebSocket(wsUrl(`/chat/ws/${sid}`))
    const wsStartedAt = Date.now()
    ws.onopen = () => {
      if (wsRef.current !== ws) return
      wsReconnectAttempts.current = 0
      setTransportStatus('open')
    }
    ws.onmessage = (e) => {
      if (wsRef.current !== ws) return
      const data = JSON.parse(e.data)
      if (data.type === 'thinking') {
        armSendWatchdog()
        setInFlightTurn((prev) => (prev ? appendInFlightThinking(prev, data.content) : prev))
      } else if (data.type === 'progress') {
        armSendWatchdog()
        if (data.tool_hint) {
          setInFlightTurn((prev) => (prev ? appendInFlightToolHint(prev, data.content) : prev))
        } else {
          setInFlightTurn((prev) => (prev ? appendInFlightAssistantChunk(prev, data.content) : prev))
        }
      } else if (data.type === 'stream_end') {
        setInFlightTurn((prev) => (prev ? applyInFlightStreamEnd(prev, !!data.resuming) : prev))
      } else if (data.type === 'direct_task' && data.task) {
        const task = data.task as DirectTaskMessage
        setDirectTasks((prev) => upsertDirectTask(prev, task))
      } else if (data.type === 'complete') {
        finalizeConsoleInFlight()
        void refreshSessionViewRef.current(sessionKey, {
          forceActiveConversation: true,
          silent: true,
        })
      } else if (data.type === 'async_result') {
        void refreshSessionViewRef.current(sessionKey, {
          preferredConversationId: activeConversationIdRef.current,
          silent: true,
        })
      }
    }
    ws.onerror = (event) => {
      if (wsRef.current !== ws) return
      console.warn('[chat-ws] console socket error', {
        sessionKey,
        sid,
        isReconnect,
        lifetimeMs: Date.now() - wsStartedAt,
        readyState: ws.readyState,
        eventType: event.type,
      })
      setTransportStatus('error')
    }
    ws.onclose = (event) => {
      if (wsRef.current !== ws) return
      console.warn('[chat-ws] console socket closed', {
        sessionKey,
        sid,
        isReconnect,
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
        lifetimeMs: Date.now() - wsStartedAt,
        readyState: ws.readyState,
      })
      wsRef.current = null
      // Reload messages on disconnect — the LLM may have finished while ws was down.
      loadSessionMessagesRef.current(sessionKey, activeConversationIdRef.current, true)
      // Auto-reconnect if this is still the active session
      if (wsSessionId.current === sid) {
        setTransportStatus('reconnecting')
        const delay = getReconnectDelay(wsReconnectAttempts.current)
        wsReconnectAttempts.current += 1
        wsReconnectTimer.current = setTimeout(() => connectWs(sid, true), delay)
      }
    }
    wsRef.current = ws
    // If reconnecting after a drop, reload messages to catch anything missed.
    if (isReconnect) {
      loadSessionMessagesRef.current(sessionKey, activeConversationIdRef.current, true)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [armSendWatchdog, finalizeConsoleInFlight, clearConsoleInFlight])

  const disconnectObserveWs = useCallback((nextStatus: ChatStreamStatus = 'idle') => {
    if (observeReconnectTimer.current) {
      clearTimeout(observeReconnectTimer.current)
      observeReconnectTimer.current = null
    }
    observeReconnectAttempts.current = 0
    const socket = observeWsRef.current
    observeWsRef.current = null
    observeSessionKey.current = ''
    disposeSocket(socket)
    setInFlightTurn((prev) => (prev?.transport === 'observe' ? null : prev))
    if (activeTransportRef.current === 'observe') {
      setActiveTransport('none')
      setTransportStatus(nextStatus)
    }
  }, [])

  const connectObserveWs = useCallback((sessionKey: string, isReconnect = false) => {
    disconnectObserveWs(isReconnect ? 'reconnecting' : 'idle')
    observeSessionKey.current = sessionKey
    setActiveTransport('observe')
    setTransportStatus(isReconnect ? 'reconnecting' : 'connecting')
    const ws = new WebSocket(wsUrl(`/chat/ws/observe/${encodeURIComponent(sessionKey)}`))

    ws.onopen = () => {
      if (observeWsRef.current !== ws) return
      observeReconnectAttempts.current = 0
      setTransportStatus('open')
      loadSessionMessagesRef.current(sessionKey, activeConversationIdRef.current, true)
    }

    ws.onmessage = (e) => {
      if (observeWsRef.current !== ws) return
      const data = JSON.parse(e.data)
      if (data.type === 'message_arrived') {
        const eventConversationId = typeof data.conversation_id === 'string' ? data.conversation_id : ''
        if (
          eventConversationId
          && activeConversationIdRef.current
          && activeConversationIdRef.current !== eventConversationId
        ) {
          return
        }
        setInFlightTurn((prev) => {
          if (
            prev?.transport === 'observe'
            && typeof data.turn_seq === 'number'
            && prev.turnSeq === data.turn_seq
          ) {
            return markInFlightProcessing(prev, true)
          }
          return createInFlightTurn({
            transport: 'observe',
            turnSeq: typeof data.turn_seq === 'number' ? data.turn_seq : getNextTurnSeq(turnsRef.current),
            conversationId: eventConversationId || activeConversationIdRef.current,
            userMessage: {
              role: 'user',
              content: data.content ?? '',
              timestamp: data.timestamp,
              metadata: { conversation_id: eventConversationId || '' },
            },
          })
        })
      } else if (data.type === 'processing_started') {
        const eventConversationId = typeof data.conversation_id === 'string' ? data.conversation_id : ''
        if (
          !eventConversationId
          || !activeConversationIdRef.current
          || activeConversationIdRef.current === eventConversationId
        ) {
          setInFlightTurn((prev) => (prev?.transport === 'observe' ? markInFlightProcessing(prev, true) : prev))
        }
      } else if (data.type === 'conversation_rotated') {
        setInFlightTurn((prev) => (prev?.transport === 'observe' ? null : prev))
        void refreshSessionViewRef.current(sessionKey, {
          preferredConversationId: data.new_conversation_id ?? null,
          silent: true,
        })
      } else if (data.type === 'turn_completed') {
        const eventConversationId = typeof data.conversation_id === 'string' ? data.conversation_id : ''
        if (
          eventConversationId
          && activeConversationIdRef.current
          && activeConversationIdRef.current !== eventConversationId
        ) {
          return
        }
        setInFlightTurn((prev) => (prev?.transport === 'observe' ? null : prev))
        void refreshSessionViewRef.current(sessionKey, {
          preferredConversationId: activeConversationIdRef.current,
          silent: true,
        })
      }
    }

    ws.onerror = () => {
      if (observeWsRef.current !== ws) return
      setTransportStatus('error')
    }

    ws.onclose = () => {
      if (observeWsRef.current !== ws) return
      observeWsRef.current = null
      if (observeSessionKey.current === sessionKey) {
        setTransportStatus('reconnecting')
        const delay = getReconnectDelay(observeReconnectAttempts.current)
        observeReconnectAttempts.current += 1
        observeReconnectTimer.current = setTimeout(() => connectObserveWs(sessionKey, true), delay)
      }
    }

    observeWsRef.current = ws
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disconnectObserveWs])

  const loadSessionList = useCallback(async () => {
    try {
      const data = await api<SessionMeta[]>('/chat/sessions')
      const metas: SessionMeta[] = data.map((s) => ({
        ...s,
        conversation_id: s.conversation_id || '',
        token_stats: s.token_stats || {
          total_prompt_tokens: 0,
          total_completion_tokens: 0,
          total_tokens: 0,
          llm_calls: 0,
        },
        message_count: s.message_count || 0,
      }))

      setSessions(metas)
      if (activeSession) {
        const activeMeta = metas.find((m) => m.key === activeSession) || null
        if (activeMeta) {
          setCurrentMeta(activeMeta)
        }
      }

      if (!initializedRef.current && metas.length > 0) {
        initializedRef.current = true

        const deepLinkSessionKeyVal = deepLinkSessionKeyRef.current
        const deepLinkConversationIdVal = deepLinkConversationIdRef.current
        const deepLinkTraceIdVal = deepLinkTraceIdRef.current
        const deepLinkTaskIdVal = deepLinkTaskIdRef.current
        let traceSessionKey: string | null = null
        let traceConversationId: string | null = null
        let taskSessionKey: string | null = null
        let taskConversationId: string | null = null
        let taskDeepLinkItem: BackgroundTaskListItem | null = null

        if (deepLinkTraceIdVal) {
          try {
            const traceMessages = await api<RawMessage[]>(
              `/chat/messages?trace_id=${encodeURIComponent(deepLinkTraceIdVal)}`,
            )
            const traceMeta = traceMessages.find((message) => {
              const sessionKey = message.metadata?.session_key
              const conversationId = message.metadata?.conversation_id
              return typeof sessionKey === 'string' && typeof conversationId === 'string'
            })?.metadata
            if (traceMeta) {
              traceSessionKey = traceMeta.session_key as string
              traceConversationId = traceMeta.conversation_id as string
            }
          } catch (err) {
            console.error('Failed to resolve trace deep link:', err)
          }
          if (!traceSessionKey) {
            setDeepLinkNotice(`未找到 trace_id=${deepLinkTraceIdVal} 对应的消息`)
          }
        }

        if (!traceSessionKey && deepLinkTaskIdVal) {
          try {
            const task = await api<BackgroundTaskListItem>(
              `/bg-tasks/${encodeURIComponent(deepLinkTaskIdVal)}`,
            )
            if (task.task_id && task.origin_session_key) {
              taskDeepLinkItem = task
              taskSessionKey = task.origin_session_key
              taskConversationId = task.origin_conversation_id || null
            } else {
              setDeepLinkNotice(`未找到 task_id=${deepLinkTaskIdVal} 对应的任务`)
            }
          } catch (err) {
            console.error('Failed to resolve task deep link:', err)
            setDeepLinkNotice(`未找到 task_id=${deepLinkTaskIdVal} 对应的任务`)
          }
        }

        const resolvedDeepLinkSessionKey = traceSessionKey || taskSessionKey || deepLinkSessionKeyVal
        const resolvedDeepLinkConversationId = traceConversationId || taskConversationId || deepLinkConversationIdVal

        let targetSession = resolvedDeepLinkSessionKey
          ? metas.find((m) => m.key === resolvedDeepLinkSessionKey) || null
          : null

        if (!targetSession) {
          targetSession = metas[0] || null
          if (targetSession) setActiveScene(targetSession.scene)
        } else {
          setActiveScene(targetSession.scene)
          if (resolvedDeepLinkConversationId == null) {
            setDeepLinkNotice('该任务缺少 conversation 绑定，已打开对应 session')
          }
        }

        if (targetSession) {
          setActiveSession(targetSession.key)
          if (taskDeepLinkItem) {
            const taskMessage: DirectTaskMessage = {
              type: 'direct_task',
              task_id: taskDeepLinkItem.task_id,
              task_type: taskDeepLinkItem.task_type as DirectTaskType,
              session_key: taskDeepLinkItem.origin_session_key,
              prompt_preview: taskDeepLinkItem.prompt_preview,
              status: taskDeepLinkItem.status,
              started_at: taskDeepLinkItem.started_at,
              elapsed_ms: taskDeepLinkItem.elapsed_ms,
              result_preview: taskDeepLinkItem.result_preview,
              error_message: taskDeepLinkItem.error_message,
              origin_conversation_id: taskDeepLinkItem.origin_conversation_id,
              origin_turn_seq: taskDeepLinkItem.origin_turn_seq,
              trace_id: taskDeepLinkItem.trace_id,
              chain_id: taskDeepLinkItem.chain_id,
              parent_task_ids: taskDeepLinkItem.parent_task_ids,
              node_kind: taskDeepLinkItem.node_kind,
            }
            setDirectTasks((prev) => upsertDirectTask(prev, taskMessage))
          }
          const sessionKey = targetSession.key
          void (async () => {
            const conversations = await loadConversationsRef.current(sessionKey)
            const preferredConvId = resolvedDeepLinkConversationId
              ?? targetSession!.conversation_id
            const conversationId = pickConversationId(targetSession, conversations, preferredConvId)
            await loadSessionMessagesWithMetaRef.current(sessionKey, targetSession, conversationId)
          })()
          if (targetSession.scene === 'console' && !mockMode) {
            const sid = targetSession.key.replace(/^console:/, '')
            connectWs(sid)
          }
        }
      }
      return metas
    } catch (err) {
      console.error('Failed to load sessions:', err)
      return []
    }
  }, [activeSession, connectWs, mockMode, pickConversationId])

  useEffect(() => {
    loadSessionList()
  }, [loadSessionList])

  // Session list polling (30s)
  useEffect(() => {
    const timer = setInterval(loadSessionList, SESSION_LIST_POLL_MS)
    return () => clearInterval(timer)
  }, [loadSessionList])

  // Observe WS for non-console sessions (replaces 10s polling)
  useEffect(() => {
    if (!activeSession || activeScene === 'console' || mockMode) {
      disconnectObserveWs()
      return
    }
    connectObserveWs(activeSession)
    return () => disconnectObserveWs()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSession, activeScene, disconnectObserveWs, connectObserveWs, mockMode])

  useEffect(() => {
    return () => {
      disconnectConsoleWs()
      disconnectObserveWs()
    }
  }, [disconnectConsoleWs, disconnectObserveWs])

  const handleSessionSelect = (key: string) => {
    setActiveSession(key)
    setActiveConversationId(null)
    setInFlightTurn(null)
    setSending(false)
    disconnectConsoleWs()
    disconnectObserveWs()
    setMobileSessionOpen(false)

    const meta = sessions.find((s) => s.key === key)
    setActiveScene(meta?.scene || 'console')
    void (async () => {
      const conversations = await loadConversationsRef.current(key)
      const conversationId = pickConversationId(meta || null, conversations, meta?.conversation_id ?? null)
      await loadSessionMessagesWithMetaRef.current(key, meta || null, conversationId)
    })()

    if (meta?.scene === 'console' && !mockMode) {
      const sid = key.replace(/^console:/, '')
      connectWs(sid)
    }
  }

  const handleConversationSelect = (sessionKey: string, conversationId: string) => {
    const meta = sessions.find((s) => s.key === sessionKey) || null
    setActiveSession(sessionKey)
    setActiveScene(meta?.scene || 'console')
    setMobileSessionOpen(false)
    setInFlightTurn(null)
    setSending(false)
    void loadSessionMessagesWithMeta(sessionKey, meta, conversationId)
  }

  const handleCreateConsole = async () => {
    setError('')
    try {
      const title = `Chat ${sessions.filter((s) => s.scene === 'console').length + 1}`
      const res = await api<{
        session_id: string
        title?: string
        conversation_id: string
        participants: string[]
        default_responder_agent_id: string
      }>('/chat/sessions', {
        method: 'POST',
        body: JSON.stringify({ title }),
      })

      const sid = res.session_id
      const newKey = `console:${sid}`

      setActiveScene('console')
      setActiveSession(newKey)
      setCurrentMeta({
        key: newKey,
        title: res.title || title,
        scene: 'console',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        conversation_id: res.conversation_id,
        participants: res.participants || ['nanobot'],
        default_responder_agent_id: res.default_responder_agent_id || 'nanobot',
        token_stats: { total_prompt_tokens: 0, total_completion_tokens: 0, total_tokens: 0, llm_calls: 0 },
        message_count: 0,
      })
      setConversationLists((prev) => ({
        ...prev,
        [newKey]: [{
          conversation_id: res.conversation_id,
          first_message_preview: '',
          message_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          is_active: true,
        }],
      }))
      setActiveConversationId(res.conversation_id)
      setTurns([])
      setInFlightTurn(null)
      setSending(false)
      disconnectObserveWs()
      if (!mockMode) {
        connectWs(sid)
      }

      loadSessionList()
    } catch (err: any) {
      const msg = err?.message || String(err)
      setError(msg)
      console.error('Failed to create session:', err)
    }
  }

  const handleParticipantsChange = useCallback(async (participants: string[]) => {
    if (!currentMeta?.key.startsWith('console:') || mockMode || !canMutateChat) return
    const sid = currentMeta.key.replace(/^console:/, '')
    const response = await api<{
      participants: string[]
      default_responder_agent_id: string
    }>(`/chat/sessions/${encodeURIComponent(sid)}`, {
      method: 'PATCH',
      body: JSON.stringify({ participants }),
    })
    setCurrentMeta((prev) => prev && prev.key === currentMeta.key
      ? {
          ...prev,
          participants: response.participants,
          default_responder_agent_id: response.default_responder_agent_id,
        }
      : prev)
    setSessions((prev) => prev.map((session) => session.key === currentMeta.key
      ? {
          ...session,
          participants: response.participants,
          default_responder_agent_id: response.default_responder_agent_id,
        }
      : session))
  }, [canMutateChat, currentMeta?.key, mockMode])

  const handleDeleteSession = async (key: string) => {
    const meta = sessions.find((s) => s.key === key)
    try {
      if (meta?.scene === 'console') {
        const sid = key.replace(/^console:/, '')
        await api(`/chat/sessions/${sid}`, { method: 'DELETE' })
      } else {
        // For non-console sessions, delete via DB (using key as session_id path)
        // The backend delete_session expects the session_id part after "console:"
        // For non-console, we need a different approach — use session key
        const safe = key.replace(/:/g, '_')
        await api('/files/delete', {
          method: 'DELETE',
          body: JSON.stringify({ path: `workspace/sessions/${safe}.jsonl` }),
        })
      }
      if (activeSession === key) {
        setActiveSession('')
        setCurrentMeta(null)
        setTurns([])
        setInFlightTurn(null)
        setSending(false)
        disconnectConsoleWs('closed')
        disconnectObserveWs('closed')
      }
      loadSessionList()
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }

  const handleRenameSession = async (key: string, newName: string) => {
    // Rename is only meaningful for console sessions with DB
    // For now, keep as no-op for non-console sessions
    console.log('Rename not yet supported for key-based sessions:', key, newName)
    // TODO: Add rename API endpoint
  }

  const handleRefresh = useCallback(() => {
    if (activeSession) {
      void refreshSessionViewRef.current(activeSession, {
        preferredConversationId: activeConversationIdRef.current,
        silent: true,
      })
    } else {
      loadSessionList()
    }
  }, [activeSession, loadSessionList])

  const activeSessionRef = useRef(activeSession)
  activeSessionRef.current = activeSession

  const deepLinkSessionKeyRef = useRef(deepLinkSessionKey)
  deepLinkSessionKeyRef.current = deepLinkSessionKey
  const deepLinkConversationIdRef = useRef(deepLinkConversationId)
  deepLinkConversationIdRef.current = deepLinkConversationId
  const deepLinkTraceIdRef = useRef(deepLinkTraceId)
  deepLinkTraceIdRef.current = deepLinkTraceId
  const deepLinkTaskIdRef = useRef(deepLinkTaskId)
  deepLinkTaskIdRef.current = deepLinkTaskId

  const loadSessionListRef = useRef(loadSessionList)
  loadSessionListRef.current = loadSessionList

  const loadConversationsRef = useRef(loadConversations)
  loadConversationsRef.current = loadConversations

  const loadSessionMessagesWithMetaRef = useRef(loadSessionMessagesWithMeta)
  loadSessionMessagesWithMetaRef.current = loadSessionMessagesWithMeta

  // Keep a ref to loadSessionMessages so ws.onmessage always uses the latest version
  // without re-creating the WebSocket every time sessions state updates.
  const loadSessionMessagesRef = useRef(loadSessionMessages)
  loadSessionMessagesRef.current = loadSessionMessages

  const refreshSessionViewRef = useRef(refreshSessionView)
  refreshSessionViewRef.current = refreshSessionView

  useEffect(() => {
    if (!activeSession) return
    const sessionTasks = directTasksRef.current.filter((task) => task.session_key === activeSession)
    if (sessionTasks.length === 0) return

    let disposed = false

    const syncDirectTasks = async () => {
      const trackedIds = new Set(
        directTasksRef.current
          .filter((task) => task.session_key === activeSession)
          .map((task) => task.task_id),
      )
      if (trackedIds.size === 0) return

      try {
        const response = await api<BackgroundTaskListResponse>(
          `/bg-tasks?session_key=${encodeURIComponent(activeSession)}&include_finished=true`,
        )
        if (disposed) return
        const byId = new Map(response.tasks.map((task) => [task.task_id, task]))
        let shouldRefreshSession = false
        for (const current of directTasksRef.current) {
          if (current.session_key !== activeSession) continue
          const next = byId.get(current.task_id)
          if (
            next
            && FINAL_DIRECT_TASK_STATUSES.has(next.status)
            && !FINAL_DIRECT_TASK_STATUSES.has(current.status)
            && !refreshedDirectTaskIdsRef.current.has(current.task_id)
          ) {
            refreshedDirectTaskIdsRef.current.add(current.task_id)
            shouldRefreshSession = true
          }
        }
        setDirectTasks((prev) => sortDirectTasks(prev.map((task) => {
          if (task.session_key !== activeSession) return task
          const next = byId.get(task.task_id)
          if (!next) return task
          const nextStatus = next.status
          return {
            ...task,
            status: nextStatus,
            started_at: next.started_at,
            elapsed_ms: next.elapsed_ms || (next.started_at ? Math.max(Date.now() - next.started_at * 1000, 0) : 0),
            result_preview: next.result_preview || task.result_preview,
            error_message: next.error_message || '',
            trace_id: next.trace_id || task.trace_id,
            origin_conversation_id: next.origin_conversation_id || task.origin_conversation_id,
            origin_turn_seq: next.origin_turn_seq ?? task.origin_turn_seq,
            chain_id: next.chain_id || task.chain_id,
            parent_task_ids: next.parent_task_ids || task.parent_task_ids,
            node_kind: next.node_kind || task.node_kind,
            skill_name: next.skill_name || task.skill_name,
            matched_by: next.matched_by || task.matched_by,
          }
        })))
        if (shouldRefreshSession) {
          void refreshSessionViewRef.current(activeSession, {
            preferredConversationId: activeConversationIdRef.current,
            silent: true,
          })
        }
      } catch (err) {
        console.error('Failed to sync direct tasks:', err)
      }
    }

    void syncDirectTasks()
    const timer = setInterval(syncDirectTasks, DIRECT_TASK_POLL_MS)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [activeSession, directTasks.length])

  const handleSend = async ({ text, attachments }: ChatComposePayload) => {
    if (mockMode) return
    if (!wsRef.current || sending || inFlightTurn || !currentMeta || activeConversationId !== currentMeta.conversation_id) return
    setError('')
    setSending(true)
    try {
      let uploads: ChatFileUpload[] = []
      if (attachments.length > 0) {
        const formData = new FormData()
        for (const attachment of attachments) {
          formData.append('files', attachment, attachment.name)
        }
        const response = await api<{ uploads: ChatFileUpload[] }>('/chat/uploads', {
          method: 'POST',
          body: formData,
        })
        uploads = response.uploads || []
      }

      const optimisticContent = uploads.length > 0
        ? [
            ...uploads.map((upload) => ({
              type: 'text',
              text: `[${upload.kind === 'image' ? 'image' : 'file'}: ${upload.media_path}]`,
            })),
            ...(text ? [{ type: 'text', text }] : []),
          ]
        : text

      const userMsg: RawMessage = {
        role: 'user',
        content: optimisticContent,
        timestamp: new Date().toISOString(),
        from_agent_id: 'user',
        mentioned_agent_ids: extractAgentMentions(text),
      }
      setInFlightTurn(createInFlightTurn({
        transport: 'console',
        turnSeq: getNextTurnSeq(turns),
        conversationId: activeConversationId,
        userMessage: userMsg,
      }))

      wsRef.current.send(JSON.stringify({
        content: text,
        media: uploads.map((upload) => upload.media_path),
        mentioned_agent_ids: extractAgentMentions(text),
      }))
      setSending(false)
      armSendWatchdog()
    } catch (err) {
      clearSendWatchdog()
      setSending(false)
      setInFlightTurn(null)
      const msg = err instanceof Error ? err.message : 'Failed to send message'
      setError(msg)
      throw err
    }
  }

  const handleDirectTaskSubmit = useCallback(async ({ task_type, prompt, project_path, params }: DirectTaskSubmitParams) => {
    if (
      mockMode ||
      !activeSession ||
      !currentMeta ||
      activeConversationId !== currentMeta.conversation_id
    ) {
      return
    }

    setError('')
    setSending(true)
    try {
      const nextTurnSeq = getNextTurnSeq(turnsRef.current)
      const response = await api<DirectTaskSubmitResponse>('/console/direct-tasks', {
        method: 'POST',
        body: JSON.stringify({
          task_type,
          prompt,
          project_path,
          params: params || {},
          session_key: activeSession,
          conversation_id: activeConversationId || '',
          turn_seq: nextTurnSeq,
        }),
      })
      const task: DirectTaskMessage = {
        type: 'direct_task',
        task_id: response.task_id,
        task_type: response.task_type,
        session_key: activeSession,
        prompt_preview: prompt.slice(0, 200),
        status: response.status || 'queued',
        started_at: Date.now() / 1000,
        elapsed_ms: 0,
        result_preview: '',
        error_message: '',
        origin_conversation_id: response.origin_conversation_id ?? activeConversationId ?? '',
        origin_turn_seq: response.origin_turn_seq ?? nextTurnSeq,
        trace_id: response.trace_id,
      }
      setDirectTasks((prev) => upsertDirectTask(prev, task))
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to submit direct task'
      setError(msg)
      throw err
    } finally {
      setSending(false)
    }
  }, [activeConversationId, activeSession, currentMeta, mockMode])

  const handleStopCurrentTurn = useCallback(async () => {
    if (
      mockMode ||
      !activeSession ||
      !currentMeta ||
      activeConversationId !== currentMeta.conversation_id
    ) {
      return
    }

    setError('')
    try {
      const sessionId = activeSession.replace(/^console:/, '')
      await api<{ ok: boolean; stopped: number; message: string }>(
        `/chat/sessions/${encodeURIComponent(sessionId)}/stop`,
        { method: 'POST' },
      )
      clearConsoleInFlight()
      void refreshSessionViewRef.current(activeSession, {
        preferredConversationId: activeConversationIdRef.current,
        silent: true,
      })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to stop current turn'
      setError(msg)
      throw err
    }
  }, [activeConversationId, activeSession, clearConsoleInFlight, currentMeta, mockMode])

  const isConsole = activeScene === 'console' && !mockMode
  const filteredSessions = sessions
  const selectedConversation = activeSession
    ? (conversationLists[activeSession] || []).find((item) => item.conversation_id === activeConversationId) || null
    : null
  const isReadOnlyConversation = mockMode || !canMutateChat || !currentMeta || activeConversationId !== currentMeta.conversation_id
  const activeDirectTasks = directTasks.filter((task) => (
    task.session_key === activeSession
    && (!task.origin_conversation_id || !activeConversationId || task.origin_conversation_id === activeConversationId)
  ))
  const showTaskOverlay = view === 'tasks' || !!deepLinkTaskId || !!deepLinkChainId || !!taskView || !!deepLinkTraceId
  const openMobileTask = useCallback((taskId: string) => {
    navigate(`/?view=tasks&task_id=${encodeURIComponent(taskId)}`)
  }, [navigate])
  const openMobileTaskList = useCallback(() => {
    navigate('/?view=tasks&task_view=current')
  }, [navigate])
  const closeTaskOverlay = useCallback(() => {
    const next = new URLSearchParams(searchParams)
    next.delete('view')
    next.delete('task_id')
    next.delete('chain_id')
    next.delete('task_view')
    next.delete('trace_id')
    next.delete('turn_seq')
    const query = next.toString()
    navigate({ pathname: '/', search: query ? `?${query}` : '' })
  }, [navigate, searchParams])
  const handleMobileSessionSwipeStart = useCallback((event: TouchEvent<HTMLDivElement>) => {
    if (!isMobile || mobileSessionOpen || showTaskOverlay) return
    const touch = event.touches[0]
    mobileSessionSwipeStart.current = { x: touch.clientX, y: touch.clientY }
  }, [isMobile, mobileSessionOpen, showTaskOverlay])
  const handleMobileSessionSwipeEnd = useCallback((event: TouchEvent<HTMLDivElement>) => {
    const start = mobileSessionSwipeStart.current
    mobileSessionSwipeStart.current = null
    if (!isMobile || !start || mobileSessionOpen || showTaskOverlay || filteredSessions.length < 2) return
    const touch = event.changedTouches[0]
    const dx = touch.clientX - start.x
    const dy = touch.clientY - start.y
    if (Math.abs(dx) < 80 || Math.abs(dx) < Math.abs(dy) * 1.2) return
    const index = filteredSessions.findIndex((session) => session.key === activeSession)
    if (index < 0) return
    const nextIndex = dx < 0 ? Math.min(index + 1, filteredSessions.length - 1) : Math.max(index - 1, 0)
    if (nextIndex !== index) {
      handleSessionSelect(filteredSessions[nextIndex].key)
    }
  }, [activeSession, filteredSessions, handleSessionSelect, isMobile, mobileSessionOpen, showTaskOverlay])

  return (
    <div className={isMobile ? 'mobile-chat-shell relative -m-4 -mb-20 flex flex-col overflow-hidden' : 'relative -m-6 flex h-full flex-col overflow-hidden'}>
      {(mockMode || !canMutateChat) && (
        <div className="border-b border-amber-500/20 bg-amber-500/10 px-4 py-2 text-xs font-medium text-amber-300">
          只读模式 · 申请权限
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 bg-[var(--danger)]/10 text-[var(--danger)] text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="ml-2 hover:underline">Dismiss</button>
        </div>
      )}
      {/* Deep link notice */}
      {deepLinkNotice && (
        <div className="px-4 py-2 bg-[var(--accent)]/10 text-[var(--accent)] text-xs flex items-center justify-between">
          <span>{deepLinkNotice}</span>
          <button onClick={() => setDeepLinkNotice(null)} className="ml-2 hover:underline">Dismiss</button>
        </div>
      )}

      {isMobile && (
        <TaskPreviewBar
          density="inline"
          onOpenTask={openMobileTask}
          onOpenList={openMobileTaskList}
        />
      )}
      <ConversationConfigBar
        session={currentMeta}
        activeScene={activeScene}
        isReadOnly={mockMode || !canMutateChat}
        isMobile={isMobile}
        onParticipantsChange={handleParticipantsChange}
      />

      {/* Main content: sidebar + message area */}
      <div
        className="flex-1 flex min-h-0 min-w-0"
        onTouchStart={handleMobileSessionSwipeStart}
        onTouchEnd={handleMobileSessionSwipeEnd}
      >
        {/* Desktop: inline sidebar. Mobile: overlay drawer */}
        {isMobile ? (
          mobileSessionOpen && (
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 z-40 bg-black/50"
                onClick={() => setMobileSessionOpen(false)}
              />
              {/* Drawer */}
              <div className="fixed inset-y-0 left-0 z-50 w-72 animate-slide-in-left">
                <SessionSidebar
                  sessions={filteredSessions}
                  activeSession={activeSession}
                  activeConversationId={activeConversationId}
                  conversationLists={conversationLists}
                  isConsoleScene={isConsole}
                  canManageSessions={canMutateChat}
                  onSessionSelect={handleSessionSelect}
                  onConversationSelect={handleConversationSelect}
                  onCreateConsole={handleCreateConsole}
                  onDeleteSession={handleDeleteSession}
                  onRenameSession={handleRenameSession}
                />
              </div>
            </>
          )
        ) : (
          <SessionSidebar
            sessions={filteredSessions}
            activeSession={activeSession}
            activeConversationId={activeConversationId}
            conversationLists={conversationLists}
            isConsoleScene={isConsole}
            canManageSessions={canMutateChat}
            onSessionSelect={handleSessionSelect}
            onConversationSelect={handleConversationSelect}
            onCreateConsole={handleCreateConsole}
            onDeleteSession={handleDeleteSession}
            onRenameSession={handleRenameSession}
          />
        )}
        <MessageArea
          session={currentMeta}
          conversation={selectedConversation}
          conversationId={activeConversationId}
          turns={turns}
          inFlightTurn={inFlightTurn}
          directTasks={activeDirectTasks}
          loading={loadingMessages}
          isConsole={isConsole && !!activeSession}
          isReadOnly={isReadOnlyConversation}
          transportStatus={transportStatus}
          activeTransport={activeTransport}
          sendDisabled={sending || !!inFlightTurn}
          onSend={handleSend}
          onStopCurrentTurn={handleStopCurrentTurn}
          onSubmitDirectTask={handleDirectTaskSubmit}
          onRefresh={handleRefresh}
          isMobile={isMobile}
          onToggleSessionPanel={() => setMobileSessionOpen(v => !v)}
          targetTaskId={deepLinkTaskId}
          targetTurnSeq={deepLinkTurnSeq}
          targetTraceId={deepLinkTraceId}
        />
      </div>
      {showTaskOverlay && (
        <TaskOverlay
          taskId={deepLinkTaskId}
          chainId={deepLinkChainId}
          traceId={deepLinkTraceId}
          taskView={taskView}
          isMobile={isMobile}
          onClose={closeTaskOverlay}
        />
      )}
    </div>
  )
}
