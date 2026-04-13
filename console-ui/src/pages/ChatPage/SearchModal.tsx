import { useState, useEffect, useRef, useCallback, type ReactElement } from 'react'
import { Search, X, ArrowRight } from 'lucide-react'
import type { TurnGroup } from './types'
import { getContentText } from './utils'

interface SearchResult {
  turnIndex: number
  role: 'User' | 'Assistant'
  snippet: string
  matchStart: number
  timestamp?: string
}

function formatTimestamp(ts?: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  if (d.getFullYear() === now.getFullYear()) {
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

interface SearchModalProps {
  turns: TurnGroup[]
  onClose: () => void
}

function highlightSnippet(snippet: string, keyword: string): ReactElement {
  const lowerSnippet = snippet.toLowerCase()
  const lowerKeyword = keyword.toLowerCase()
  const parts: ReactElement[] = []
  let lastIndex = 0

  let idx = lowerSnippet.indexOf(lowerKeyword, lastIndex)
  while (idx !== -1) {
    if (idx > lastIndex) {
      parts.push(<span key={lastIndex}>{snippet.slice(lastIndex, idx)}</span>)
    }
    parts.push(
      <mark key={`h-${idx}`} className="bg-[var(--accent)]/30 text-[var(--text-primary)] rounded px-0.5">
        {snippet.slice(idx, idx + keyword.length)}
      </mark>
    )
    lastIndex = idx + keyword.length
    idx = lowerSnippet.indexOf(lowerKeyword, lastIndex)
  }

  if (lastIndex < snippet.length) {
    parts.push(<span key={lastIndex}>{snippet.slice(lastIndex)}</span>)
  }

  return <>{parts}</>
}

function buildSnippet(text: string, matchIndex: number, keyword: string): string {
  const contextChars = 40
  const start = Math.max(0, matchIndex - contextChars)
  const end = Math.min(text.length, matchIndex + keyword.length + contextChars)
  let snippet = text.slice(start, end)
  if (start > 0) snippet = '…' + snippet
  if (end < text.length) snippet = snippet + '…'
  return snippet
}

function searchTurns(turns: TurnGroup[], keyword: string): SearchResult[] {
  if (!keyword.trim()) return []

  const lowerKeyword = keyword.toLowerCase()
  const results: SearchResult[] = []

  for (let i = 0; i < turns.length && results.length < 20; i++) {
    const turn = turns[i]

    // Search user message
    const userText = getContentText(turn.userMessage.content)
    const userIdx = userText.toLowerCase().indexOf(lowerKeyword)
    if (userIdx !== -1) {
      results.push({
        turnIndex: i,
        role: 'User',
        snippet: buildSnippet(userText, userIdx, keyword),
        matchStart: userIdx,
        timestamp: turn.userMessage.timestamp || turn.startTime,
      })
      if (results.length >= 20) break
    }

    // Search assistant steps
    for (const step of turn.assistantSteps) {
      if (results.length >= 20) break
      const stepText = getContentText(step.content)
      const stepIdx = stepText.toLowerCase().indexOf(lowerKeyword)
      if (stepIdx !== -1) {
        results.push({
          turnIndex: i,
          role: 'Assistant',
          snippet: buildSnippet(stepText, stepIdx, keyword),
          matchStart: stepIdx,
          timestamp: step.timestamp || turn.startTime,
        })
      }
    }
  }

  return results
}

export function SearchModal({ turns, onClose }: SearchModalProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [onClose])

  const handleSearch = useCallback((value: string) => {
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setResults(searchTurns(turns, value))
    }, 150)
  }, [turns])

  const handleJump = (turnIndex: number) => {
    onClose()
    requestAnimationFrame(() => {
      const el = document.getElementById(`turn-${turnIndex}`)
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  return (
    <div className="absolute inset-0 z-20 flex items-start justify-center pt-16 bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-lg mx-4 rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)]">
          <Search className="w-4 h-4 text-[var(--text-secondary)]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => handleSearch(e.target.value)}
            placeholder="搜索聊天记录..."
            className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] outline-none"
          />
          <button
            onClick={onClose}
            className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto">
          {query.trim() && results.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-[var(--text-secondary)]">
              无匹配结果
            </div>
          )}
          {results.map((r, i) => (
            <div
              key={i}
              className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg-secondary)] transition-colors group/result"
            >
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0 ${
                r.role === 'User'
                  ? 'bg-[var(--accent)]/20 text-[var(--accent)]'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
              }`}>
                {r.role}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-xs text-[var(--text-primary)] truncate leading-relaxed block">
                  {highlightSnippet(r.snippet, query)}
                </span>
                {formatTimestamp(r.timestamp) && (
                  <span className="text-[10px] text-[var(--text-secondary)] opacity-60">
                    {formatTimestamp(r.timestamp)}
                  </span>
                )}
              </div>
              <button
                onClick={() => handleJump(r.turnIndex)}
                className="p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors opacity-0 group-hover/result:opacity-100"
                title="跳转到此消息"
              >
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        {/* Footer hint */}
        {!query.trim() && (
          <div className="px-4 py-6 text-center text-xs text-[var(--text-secondary)]">
            输入关键词搜索当前会话的聊天记录
          </div>
        )}
      </div>
    </div>
  )
}
