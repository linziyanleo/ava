import type { RawMessage } from './types'

const BG_TASK_ASSISTANT_RE =
  /^\[Background Task ([A-Za-z0-9_-]+) ([A-Z_]+)\]\nType: ([^|\n]+?) \| Duration: (\d+)ms(?:\n\n([\s\S]*))?$/
const BG_TASK_CONTINUATION_RE =
  /^\[Background Task Completed — ([A-Z_]+)\]\nTask: ([^:\n]+):([A-Za-z0-9_-]+)\nDuration: (\d+)ms(?:\n\n([\s\S]*))?$/
const CONTINUATION_TAIL = '请基于以上结果继续处理后续步骤。如果所有工作已完成，请总结。'

export interface BackgroundTaskMessage {
  kind: 'assistant' | 'continuation'
  taskId: string
  taskType: string
  status: string
  durationMs: number | null
  body: string
}

function stripContinuationTail(body: string): string {
  const trimmed = body.trim()
  if (!trimmed.endsWith(CONTINUATION_TAIL)) return trimmed
  return trimmed.slice(0, -CONTINUATION_TAIL.length).trimEnd()
}

export function parseBackgroundTaskMessage(
  content: string | null | unknown[],
): BackgroundTaskMessage | null {
  if (typeof content !== 'string') return null

  const assistantMatch = content.match(BG_TASK_ASSISTANT_RE)
  if (assistantMatch) {
    return {
      kind: 'assistant',
      taskId: assistantMatch[1],
      status: assistantMatch[2],
      taskType: assistantMatch[3].trim(),
      durationMs: Number(assistantMatch[4]) || null,
      body: (assistantMatch[5] || '').trim(),
    }
  }

  const continuationMatch = content.match(BG_TASK_CONTINUATION_RE)
  if (continuationMatch) {
    return {
      kind: 'continuation',
      status: continuationMatch[1],
      taskType: continuationMatch[2].trim(),
      taskId: continuationMatch[3],
      durationMs: Number(continuationMatch[4]) || null,
      body: stripContinuationTail(continuationMatch[5] || ''),
    }
  }

  return null
}

// eslint-disable-next-line react-refresh/only-export-components
export function isBackgroundTaskMessage(content: string | null | unknown[]): boolean {
  return parseBackgroundTaskMessage(content) !== null
}

function isSameEvent(a: BackgroundTaskMessage, b: BackgroundTaskMessage): boolean {
  if (a.taskId !== b.taskId || a.taskType !== b.taskType || a.status !== b.status) return false
  if (a.durationMs == null || b.durationMs == null) return true
  return a.durationMs === b.durationMs
}

function isSameDisplayMessage(a: BackgroundTaskMessage, b: BackgroundTaskMessage): boolean {
  return isSameEvent(a, b) && a.body === b.body
}

export function normalizeBackgroundTaskMessages(messages: RawMessage[]): RawMessage[] {
  const normalized: RawMessage[] = []

  for (let i = 0; i < messages.length; i += 1) {
    const message = messages[i]
    const parsed = parseBackgroundTaskMessage(message.content)

    if (!parsed) {
      normalized.push(message)
      continue
    }

    if (parsed.kind === 'assistant') {
      const nextParsed = parseBackgroundTaskMessage(messages[i + 1]?.content ?? null)
      if (nextParsed?.kind === 'continuation' && isSameEvent(parsed, nextParsed)) {
        continue
      }
      normalized.push(message)
      continue
    }

    const previousParsed = parseBackgroundTaskMessage(normalized[normalized.length - 1]?.content ?? null)
    if (previousParsed?.kind === 'continuation' && isSameDisplayMessage(previousParsed, parsed)) {
      continue
    }

    normalized.push(message)
  }

  return normalized
}
