import { useState, useMemo } from 'react'
import { ChevronDown, ChevronRight, User, Bot, Wrench, MessageCircle, Layers } from 'lucide-react'

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
  userTurns: number
  assistantTurns: number
  toolCalls: number
  truncatedCount: number
}

const CONTENT_TRUNCATE_THRESHOLD = 198

function UserBubble({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false)
  const isTruncated = content.length >= CONTENT_TRUNCATE_THRESHOLD
  const displayTruncated = content.length > 200
  const display = displayTruncated && !expanded ? content.slice(0, 200) + '…' : content

  return (
    <div className="w-full sm:max-w-[85%] md:max-w-[80%] px-3 py-2 rounded-xl rounded-br-sm bg-[var(--accent)]/15 border border-[var(--accent)]/20 text-sm">
      <div className="flex items-center gap-1.5 mb-1 text-xs text-[var(--text-secondary)]">
        <User className="w-3 h-3 shrink-0" />
        <span>User</span>
        {isTruncated && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-[var(--warning)]/10 text-[var(--warning)]">已截断</span>
        )}
      </div>
      <pre className="whitespace-pre-wrap font-[inherit] text-[var(--text-primary)] break-words">{display}</pre>
      {displayTruncated && (
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
  const isTruncated = content.length >= CONTENT_TRUNCATE_THRESHOLD
  const displayTruncated = content.length > 300
  const display = displayTruncated && !expanded ? content.slice(0, 300) + '…' : content

  return (
    <div className="w-full sm:max-w-[85%] md:max-w-[80%] px-3 py-2 rounded-xl rounded-bl-sm bg-[var(--bg-secondary)] border border-[var(--border)] text-sm">
      <div className="flex items-center gap-1.5 mb-1 text-xs text-[var(--text-secondary)]">
        <Bot className="w-3 h-3 shrink-0" />
        <span>Assistant</span>
        {isTruncated && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-[var(--warning)]/10 text-[var(--warning)]">已截断</span>
        )}
      </div>
      <pre className="whitespace-pre-wrap font-[inherit] text-[var(--text-primary)] break-words">{display}</pre>
      {displayTruncated && (
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
        {stats.userTurns} 轮对话
      </span>
      <span>{stats.totalMessages} 条消息</span>
      {stats.toolCalls > 0 && (
        <span className="inline-flex items-center gap-1">
          <Wrench className="w-3 h-3" />
          {stats.toolCalls} 工具调用
        </span>
      )}
      {stats.truncatedCount > 0 ? (
        <span className="inline-flex items-center gap-1 text-[var(--warning)]">
          <Layers className="w-3 h-3" />
          已压缩 · {stats.truncatedCount} 条截断
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-[var(--success)]">
          <Layers className="w-3 h-3" />
          未压缩
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
    let userTurns = 0
    let assistantTurns = 0
    let toolCalls = 0
    let truncatedCount = 0
    for (const m of messages) {
      if (m.role === 'user') userTurns++
      else if (m.role === 'assistant') assistantTurns++
      else if (m.role === 'tool') toolCalls++
      if (m.content && m.content.length >= CONTENT_TRUNCATE_THRESHOLD) truncatedCount++
    }
    return { totalMessages: messages.length, userTurns, assistantTurns, toolCalls, truncatedCount }
  }, [messages])

  if (messages.length === 0) {
    return <span className="text-xs text-[var(--text-secondary)] italic">No conversation history</span>
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
