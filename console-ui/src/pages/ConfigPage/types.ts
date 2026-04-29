export interface ConfigItem {
  name: string
  path: string
  exists: boolean
}

export interface ConfigData {
  content: string
  mtime: number
  format: string
}

export interface ContextCompressionConfig {
  enabled: boolean
  maxChars: number
  recentTurns: number
  minRecentTurns: number
  maxOldTurns: number
  enableHistoryLookupHint: boolean
  protectedRecentMessages: number
  bootstrapMaxChars: number
}

export interface InLoopTruncationConfig {
  enabled: boolean
  readFile: number
  exec: number
  webFetch: number
  default: number
}

export interface AgentDefaults {
  workspace: string
  model: string
  visionModel: string | null
  miniModel: string | null
  voiceModel: string | null
  imageGenModel: string | null
  memoryTier?: string | null
  provider?: string
  maxTokens: number
  temperature: number
  maxToolIterations: number
  memoryWindow?: number
  reasoningEffort?: string | null
  contextCompression?: ContextCompressionConfig
  inLoopTruncation?: InLoopTruncationConfig
  heartbeat?: HeartbeatConfig
}

export interface ChannelBase {
  enabled: boolean
  [key: string]: unknown
}

export interface ProviderConfig {
  apiKey: string
  apiBase: string | null
  extraHeaders: Record<string, string> | null
}

export interface MCPServerConfig {
  command: string
  args: string[]
  env: Record<string, string>
  url: string
  headers: Record<string, string>
  toolTimeout: number
  enabledTools?: string[]
}

export interface WebSearchConfig {
  apiKey: string
  maxResults: number
}

export interface WebToolsConfig {
  proxy: string | null
  search: WebSearchConfig
}

export interface ExecToolConfig {
  timeout: number
  pathAppend?: string
  autoVenv?: boolean
}

export interface ImageGenToolConfig {
  timeout: number
  background: boolean
  autoContinue: boolean
  autoSend: boolean
}

export interface ToolsConfig {
  web?: WebToolsConfig
  exec?: ExecToolConfig
  imageGen?: ImageGenToolConfig
  restrictToWorkspace: boolean
  restrictConfigFile: boolean
  mcpServers?: Record<string, MCPServerConfig>
}

export interface HeartbeatPhaseConfig {
  model: string
}

export interface HeartbeatConfig {
  enabled: boolean;
  interval_s: number;
  phrase1?: HeartbeatPhaseConfig;
  phrase2?: HeartbeatPhaseConfig;
}

export interface ConsoleConfigType {
  enabled: boolean
  port: number
  secretKey: string
  tokenExpireMinutes: number
}

export interface GatewayConfig {
  host: string
  port: number
  console?: ConsoleConfigType
}

export interface TokenStatsConfig {
  enabled: boolean
  record_full_request_payload: boolean
}

export interface NanobotConfig {
  agents: {
    defaults: AgentDefaults
  }
  token_stats?: TokenStatsConfig
  channels: Record<string, ChannelBase>
  providers: Record<string, ProviderConfig>
  gateway: GatewayConfig
  tools: ToolsConfig
}

// ─── Cron Job Types ──────────────────────────────────────────────────────────

export interface CronSchedule {
  kind: 'at' | 'every' | 'cron'
  atMs: number | null
  everyMs: number | null
  expr: string | null
  tz: string | null
}

export interface CronPayload {
  kind: 'system_event' | 'agent_turn'
  message: string
  deliver: boolean
  channel: string | null
  to: string | null
  modelTier: 'default' | 'mini' | null
}

export interface CronJobState {
  nextRunAtMs: number | null
  lastRunAtMs: number | null
  lastStatus: 'ok' | 'error' | 'skipped' | null
  lastError: string | null
  taskCompletedAtMs: number | null
  taskCycleId: string | null
}

export interface CronJob {
  id: string
  name: string
  enabled: boolean
  schedule: CronSchedule
  payload: CronPayload
  state: CronJobState
  createdAtMs: number
  updatedAtMs: number
  deleteAfterRun: boolean
  source: 'cli' | 'schedule'
}

export interface CronStore {
  version: number
  jobs: CronJob[]
}
