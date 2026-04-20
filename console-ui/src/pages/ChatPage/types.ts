export type SceneType = 'telegram' | 'cron' | 'heartbeat' | 'console' | 'cli' | 'feishu' | 'QQ' | 'wx' | 'discord' | 'other'

export interface SessionMeta {
  key: string
  scene: SceneType
  created_at: string
  updated_at: string
  conversation_id: string
  token_stats: {
    total_prompt_tokens: number
    total_completion_tokens: number
    total_tokens: number
    llm_calls: number
  }
  message_count: number
  filename?: string
  filepath?: string
}

export interface ConversationMeta {
  conversation_id: string
  first_message_preview: string
  message_count: number
  created_at: string
  updated_at: string
  is_active: boolean
  is_legacy?: boolean
}

export interface ToolCall {
  id: string
  type: 'function'
  function: { name: string; arguments: string }
}

export interface RawMessage {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string | null | Array<{ type: string; text?: string }>
  timestamp?: string
  tool_calls?: ToolCall[]
  tool_call_id?: string
  name?: string
  reasoning_content?: string
  metadata?: Record<string, unknown>
}

export interface ToolCallWithResult {
  call: ToolCall
  result?: RawMessage
  callTimestamp?: string
  iteration: number
}

export interface TurnTokenStats {
  conversation_id: string
  turn_seq: number | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  llm_calls: number
  models: string
}

export interface IterationTokenStats {
  conversation_id: string
  turn_seq: number | null
  iteration: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cached_tokens: number
  cache_creation_tokens: number
  model: string
  model_role: string
  tool_names: string
  finish_reason: string
}

export interface TurnGroup {
  turnSeq: number | null
  userMessage: RawMessage
  assistantSteps: RawMessage[]
  isComplete: boolean
  startTime?: string
  endTime?: string
  toolCalls: ToolCallWithResult[]
}

export const SCENE_LABELS: Record<SceneType, string> = {
  telegram: 'Telegram',
  cron: 'Cron',
  heartbeat: 'Heartbeat',
  console: 'Console',
  cli: 'CLI',
  feishu: 'Feishu',
  QQ: 'QQ',
  wx: 'WeChat',
  discord: 'Discord',
  other: 'Other',
}

export const SCENE_ORDER: SceneType[] = ['telegram', 'console', 'cli', 'cron', 'heartbeat', 'other']
