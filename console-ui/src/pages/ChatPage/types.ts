export type SceneType = 'telegram' | 'cron' | 'heartbeat' | 'console' | 'cli' | 'feishu' | 'QQ' | 'wx' | 'discord' | 'other'
export type ChatStreamStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed' | 'error'
export type ActiveChatTransport = 'console' | 'observe' | 'none'

export interface MessageContentBlock {
  type: string
  text?: string
  [key: string]: unknown
}

export interface ChatComposePayload {
  text: string
  attachments: File[]
}

export type DirectTaskType = 'codex' | 'claude_code' | 'image_gen' | 'skill'
export type DirectTaskStatus =
  | 'pending'
  | 'awaiting_deps'
  | 'queued'
  | 'running'
  | 'streaming'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'skipped'

export interface DirectTaskSubmitParams {
  task_type: DirectTaskType
  prompt: string
  project_path?: string
  params?: {
    mode?: 'standard' | 'readonly'
    session_id?: string
    auto_continue?: boolean
    continue_after_completion?: boolean
    reference_image?: string
  }
}

export interface DirectTaskMessage {
  type: 'direct_task'
  task_id: string
  task_type: DirectTaskType
  session_key: string
  prompt_preview: string
  status: DirectTaskStatus
  started_at: number | null
  elapsed_ms: number
  result_preview?: string
  error_message?: string
  origin_conversation_id?: string
  origin_turn_seq?: number | null
  progress_percent?: number
  artifact_preview?: string
  artifact_uri?: string
  trace_id?: string
  chain_id?: string
  parent_task_ids?: string[]
  node_kind?: string
  skill_name?: string
  matched_by?: 'natural_language' | 'explicit'
}

export interface ChatFileUpload {
  filename: string
  media_path: string
  path: string
  mime_type: string
  kind: 'image' | 'file'
  size_bytes: number
  preview_url: string | null
  download_url: string
}

export interface SessionMeta {
  key: string
  title?: string
  scene: SceneType
  created_at: string
  updated_at: string
  conversation_id: string
  participants: string[]
  default_responder_agent_id: string
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
  content: string | null | MessageContentBlock[]
  timestamp?: string
  tool_calls?: ToolCall[]
  tool_call_id?: string
  name?: string
  reasoning_content?: string
  trace_id?: string
  from_agent_id?: string
  mentioned_agent_ids?: string[]
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
  trace_id?: string
  span_id?: string
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
  trace_id?: string
  span_id?: string
  parent_span_id?: string
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

export interface ContextPreviewWindow {
  strategy: string
  kept_count: number
  dropped_count: number
  kept_tokens: number
  estimate_scope: string
  replay_max_messages?: number | null
  replay_max_tokens?: number | null
  runner_snipped?: boolean | null
  consolidated_count?: number | null
  summary_present?: boolean | null
  oldest_kept_msg_id?: string | null
  oldest_dropped_msg_id?: string | null
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
    estimate_scope?: string
  }
  window?: ContextPreviewWindow
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
