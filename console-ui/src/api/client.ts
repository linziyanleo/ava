const BASE = '/api'

let onUnauthorized: (() => void) | null = null

function isJsonResponse(res: Response): boolean {
  const contentType = res.headers.get('content-type') || ''
  return /\bapplication\/json\b|\+json\b/i.test(contentType)
}

function describeResponseBody(res: Response, text: string): string {
  const trimmed = text.trimStart().toLowerCase()
  if (trimmed.startsWith('<!doctype') || trimmed.startsWith('<html')) {
    return 'HTML'
  }

  const contentType = res.headers.get('content-type')
  if (contentType) {
    return contentType.split(';')[0].trim() || 'non-JSON'
  }
  return 'non-JSON'
}

async function readJsonResponse<T>(res: Response, path: string): Promise<T> {
  const text = await res.text()
  if (!text.trim()) {
    return undefined as T
  }

  const trimmed = text.trimStart()
  if (!isJsonResponse(res) && !trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    const received = describeResponseBody(res, text)
    throw new Error(
      `Expected JSON from ${BASE}${path} but received ${received} (HTTP ${res.status}). The backend route may be missing or this frontend may be proxying to an older gateway.`,
    )
  }

  try {
    return JSON.parse(text) as T
  } catch (err) {
    const message = err instanceof Error ? err.message : 'parse failed'
    throw new Error(`Invalid JSON from ${BASE}${path}: ${message}`)
  }
}

function getErrorDetail(body: unknown): string | null {
  if (!body || typeof body !== 'object' || !('detail' in body)) {
    return null
  }
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string') {
    return detail
  }
  if (detail == null) {
    return null
  }
  return JSON.stringify(detail)
}

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
    const body = await readJsonResponse<unknown>(res, path).catch(() => ({}))
    throw new Error(getErrorDetail(body) || `HTTP ${res.status}`)
  }

  return readJsonResponse<T>(res, path)
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
