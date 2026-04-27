const BASE = '/api'

let onUnauthorized: (() => void) | null = null

export function setOnUnauthorized(cb: () => void) {
  onUnauthorized = cb
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...((options.headers as Record<string, string>) || {}),
  }
  if (isFormData) delete headers['Content-Type']

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (res.status === 401) {
    if (onUnauthorized && !path.startsWith('/auth/')) {
      onUnauthorized()
    }
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }

  return res.json()
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${BASE}${path}`
}

export interface TraceTokenUsage {
  id: number
  timestamp: string
  model: string
  provider: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  trace_id: string
  span_id: string
  parent_span_id: string
}

export interface TraceSpanRecord {
  id: number
  trace_id: string
  span_id: string
  parent_span_id: string
  name: string
  operation_name: string
  kind: string
  status: string
  status_message: string
  start_ns: number
  end_ns: number | null
  duration_ms: number | null
  session_key: string
  conversation_id: string
  turn_seq: number | null
  attributes: Record<string, unknown>
  events: Array<Record<string, unknown>>
  token_usage: TraceTokenUsage[]
  children: TraceSpanRecord[]
  depth: number
}

export interface TraceDetail {
  trace_id: string
  spans: TraceSpanRecord[]
  tree: TraceSpanRecord[]
  token_usage: TraceTokenUsage[]
}

export interface TraceListItem {
  trace_id: string
  start_ns: number
  end_ns: number
  span_count: number
  open_spans: number
  has_error: number
  has_interrupted: number
}

export function getTrace(traceId: string): Promise<TraceDetail> {
  return api<TraceDetail>(`/stats/traces/${encodeURIComponent(traceId)}`)
}

export function listTraces(filters: { session_key?: string; turn_seq?: number; limit?: number } = {}) {
  const params = new URLSearchParams()
  if (filters.session_key) params.set('session_key', filters.session_key)
  if (filters.turn_seq != null) params.set('turn_seq', String(filters.turn_seq))
  if (filters.limit != null) params.set('limit', String(filters.limit))
  const query = params.toString()
  return api<{ traces: TraceListItem[] }>(`/stats/traces${query ? `?${query}` : ''}`)
}
