import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../../api/client'
import ScreencastView from './ScreencastView'
import ActivityPanel from './ActivityPanel'
import type { PageAgentEvent, ActivityEntry } from './types'

export default function BrowserPage() {
  const [sessions, setSessions] = useState<string[]>([])
  const [activeSession, setActiveSession] = useState<string>('')
  const [connected, setConnected] = useState(false)
  const [frame, setFrame] = useState<string | null>(null)
  const [activities, setActivities] = useState<ActivityEntry[]>([])
  const [status, setStatus] = useState<string>('idle')
  const [pageUrl, setPageUrl] = useState('')
  const [stepCount, setStepCount] = useState(0)

  const wsRef = useRef<WebSocket | null>(null)
  const activityIdRef = useRef(0)

  // 获取活跃 session 列表
  const fetchSessions = useCallback(async () => {
    try {
      const data = await api<{ sessions: string[] }>('/page-agent/sessions')
      setSessions(data.sessions)
      if (data.sessions.length > 0 && !activeSession) {
        setActiveSession(data.sessions[0])
      }
    } catch {
      // page-agent 可能未启动
    }
  }, [activeSession])

  // 无会话时 2s 快速轮询，有会话后放慢到 5s
  useEffect(() => {
    fetchSessions()
    const interval = setInterval(fetchSessions, sessions.length > 0 ? 5000 : 2000)
    return () => clearInterval(interval)
  }, [fetchSessions, sessions.length])

  // WebSocket 连接
  useEffect(() => {
    if (!activeSession) {
      setConnected(false)
      setFrame(null)
      setPageUrl('')
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/page-agent/ws/${activeSession}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      // 不清空 activities — 服务端会回放缓存事件
    }

    ws.onmessage = (event) => {
      try {
        const msg: PageAgentEvent = JSON.parse(event.data)

        if (msg.type === 'frame') {
          setFrame(msg.data)
        } else if (msg.type === 'activity') {
          const a = msg.activity
          activityIdRef.current += 1
          const entry: ActivityEntry = {
            id: `a-${activityIdRef.current}`,
            timestamp: Date.now(),
            type: a.type,
            tool: a.tool,
            detail: a.output || (a.input ? JSON.stringify(a.input) : undefined),
          }
          setActivities((prev) => [entry, ...prev].slice(0, 100))

          if (a.type === 'executed') {
            setStepCount((c) => c + 1)
          }
        } else if (msg.type === 'status') {
          setStatus(msg.status)
        } else if (msg.type === 'page_info') {
          setPageUrl(msg.page_url || '')
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setConnected(false)
      setPageUrl('')
    }

    ws.onerror = () => {
      setConnected(false)
      setPageUrl('')
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [activeSession])

  return (
    <div className="h-full flex flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
        <h2 className="text-sm font-medium text-[var(--text-primary)]">浏览器预览</h2>

        {sessions.length > 0 && (
          <select
            value={activeSession}
            onChange={(e) => setActiveSession(e.target.value)}
            className="text-xs bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1"
          >
            {sessions.map((sid) => (
              <option key={sid} value={sid}>
                {sid}
              </option>
            ))}
          </select>
        )}

        <div className="ml-auto flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-gray-400'}`} />
          {connected ? '已连接' : '未连接'}
        </div>
      </div>

      {/* Main content: screencast + activity panel */}
      <div className="flex-1 flex min-h-0">
        <ScreencastView frame={frame} connected={connected} />
        <ActivityPanel
          entries={activities}
          status={status}
          pageUrl={pageUrl}
          stepCount={stepCount}
        />
      </div>
    </div>
  )
}
