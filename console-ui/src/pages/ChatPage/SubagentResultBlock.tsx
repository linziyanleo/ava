import { useState } from 'react'
import { ChevronDown, ChevronRight, CheckCircle, XCircle, Bot } from 'lucide-react'
import { cn } from '../../lib/utils'

interface SubagentResult {
  label: string
  status: 'completed' | 'failed'
  task: string
  result: string
}

function parseSubagentContent(content: string): SubagentResult | null {
  // Match: [Subagent 'label' completed successfully] or [Subagent 'label' failed]
  const headerMatch = content.match(/^\[Subagent '(.+?)' (completed successfully|failed)\]/)
  if (!headerMatch) return null

  const label = headerMatch[1]
  const status: 'completed' | 'failed' = headerMatch[2] === 'completed successfully' ? 'completed' : 'failed'

  const taskMatch = content.match(/\nTask: ([\s\S]+?)\n\nResult:\n?([\s\S]*)$/)
  const task = taskMatch ? taskMatch[1].trim() : ''
  const result = taskMatch ? taskMatch[2].trim() : ''

  return { label, status, task, result }
}

// eslint-disable-next-line react-refresh/only-export-components
export function isSubagentMessage(content: string | null | unknown[]): boolean {
  if (typeof content !== 'string') return false
  return content.startsWith("[Subagent '")
}

interface SubagentResultBlockProps {
  content: string
  metadata?: Record<string, unknown>
}

export function SubagentResultBlock({ content }: SubagentResultBlockProps) {
  const [taskExpanded, setTaskExpanded] = useState(true)
  const [resultExpanded, setResultExpanded] = useState(false)

  const parsed = parseSubagentContent(content)
  if (!parsed) return null

  const { label, status, task, result } = parsed
  const isCompleted = status === 'completed'

  return (
    <div className={cn(
      'my-1.5 rounded-lg border text-xs overflow-hidden',
      isCompleted
        ? 'border-emerald-500/30 bg-emerald-500/5'
        : 'border-red-500/30 bg-red-500/5',
    )}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2">
        <Bot className="w-3.5 h-3.5 shrink-0 text-[var(--text-secondary)]" />
        <span className="font-medium text-[var(--text-primary)] truncate">{label} ...</span>
        <span className={cn(
          'ml-auto shrink-0 flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
          isCompleted
            ? 'bg-emerald-500/15 text-emerald-400'
            : 'bg-red-500/15 text-red-400',
        )}>
          {isCompleted
            ? <CheckCircle className="w-3 h-3" />
            : <XCircle className="w-3 h-3" />}
          {isCompleted ? 'completed' : 'failed'}
        </span>
      </div>

      <div className="px-3 pb-2.5 space-y-1.5 border-t border-[var(--border)]">
        {/* Task section */}
        {task && (
          <div>
            <button
              onClick={() => setTaskExpanded(!taskExpanded)}
              className="flex items-center gap-1 py-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors w-full text-left"
            >
              {taskExpanded
                ? <ChevronDown className="w-3 h-3 shrink-0" />
                : <ChevronRight className="w-3 h-3 shrink-0" />}
              <span className="font-medium">Task</span>
            </button>
            {taskExpanded && (
              <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-32 overflow-y-auto">
                {task}
              </pre>
            )}
          </div>
        )}

        {/* Result section */}
        {result && (
          <div>
            <button
              onClick={() => setResultExpanded(!resultExpanded)}
              className="flex items-center gap-1 py-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors w-full text-left"
            >
              {resultExpanded
                ? <ChevronDown className="w-3 h-3 shrink-0" />
                : <ChevronRight className="w-3 h-3 shrink-0" />}
              <span className="font-medium">Result</span>
              {!resultExpanded && (
                <span className="ml-1.5 text-[var(--text-secondary)] truncate">
                  — {result.length > 80 ? result.slice(0, 80) + '...' : result}
                </span>
              )}
            </button>
            {resultExpanded && (
              <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-64 overflow-y-auto">
                {result}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
