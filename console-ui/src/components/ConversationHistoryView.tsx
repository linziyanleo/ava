import { useState, useMemo } from 'react'
import { ChevronDown, ChevronRight, User, Bot, Wrench, MessageCircle } from 'lucide-react'

interface Message {
  role: string
  content: string
  name?: string
}

interface ConversationHistoryViewProps {
  historyJson: string
}

interface HistoryStats {
  totalMessages: number
  userMessages: number
  assistantMessages: number
  toolCalls: number
}

const CONTEXT_PREVIEW_LIMIT = 500

function UserBubble({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false)
  const isFolded = content.length > CONTEXT_PREVIEW_LIMIT
  const display = isFolded && !expanded ? content.slice(0, CONTEXT_PREVIEW_LIMIT) + '…' : content

  return (
    <div className="w-full sm:max-w-[85%] md:max-w-[80%] px-3 py-2 rounded-xl rounded-br-sm bg-[var(--accent)]/15 border border-[var(--accent)]/20 text-sm">
      <div className="flex items-center gap-1.5 mb-1 text-xs text-[var(--text-secondary)]">
        <User className="w-3 h-3 shrink-0" />
        <span>User</span>
        {isFolded && !expanded && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-[var(--warning)]/10 text-[var(--warning)]">已折叠</span>
        )}
      </div>
      <pre className="whitespace-pre-wrap font-[inherit] text-[var(--text-primary)] break-words">{display}</pre>
      {isFolded && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1 text-xs text-[var(--accent)] hover:underline"
        >
          {expanded ? '收起' : '展开'}
        </button>
      )}
    </div>
  )
}

function AssistantBubble({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false)
  const isFolded = content.length > CONTEXT_PREVIEW_LIMIT
  const display = isFolded && !expanded ? content.slice(0, CONTEXT_PREVIEW_LIMIT) + '…' : content

  return (
    <div className="w-full sm:max-w-[85%] md:max-w-[80%] px-3 py-2 rounded-xl rounded-bl-sm bg-[var(--bg-secondary)] border border-[var(--border)] text-sm">
      <div className="flex items-center gap-1.5 mb-1 text-xs text-[var(--text-secondary)]">
        <Bot className="w-3 h-3 shrink-0" />
        <span>Assistant</span>
        {isFolded && !expanded && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-[var(--warning)]/10 text-[var(--warning)]">已折叠</span>
        )}
      </div>
      <pre className="whitespace-pre-wrap font-[inherit] text-[var(--text-primary)] break-words">{display}</pre>
      {isFolded && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1 text-xs text-[var(--accent)] hover:underline"
        >
          {expanded ? '收起' : '展开'}
        </button>
      )}
    </div>
  )
}

function ToolCallCard({ name, content }: { name?: string; content: string }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="w-full sm:max-w-[85%] md:max-w-[80%] px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] text-sm">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        <Wrench className="w-3 h-3 shrink-0" />
        <span className="truncate">{name || 'Tool'}</span>
        {expanded ? <ChevronDown className="w-3 h-3 shrink-0" /> : <ChevronRight className="w-3 h-3 shrink-0" />}
      </button>
      {expanded && (
        <pre className="mt-1.5 whitespace-pre-wrap font-mono text-xs text-[var(--text-secondary)] max-h-40 overflow-y-auto break-all">
          {content}
        </pre>
      )}
    </div>
  )
}

function StatsBar({ stats }: { stats: HistoryStats }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-1.5 mb-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] text-[11px] text-[var(--text-secondary)]">
      <span className="inline-flex items-center gap-1">
        <MessageCircle className="w-3 h-3" />
        {stats.userMessages} 条用户消息
      </span>
      <span>{stats.totalMessages} 条消息</span>
      {stats.assistantMessages > 0 && <span>{stats.assistantMessages} 条助手消息</span>}
      {stats.toolCalls > 0 && (
        <span className="inline-flex items-center gap-1">
          <Wrench className="w-3 h-3" />
          {stats.toolCalls} 工具调用
        </span>
      )}
    </div>
  )
}

export default function ConversationHistoryView({ historyJson }: ConversationHistoryViewProps) {
  const messages = useMemo<Message[]>(() => {
    try {
      const parsed = JSON.parse(historyJson)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }, [historyJson])

  const stats = useMemo<HistoryStats>(() => {
    let userMessages = 0
    let assistantMessages = 0
    let toolCalls = 0
    for (const m of messages) {
      if (m.role === 'user') userMessages++
      else if (m.role === 'assistant') assistantMessages++
      else if (m.role === 'tool') toolCalls++
    }
    return { totalMessages: messages.length, userMessages, assistantMessages, toolCalls }
  }, [messages])

  if (messages.length === 0) {
    return <span className="text-xs text-[var(--text-secondary)] italic">无请求上下文</span>
  }

  return (
    <div className="w-full">
      <StatsBar stats={stats} />
      <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
        {messages.map((msg, i) => (
          <div key={i} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            {msg.role === 'user' && <UserBubble content={msg.content} />}
            {msg.role === 'assistant' && <AssistantBubble content={msg.content} />}
            {msg.role === 'tool' && <ToolCallCard name={msg.name} content={msg.content} />}
          </div>
        ))}
      </div>
    </div>
  )
}
