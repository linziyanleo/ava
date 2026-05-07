export interface TokenStatsNavOptions {
  sessionKey?: string | null
  conversationId?: string | null
  turnSeq?: number | string | null
  traceId?: string | null
  spanId?: string | null
}

export function buildTokenStatsNavUrl(options: TokenStatsNavOptions): string {
  const params = new URLSearchParams()
  if (options.sessionKey) params.set('session_key', options.sessionKey)
  if (options.conversationId) params.set('conversation_id', options.conversationId)
  if (options.turnSeq !== null && options.turnSeq !== undefined && options.turnSeq !== '') {
    params.set('turn_seq', String(options.turnSeq))
  }
  if (options.traceId) params.set('trace_id', options.traceId)
  if (options.spanId) params.set('span_id', options.spanId)

  const query = params.toString()
  return query ? `/tokens?${query}` : '/tokens'
}
