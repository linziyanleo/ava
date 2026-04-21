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

export interface ContextPreviewSection {
  name: string
  source: string
  content: string
  tokens: number
  truncated: boolean
}

export interface ContextPreviewBlock {
  type: string
  text?: string
  image_url?: { url: string }
  value?: unknown
  [key: string]: unknown
}

export interface ContextPreviewMessage {
  role: 'user' | 'assistant' | 'tool' | 'system' | string
  content: string
  content_type: 'text' | 'blocks'
  content_blocks: ContextPreviewBlock[] | null
  tool_calls?: ToolCall[] | null
  tool_call_id?: string | null
  name?: string | null
  tokens: number
  truncated: boolean
}

export interface ContextPreview {
  snapshot_ts: string
  session_key: string
  workspace: string
  provider: {
    name: string
    model: string
  }
  scope: string
  system_sections: ContextPreviewSection[]
  runtime_context: {
    content: string
    tokens: number
    truncated: boolean
  }
  messages: ContextPreviewMessage[]
  tools: {
    count: number
    tokens: number
    names: string[]
  }
  totals: {
    system_tokens: number
    runtime_tokens: number
    history_tokens: number
    tool_tokens: number
    request_total_tokens: number
    context_window: number
    max_completion_tokens: number
    ctx_budget: number
    utilization_pct: number
  }
  flags: {
    sanitized: boolean
    full: boolean
    reveal: boolean
    streaming: boolean
    in_flight: boolean
  }
  notes: string[]
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
