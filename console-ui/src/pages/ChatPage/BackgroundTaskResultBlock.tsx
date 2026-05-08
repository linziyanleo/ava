import { useMemo } from 'react'
import type { DirectTaskMessage, DirectTaskStatus, DirectTaskType } from './types'
import { parseBackgroundTaskMessage } from './backgroundTask'
import { ConversationTaskCard } from './ConversationTaskCard'

// eslint-disable-next-line react-refresh/only-export-components
export function getBackgroundTaskPreview(content: string): string {
  const parsed = parseBackgroundTaskMessage(content)
  if (!parsed?.body) return ''
  const firstLine = parsed.body.split('\n').find((line) => line.trim())
  if (!firstLine) return ''
  return firstLine.length > 90 ? `${firstLine.slice(0, 90)}...` : firstLine
}

interface BackgroundTaskResultBlockProps {
  content: string
  timestamp?: string
  taskId?: string
  sessionKey?: string
  conversationId?: string | null
  highlighted?: boolean
}

const TASK_TYPE_ALIASES: Record<string, DirectTaskType> = {
  claude_code: 'claude_code',
  'claude-code': 'claude_code',
  claude: 'claude_code',
  codex: 'codex',
  image_gen: 'image_gen',
  'image-gen': 'image_gen',
  image: 'image_gen',
  skill: 'skill',
}

function normalizeTaskType(raw: string): DirectTaskType {
  return TASK_TYPE_ALIASES[raw.trim().toLowerCase()] || 'skill'
}

function normalizeStatus(raw: string): DirectTaskStatus {
  const value = raw.trim().toLowerCase()
  if (value === 'success' || value === 'completed' || value === 'complete') return 'succeeded'
  if (value === 'failure' || value === 'error') return 'failed'
  if (value === 'canceled') return 'cancelled'
  if (value === 'queued' || value === 'running' || value === 'streaming' || value === 'pending' || value === 'skipped') return value
  return value === 'awaiting_deps' ? 'awaiting_deps' : 'failed'
}

export function BackgroundTaskResultBlock({ content, timestamp, taskId: taskIdProp, sessionKey = '', highlighted }: BackgroundTaskResultBlockProps) {
  const parsed = parseBackgroundTaskMessage(content)
  const task = useMemo<DirectTaskMessage | null>(() => {
    if (!parsed) return null
    const taskId = taskIdProp ?? parsed.taskId
    return {
      type: 'direct_task',
      task_id: taskId,
      task_type: normalizeTaskType(parsed.taskType),
      session_key: sessionKey,
      prompt_preview: getBackgroundTaskPreview(content) || `${parsed.taskType}:${taskId}`,
      status: normalizeStatus(parsed.status),
      started_at: null,
      elapsed_ms: parsed.durationMs ?? 0,
      result_preview: '',
      error_message: normalizeStatus(parsed.status) === 'failed' ? getBackgroundTaskPreview(content) : '',
    }
  }, [content, parsed, sessionKey, taskIdProp])

  if (!parsed || !task) return null

  return (
    <ConversationTaskCard
      task={task}
      variant="result"
      highlighted={highlighted}
      details={{
        body: parsed.body,
        timestamp,
        defaultExpanded: parsed.body.length <= 220,
      }}
    />
  )
}
