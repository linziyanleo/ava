import type { SceneType, SessionMeta, RawMessage, TurnGroup } from './types'

export interface FileTreeNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileTreeNode[]
}

export function parseScene(filename: string): SceneType {
  const name = filename.replace(/\.jsonl$/, '')
  if (name.startsWith('telegram_')) return 'telegram'
  if (name.startsWith('cron_sched_') || name.startsWith('cron_')) return 'cron'
  if (name === 'heartbeat') return 'heartbeat'
  if (name.startsWith('console_')) return 'console'
  if (name.startsWith('cli_')) return 'cli'
  return 'other'
}

export function parseJsonl(content: string, filename: string): { meta: SessionMeta | null; messages: RawMessage[] } {
  const lines = content.split('\n').filter((l) => l.trim())
  let meta: SessionMeta | null = null
  const messages: RawMessage[] = []

  for (const line of lines) {
    try {
      const data = JSON.parse(line)
      if (data._type === 'metadata') {
        meta = {
          filename,
          filepath: '',
          scene: parseScene(filename),
          key: data.key || filename,
          created_at: data.created_at || '',
          updated_at: data.updated_at || '',
          conversation_id: data.conversation_id || '',
          token_stats: data.token_stats || {
            total_prompt_tokens: 0,
            total_completion_tokens: 0,
            total_tokens: 0,
            llm_calls: 0,
          },
          message_count: 0,
        }
      } else if (data.role) {
        messages.push(data as RawMessage)
      }
    } catch {
      // skip malformed lines
    }
  }

  if (!meta) {
    meta = {
      filename,
      filepath: '',
      scene: parseScene(filename),
      key: filename,
      created_at: '',
      updated_at: '',
      conversation_id: '',
      token_stats: { total_prompt_tokens: 0, total_completion_tokens: 0, total_tokens: 0, llm_calls: 0 },
      message_count: 0,
    }
  }

  return { meta, messages }
}

export function groupTurns(messages: RawMessage[]): TurnGroup[] {
  const turns: TurnGroup[] = []
  let current: TurnGroup | null = null
  let nextTurnSeq = 0

  for (const msg of messages) {
    if (msg.role === 'user') {
      if (current) {
        current.isComplete = checkTurnComplete(current)
        turns.push(current)
      }
      current = {
        turnSeq: nextTurnSeq,
        userMessage: msg,
        assistantSteps: [],
        isComplete: false,
        startTime: msg.timestamp,
        toolCalls: [],
      }
      nextTurnSeq += 1
    } else if (!current) {
      // Orphan assistant/tool message without a preceding user message.
      // Create a turn with a synthetic user placeholder so it still renders.
      current = {
        turnSeq: null,
        userMessage: { role: 'user', content: null, timestamp: msg.timestamp },
        assistantSteps: [],
        isComplete: false,
        startTime: msg.timestamp,
        toolCalls: [],
      }
      current.assistantSteps.push(msg)

      if (msg.role === 'assistant' && msg.tool_calls?.length) {
        for (const tc of msg.tool_calls) {
          current.toolCalls.push({ call: tc, callTimestamp: msg.timestamp })
        }
      }
    } else {
      current.assistantSteps.push(msg)

      if (msg.role === 'assistant' && msg.tool_calls?.length) {
        for (const tc of msg.tool_calls) {
          current.toolCalls.push({ call: tc, callTimestamp: msg.timestamp })
        }
      }

      if (msg.role === 'tool' && msg.tool_call_id) {
        const match = current.toolCalls.find((tc) => tc.call.id === msg.tool_call_id)
        if (match) match.result = msg
      }

      if (msg.role === 'assistant' && msg.content !== null) {
        current.endTime = msg.timestamp
      }
    }
  }

  if (current) {
    current.isComplete = checkTurnComplete(current)
    turns.push(current)
  }

  return turns
}

export function getNextTurnSeq(turns: TurnGroup[]): number {
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const turnSeq = turns[i]?.turnSeq
    if (typeof turnSeq === 'number') {
      return turnSeq + 1
    }
  }
  return 0
}

function checkTurnComplete(turn: TurnGroup): boolean {
  const steps = turn.assistantSteps
  if (steps.length === 0) return false
  const last = steps[steps.length - 1]
  if (last.role === 'assistant' && !last.tool_calls && last.content !== null) return true
  if (last.role === 'assistant' && last.tool_calls?.length && last.content !== null && getContentText(last.content)) return true
  if (last.role === 'tool') {
    const prevAssistant = [...steps].reverse().find((s) => s.role === 'assistant')
    if (prevAssistant?.content != null && getContentText(prevAssistant.content)) return true
  }
  return false
}

export function getContentText(content: string | null | Array<{ type: string; text?: string }>): string {
  if (content === null || content === undefined) return ''
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .filter((c) => c.type === 'text' && c.text)
      .map((c) => c.text!)
      .join('\n')
  }
  return String(content)
}

export function formatTimestamp(ts?: string): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ts
  }
}

export function calcDuration(start?: string, end?: string): string {
  if (!start || !end) return ''
  try {
    const ms = new Date(end).getTime() - new Date(start).getTime()
    if (ms < 0) return ''
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
  } catch {
    return ''
  }
}

export function extractSessionTitle(meta: SessionMeta, messages: RawMessage[]): string {
  const name = (meta.filename ?? meta.key).replace(/\.jsonl$/, '')

  if (meta.scene === 'heartbeat') return 'Heartbeat'

  const idPart = name.replace(/^(telegram|cron_sched|cron|console|cli)_?/, '')

  const firstUser = messages.find((m) => m.role === 'user')
  if (firstUser) {
    const text = getContentText(firstUser.content)
    if (text) {
      const preview = text.slice(0, 40).replace(/\n/g, ' ')
      return preview + (text.length > 40 ? '...' : '')
    }
  }

  return idPart || name
}

export function extractSessionFiles(tree: FileTreeNode): { name: string; path: string }[] {
  const files: { name: string; path: string }[] = []

  if (tree.children) {
    const sessionsDir = tree.children.find((c) => c.name === 'sessions')
    if (sessionsDir?.children) {
      for (const child of sessionsDir.children) {
        if (child.type === 'file' && child.name.endsWith('.jsonl') && !child.name.startsWith('_')) {
          files.push({ name: child.name, path: child.path })
        }
      }
    }
  }

  return files
}

export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

export function imageUrl(path: string): string {
  const filename = path.split('/').pop() || path
  return `/api/media/images/${filename}`
}

const GENERATED_RE = /Generated image\(s\):\s*(.+)/
export function extractImagePaths(resultText: string): string[] {
  const m = GENERATED_RE.exec(resultText)
  if (!m) return []
  return m[1].split(',').map((s) => s.trim()).filter(Boolean)
}
