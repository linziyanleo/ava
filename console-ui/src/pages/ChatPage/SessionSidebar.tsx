import { useState, useEffect } from 'react'
import { Plus, MessageSquare, Trash2, Pencil, Check, X, CornerDownRight, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { SessionMeta, ConversationMeta } from './types'
import { formatTokenCount } from './utils'

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
}: SessionSidebarProps) {
  const [collapsed, setCollapsed] = useState(() => {
    const stored = localStorage.getItem('chat-sidebar-collapsed')
    return stored === null ? true : stored === 'true'
  })
  const [editingFilename, setEditingFilename] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  useEffect(() => {
    localStorage.setItem('chat-sidebar-collapsed', String(collapsed))
  }, [collapsed])

  const startRename = (s: SessionMeta, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingFilename(s.key)
    setEditValue(s.key)
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
        collapsed ? 'w-8' : 'w-full sm:w-64',
      )}
    >
      {collapsed ? (
        <div className="flex flex-col items-center pt-2">
          <button
            onClick={() => setCollapsed(false)}
            className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
            title="展开侧边栏"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <>
          <div className="p-2 border-b border-[var(--border)] flex items-center gap-1">
            <button
              onClick={onCreateConsole}
              className="flex items-center gap-2 flex-1 px-3 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" /> New Chat
            </button>
            <button
              onClick={() => setCollapsed(true)}
              className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors shrink-0"
              title="折叠侧边栏"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {sessions.map((s) => (
              <div key={s.key}>
                <div
                  className={cn(
                    'flex items-center justify-between group px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors',
                    activeSession === s.key
                      ? 'bg-[var(--accent)]/10 text-[var(--accent)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]',
                  )}
                  onClick={() => onSessionSelect(s.key)}
                >
                  <div className="flex items-center gap-2 truncate min-w-0">
                    <MessageSquare className="w-3.5 h-3.5 shrink-0" />
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
                        <button onClick={() => confirmRename(s.key)} className="p-0.5 text-green-500 hover:text-green-400">
                          <Check className="w-3 h-3" />
                        </button>
                        <button onClick={cancelRename} className="p-0.5 text-[var(--text-secondary)] hover:text-[var(--danger)]">
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ) : (
                      <div className="truncate">
                        <div className="truncate text-sm">{s.key}</div>
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
                      {onRenameSession && (
                        <button
                          onClick={(e) => startRename(s, e)}
                          className="p-1 text-[var(--text-secondary)] hover:text-[var(--accent)]"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); setConfirmDelete(s.key) }}
                        className="p-1 text-[var(--text-secondary)] hover:text-[var(--danger)]"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                  {confirmDelete === s.key && (
                    <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <span className="text-[10px] text-[var(--danger)]">Delete?</span>
                      <button
                        onClick={() => { onDeleteSession(s.key); setConfirmDelete(null) }}
                        className="p-0.5 text-[var(--danger)] hover:text-red-400"
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
            ))}
            {sessions.length === 0 && (
              <p className="text-center text-xs text-[var(--text-secondary)] py-8">
                No sessions
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
