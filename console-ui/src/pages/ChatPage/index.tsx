import { useEffect, useRef, useState, useCallback } from 'react'
import { api, wsUrl } from '../../api/client'
import { useAuth } from '../../stores/auth'
import { useResponsiveMode } from '../../hooks/useResponsiveMode'
import type { ChatComposePayload, ChatImageUpload, SceneType, SessionMeta, ConversationMeta, RawMessage, TurnGroup, ChatStreamStatus, ActiveChatTransport } from './types'
import { SCENE_ORDER } from './types'
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
import { SceneTabs } from './SceneTabs'
import { SessionSidebar } from './SessionSidebar'
import { MessageArea } from './MessageArea'

const SESSION_LIST_POLL_MS = 30_000
const MAX_RECONNECT_DELAY_MS = 15_000
const SEND_WATCHDOG_MS = 120_000

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
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [conversationLists, setConversationLists] = useState<Record<string, ConversationMeta[]>>({})
  const [activeScene, setActiveScene] = useState<SceneType>('console')
  const [activeSession, setActiveSession] = useState('')
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [currentMeta, setCurrentMeta] = useState<SessionMeta | null>(null)
  const [turns, setTurns] = useState<TurnGroup[]>([])
  const [inFlightTurn, setInFlightTurn] = useState<InFlightTurn | null>(null)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [transportStatus, setTransportStatus] = useState<ChatStreamStatus>('idle')
  const [activeTransport, setActiveTransport] = useState<ActiveChatTransport>('none')
  const [mobileSessionOpen, setMobileSessionOpen] = useState(false)
  const [error, setError] = useState('')
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
  const { isMobile } = useResponsiveMode()
  const { isMockTester } = useAuth()
  const mockMode = isMockTester()
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
        const firstScene = SCENE_ORDER.find((s) => metas.some((m) => m.scene === s)) || metas[0].scene
        setActiveScene(firstScene)
        const firstSessionInScene = metas.find((m) => m.scene === firstScene)
        if (firstSessionInScene) {
          setActiveSession(firstSessionInScene.key)
          void (async () => {
            const conversations = await loadConversationsRef.current(firstSessionInScene.key)
            const conversationId = pickConversationId(firstSessionInScene, conversations, firstSessionInScene.conversation_id)
            await loadSessionMessagesWithMetaRef.current(firstSessionInScene.key, firstSessionInScene, conversationId)
          })()
          if (firstScene === 'console' && !mockMode) {
            const sid = firstSessionInScene.key.replace(/^console:/, '')
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
    setMobileSessionOpen(false)
    setInFlightTurn(null)
    setSending(false)
    void loadSessionMessagesWithMeta(sessionKey, meta, conversationId)
  }

  const handleSceneChange = (scene: SceneType) => {
    setActiveScene(scene)
    disconnectConsoleWs()
    disconnectObserveWs()
    setInFlightTurn(null)
    setSending(false)

    const sceneSessions = sessions.filter((s) => s.scene === scene)
    if (sceneSessions.length > 0) {
      const first = sceneSessions[0]
      setActiveSession(first.key)
      setActiveConversationId(null)
      void (async () => {
        const conversations = await loadConversationsRef.current(first.key)
        const conversationId = pickConversationId(first, conversations, first.conversation_id)
        await loadSessionMessagesWithMetaRef.current(first.key, first, conversationId)
      })()
      if (scene === 'console' && !mockMode) {
        const sid = first.key.replace(/^console:/, '')
        connectWs(sid)
      }
    } else {
      setActiveSession('')
      setActiveConversationId(null)
      setCurrentMeta(null)
      setTurns([])
      setInFlightTurn(null)
      setSending(false)
      setActiveTransport('none')
      setTransportStatus('idle')
    }
  }

  const handleCreateConsole = async () => {
    setError('')
    try {
      const title = `Chat ${sessions.filter((s) => s.scene === 'console').length + 1}`
      const res = await api<{ session_id: string; conversation_id: string }>('/chat/sessions', {
        method: 'POST',
        body: JSON.stringify({ title }),
      })

      const sid = res.session_id
      const newKey = `console:${sid}`

      setActiveScene('console')
      setActiveSession(newKey)
      setCurrentMeta({
        key: newKey,
        scene: 'console',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        conversation_id: res.conversation_id,
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

  const handleSend = async ({ text, attachments }: ChatComposePayload) => {
    if (mockMode) return
    if (!wsRef.current || sending || inFlightTurn || !currentMeta || activeConversationId !== currentMeta.conversation_id) return
    setError('')
    setSending(true)
    try {
      let uploads: ChatImageUpload[] = []
      if (attachments.length > 0) {
        const formData = new FormData()
        for (const attachment of attachments) {
          formData.append('files', attachment, attachment.name)
        }
        const response = await api<{ uploads: ChatImageUpload[] }>('/chat/uploads', {
          method: 'POST',
          body: formData,
        })
        uploads = response.uploads || []
      }

      const optimisticContent = uploads.length > 0
        ? [
            ...uploads.map((upload) => ({ type: 'text', text: `[image: ${upload.media_path}]` })),
            ...(text ? [{ type: 'text', text }] : []),
          ]
        : text

      const userMsg: RawMessage = {
        role: 'user',
        content: optimisticContent,
        timestamp: new Date().toISOString(),
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

  const isConsole = activeScene === 'console' && !mockMode
  const filteredSessions = sessions.filter((s) => s.scene === activeScene)
  const selectedConversation = activeSession
    ? (conversationLists[activeSession] || []).find((item) => item.conversation_id === activeConversationId) || null
    : null
  const isReadOnlyConversation = mockMode || !currentMeta || activeConversationId !== currentMeta.conversation_id

  return (
    <div className={isMobile ? '-m-4 -mb-20 h-[calc(100dvh-4rem-env(safe-area-inset-bottom,0px))] flex flex-col overflow-hidden' : '-m-6 h-[calc(100vh)] flex flex-col overflow-hidden'}>
      {/* Top scene tabs bar */}
      <SceneTabs
        sessions={sessions}
        activeScene={activeScene}
        onSceneChange={handleSceneChange}
      />

      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 bg-[var(--danger)]/10 text-[var(--danger)] text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="ml-2 hover:underline">Dismiss</button>
        </div>
      )}

      {/* Main content: sidebar + message area */}
      <div className="flex-1 flex min-h-0 min-w-0">
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
          loading={loadingMessages}
          isConsole={isConsole && !!activeSession}
          isReadOnly={isReadOnlyConversation}
          transportStatus={transportStatus}
          activeTransport={activeTransport}
          sendDisabled={sending || !!inFlightTurn}
          onSend={handleSend}
          onRefresh={handleRefresh}
          isMobile={isMobile}
          onToggleSessionPanel={() => setMobileSessionOpen(v => !v)}
        />
      </div>
    </div>
  )
}
