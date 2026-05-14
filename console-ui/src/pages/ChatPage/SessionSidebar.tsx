import { useState, useEffect, useMemo, useRef } from 'react'
import { Plus, MessageSquare, Trash2, Pencil, Check, X, CornerDownRight, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { SessionMeta, ConversationMeta } from './types'
import { formatTokenCount, getAgentInitial, getAgentLabel, getSessionParticipants, getSessionTitle } from './utils'

function relativeTime(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = now - then
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`
  if (diff < 172_800_000) return '昨天'
  const d = new Date(dateStr)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

interface SessionSidebarProps {
  sessions: SessionMeta[]
  activeSession: string
  activeConversationId: string | null
  conversationLists: Record<string, ConversationMeta[]>
  isConsoleScene?: boolean
  canManageSessions?: boolean
  onSessionSelect: (key: string) => void
  onConversationSelect: (sessionKey: string, conversationId: string) => void
  onCreateConsole: () => void
  onDeleteSession: (key: string) => void
  onRenameSession?: (key: string, newName: string) => void
}

export function SessionSidebar({
  sessions,
  activeSession,
  activeConversationId,
  conversationLists,
  onSessionSelect,
  onConversationSelect,
  onCreateConsole,
  onDeleteSession,
  onRenameSession,
  canManageSessions = true,
}: SessionSidebarProps) {
  const [collapsed, setCollapsed] = useState(() => {
    const stored = localStorage.getItem('chat-sidebar-collapsed')
    return stored === null ? true : stored === 'true'
  })
  const [editingFilename, setEditingFilename] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [focusSearchAfterExpand, setFocusSearchAfterExpand] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    localStorage.setItem('chat-sidebar-collapsed', String(collapsed))
  }, [collapsed])

  useEffect(() => {
    if (collapsed || !focusSearchAfterExpand) return
    const frame = requestAnimationFrame(() => {
      searchInputRef.current?.focus()
      setFocusSearchAfterExpand(false)
    })
    return () => cancelAnimationFrame(frame)
  }, [collapsed, focusSearchAfterExpand])

  const getSessionPreview = (s: SessionMeta) => {
    const primaryConversation = (conversationLists[s.key] || []).find((item) => item.is_active) || (conversationLists[s.key] || [])[0]
    return primaryConversation?.first_message_preview || (s.message_count > 0 ? `${s.message_count} messages` : 'New conversation')
  }

  const visibleSessions = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return sessions
    return sessions.filter((s) => {
      const searchable = `${getSessionTitle(s)} ${getSessionPreview(s)}`.toLowerCase()
      return searchable.includes(query)
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationLists, search, sessions])

  const startRename = (s: SessionMeta, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingFilename(s.key)
    setEditValue(getSessionTitle(s))
  }

  const confirmRename = (key: string) => {
    if (editValue.trim() && onRenameSession) {
      onRenameSession(key, editValue.trim())
    }
    setEditingFilename(null)
  }

  const cancelRename = () => setEditingFilename(null)

  return (
    <div
      className={cn(
        'h-full shrink-0 bg-[var(--bg-secondary)] border-r border-[var(--border)] flex flex-col transition-all duration-300 overflow-hidden',
        collapsed ? 'w-12' : 'w-full sm:w-64',
      )}
    >
      {collapsed ? (
        <div className="flex flex-col items-center gap-1 pt-2">
          {canManageSessions && (
            <button
              onClick={onCreateConsole}
              className="flex h-10 w-10 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
              title="新建对话"
              aria-label="新建对话"
            >
              <Plus className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => {
              setFocusSearchAfterExpand(true)
              setCollapsed(false)
            }}
            className="flex h-10 w-10 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            title="搜索会话"
            aria-label="搜索会话"
          >
            <Search className="h-4 w-4" />
          </button>
          <button
            onClick={() => setCollapsed(false)}
            className="flex h-10 w-10 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            title="展开侧边栏"
            aria-label="展开侧边栏"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <>
          <div className="border-b border-[var(--border)] p-2">
            <div className="flex items-center gap-1">
              {canManageSessions && (
                <button
                  onClick={onCreateConsole}
                  className="flex items-center gap-2 flex-1 px-3 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors"
                >
                  <Plus className="w-4 h-4" /> New Chat
                </button>
              )}
              <button
                onClick={() => setCollapsed(true)}
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors shrink-0"
                title="折叠侧边栏"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            </div>
            <label className="mt-2 flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-[var(--text-secondary)]">
              <Search className="h-3.5 w-3.5 shrink-0" />
              <input
                ref={searchInputRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索会话"
                className="min-w-0 flex-1 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-secondary)]"
              />
            </label>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {visibleSessions.map((s) => {
              const participants = getSessionParticipants(s)
              const participantLabels = participants.map(getAgentLabel).filter(Boolean)
              const preview = getSessionPreview(s)
              return (
              <div key={s.key}>
                <div
                  className={cn(
                    'flex items-start justify-between group px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors',
                    activeSession === s.key
                      ? 'bg-[var(--accent)]/10 text-[var(--accent)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]',
                  )}
                  onClick={() => onSessionSelect(s.key)}
                >
                  <div className="flex min-w-0 flex-1 items-start gap-2">
                    <MessageSquare className="mt-0.5 w-3.5 h-3.5 shrink-0" />
                    {editingFilename === s.key ? (
                      <div className="flex items-center gap-1 min-w-0" onClick={(e) => e.stopPropagation()}>
                        <input
                          autoFocus
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') confirmRename(s.key)
                            if (e.key === 'Escape') cancelRename()
                          }}
                          className="w-full px-1 py-0.5 text-sm bg-[var(--bg-primary)] border border-[var(--border)] rounded text-[var(--text-primary)] outline-none"
                        />
                        <button onClick={() => confirmRename(s.key)} className="p-0.5 text-[var(--ava-success)] hover:text-[var(--ava-success)]">
                          <Check className="w-3 h-3" />
                        </button>
                        <button onClick={cancelRename} className="p-0.5 text-[var(--text-secondary)] hover:text-[var(--danger)]">
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ) : (
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-[var(--text-primary)]">{getSessionTitle(s)}</div>
                        <div className="mt-1 flex min-w-0 items-center gap-1.5">
                          <div className="flex shrink-0 -space-x-1">
                            {participants.slice(0, 3).map((agentId) => (
                              <span
                                key={agentId}
                                title={getAgentLabel(agentId)}
                                className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[var(--bg-secondary)] bg-[var(--bg-tertiary)] text-[8px] font-semibold text-[var(--text-secondary)]"
                              >
                                {getAgentInitial(agentId)}
                              </span>
                            ))}
                            {participants.length > 3 && (
                              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[var(--bg-secondary)] bg-[var(--bg-tertiary)] text-[8px] font-semibold text-[var(--text-secondary)]">
                                +{participants.length - 3}
                              </span>
                            )}
                          </div>
                          <div className="truncate text-[10px] text-[var(--text-secondary)]">
                            {participantLabels.join(' / ')}
                          </div>
                        </div>
                        <div className="mt-0.5 truncate text-[10px] text-[var(--text-secondary)] opacity-80">
                          {preview}
                        </div>
                        <div className="text-[10px] text-[var(--text-secondary)] opacity-70">
                          {s.message_count} msgs · {s.updated_at ? relativeTime(s.updated_at) : ''}
                        </div>
                        <div className="text-[10px] text-[var(--text-secondary)] opacity-70">
                          {formatTokenCount(s.token_stats.total_tokens)} tokens · {s.token_stats.llm_calls} calls
                        </div>
                      </div>
                    )}
                  </div>
                  {editingFilename !== s.key && confirmDelete !== s.key && (
                    <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      {canManageSessions && onRenameSession && (
                        <button
                          onClick={(e) => startRename(s, e)}
                          className="p-1 text-[var(--text-secondary)] hover:text-[var(--accent)]"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {canManageSessions && (
                        <button
                          onClick={(e) => { e.stopPropagation(); setConfirmDelete(s.key) }}
                          className="p-1 text-[var(--text-secondary)] hover:text-[var(--danger)]"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  )}
                  {confirmDelete === s.key && (
                    <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <span className="text-[10px] text-[var(--danger)]">Delete?</span>
                      <button
                        onClick={() => { onDeleteSession(s.key); setConfirmDelete(null) }}
                        className="p-0.5 text-[var(--danger)] hover:text-[var(--ava-danger)]"
                      >
                        <Check className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(null)}
                        className="p-0.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>

                {activeSession === s.key && (conversationLists[s.key] || []).length > 0 && (
                  <div className="ml-4 mt-1 space-y-0.5">
                    {(conversationLists[s.key] || []).map((conversation) => {
                      const preview = conversation.first_message_preview || (conversation.is_active ? '当前空会话' : '历史空会话')
                      return (
                        <button
                          key={`${s.key}:${conversation.conversation_id}`}
                          onClick={() => onConversationSelect(s.key, conversation.conversation_id)}
                          className={cn(
                            'w-full text-left flex items-start gap-2 px-2 py-1.5 rounded-md transition-colors',
                            activeConversationId === conversation.conversation_id
                              ? 'bg-[var(--accent)]/10 text-[var(--accent)]'
                              : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]',
                          )}
                        >
                          <CornerDownRight className="w-3 h-3 mt-0.5 shrink-0 opacity-70" />
                          <div className="min-w-0">
                            <div className="truncate text-[11px]">
                              {preview}
                            </div>
                            <div className="text-[10px] text-[var(--text-secondary)] opacity-70">
                              {conversation.message_count} msgs
                              {conversation.updated_at ? ` · ${relativeTime(conversation.updated_at)}` : ''}
                              {conversation.is_active ? ' · 活跃' : ''}
                              {conversation.is_legacy ? ' · legacy' : ''}
                            </div>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
              )
            })}
            {sessions.length === 0 && (
              <p className="text-center text-xs text-[var(--text-secondary)] py-8">
                No sessions
              </p>
            )}
            {sessions.length > 0 && visibleSessions.length === 0 && (
              <p className="text-center text-xs text-[var(--text-secondary)] py-8">
                无匹配会话
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
