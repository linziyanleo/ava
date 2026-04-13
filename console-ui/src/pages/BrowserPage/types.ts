/** WebSocket 推送事件类型 */
export interface ScreencastFrame {
  type: 'frame'
  session_id: string
  data: string // base64 JPEG
  metadata?: { timestamp?: number }
}

export interface ActivityEvent {
  type: 'activity'
  session_id: string
  activity: {
    type: 'thinking' | 'executing' | 'executed' | 'retrying' | 'error'
    tool?: string
    input?: Record<string, unknown>
    output?: string
    duration_ms?: number
  }
}

export interface StatusEvent {
  type: 'status'
  session_id: string
  status: 'idle' | 'running' | 'completed' | 'error'
}

export interface PageInfoEvent {
  type: 'page_info'
  session_id: string
  page_url: string
  page_title?: string
  viewport?: string
}

export interface StepEvent {
  type: 'step'
  session_id: string
  reflection?: {
    evaluation_previous_goal?: string
    memory?: string
    next_goal?: string
  }
  action?: {
    tool?: string
    input?: Record<string, unknown>
    output?: string
  }
}

export type PageAgentEvent = ScreencastFrame | ActivityEvent | StatusEvent | PageInfoEvent | StepEvent

/** Activity 面板中的事件条目 */
export interface ActivityEntry {
  id: string
  timestamp: number
  type: ActivityEvent['activity']['type']
  tool?: string
  detail?: string
}
