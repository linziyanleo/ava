import type { RawMessage, ToolCall, ToolCallWithResult, TurnGroup } from './types'

export type InFlightTransport = 'console' | 'observe'
export type InFlightPhase = 'pending' | 'thinking' | 'streaming' | 'awaiting_tool'

export interface InFlightToolCall extends ToolCallWithResult {
  isLoading: boolean
}

export type InFlightTurnEntry =
  | { kind: 'assistant'; message: RawMessage }
  | { kind: 'tool'; tool: InFlightToolCall }

export interface InFlightTurn {
  transport: InFlightTransport
  phase: InFlightPhase
  turnSeq: number | null
  conversationId: string | null
  userMessage: RawMessage
  entries: InFlightTurnEntry[]
  draftAssistant: string
  thinkingContent: string
  processing: boolean
}

interface CreateInFlightTurnOptions {
  transport: InFlightTransport
  turnSeq: number | null
  conversationId: string | null
  userMessage: RawMessage
}

function commitAssistantDraft(turn: InFlightTurn): InFlightTurn {
  if (!turn.draftAssistant) return turn
  return {
    ...turn,
    entries: [
      ...turn.entries,
      {
        kind: 'assistant',
        message: {
          role: 'assistant',
          content: turn.draftAssistant,
          timestamp: new Date().toISOString(),
        },
      },
    ],
    draftAssistant: '',
    thinkingContent: '',
  }
}

function settleLastLoadingTool(entries: InFlightTurnEntry[]): InFlightTurnEntry[] {
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    const entry = entries[i]
    if (entry.kind !== 'tool') continue
    if (!entry.tool.isLoading) break
    const next = [...entries]
    next[i] = {
      kind: 'tool',
      tool: {
        ...entry.tool,
        isLoading: false,
      },
    }
    return next
  }
  return entries
}

function stripWrappingQuotes(value: string): string {
  if (
    (value.startsWith('"') && value.endsWith('"'))
    || (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1)
  }
  return value
}

function buildSyntheticToolCall(hint: string, iteration: number): InFlightToolCall {
  const trimmed = hint.trim()
  let name = trimmed || 'tool'
  let args: Record<string, string> = {}

  if (trimmed.startsWith('fetch ')) {
    name = 'web_fetch'
    args = { url: trimmed.slice('fetch '.length).trim() }
  } else if (trimmed.startsWith('search ')) {
    name = 'web_search'
    args = { query: stripWrappingQuotes(trimmed.slice('search '.length).trim()) }
  } else if (trimmed.startsWith('$ ')) {
    name = 'exec'
    args = { command: trimmed.slice(2).trim() }
  } else if (trimmed.startsWith('read ')) {
    name = 'read_file'
    args = { path: trimmed.slice('read '.length).trim() }
  } else if (trimmed.startsWith('write ')) {
    name = 'write_file'
    args = { path: trimmed.slice('write '.length).trim() }
  } else if (trimmed.startsWith('edit ')) {
    name = 'edit'
    args = { file_path: trimmed.slice('edit '.length).trim() }
  } else if (trimmed.startsWith('ls ')) {
    name = 'list_dir'
    args = { path: trimmed.slice('ls '.length).trim() }
  } else if (trimmed.startsWith('glob ')) {
    name = 'glob'
    args = { pattern: stripWrappingQuotes(trimmed.slice('glob '.length).trim()) }
  } else if (trimmed.startsWith('grep ')) {
    name = 'grep'
    args = { pattern: stripWrappingQuotes(trimmed.slice('grep '.length).trim()) }
  } else if (trimmed.includes('::')) {
    name = trimmed.split('(', 1)[0]?.trim() || trimmed
  }

  return {
    call: {
      id: `live-tool-${iteration}-${Math.random().toString(36).slice(2, 10)}`,
      type: 'function',
      function: {
        name,
        arguments: JSON.stringify(args),
      },
    } satisfies ToolCall,
    iteration,
    isLoading: true,
  }
}

export function createInFlightTurn({
  transport,
  turnSeq,
  conversationId,
  userMessage,
}: CreateInFlightTurnOptions): InFlightTurn {
  return {
    transport,
    phase: 'pending',
    turnSeq,
    conversationId,
    userMessage,
    entries: [],
    draftAssistant: '',
    thinkingContent: '',
    processing: true,
  }
}

export function appendInFlightThinking(turn: InFlightTurn, chunk: string): InFlightTurn {
  return {
    ...turn,
    phase: 'thinking',
    processing: true,
    thinkingContent: turn.thinkingContent + chunk,
  }
}

export function appendInFlightAssistantChunk(turn: InFlightTurn, chunk: string): InFlightTurn {
  return {
    ...turn,
    phase: 'streaming',
    processing: true,
    entries: settleLastLoadingTool(turn.entries),
    draftAssistant: turn.draftAssistant + chunk,
  }
}

export function appendInFlightToolHint(turn: InFlightTurn, hint: string): InFlightTurn {
  const committed = commitAssistantDraft(turn)
  const nextIteration = committed.entries.filter((entry) => entry.kind === 'tool').length
  return {
    ...committed,
    phase: 'awaiting_tool',
    processing: true,
    entries: [
      ...committed.entries,
      {
        kind: 'tool',
        tool: buildSyntheticToolCall(hint, nextIteration),
      },
    ],
  }
}

export function applyInFlightStreamEnd(turn: InFlightTurn, resuming: boolean): InFlightTurn {
  const committed = commitAssistantDraft(turn)
  return {
    ...committed,
    phase: resuming ? 'awaiting_tool' : 'pending',
    processing: true,
  }
}

export function markInFlightProcessing(turn: InFlightTurn, processing: boolean): InFlightTurn {
  return {
    ...turn,
    processing,
  }
}

export function finalizeInFlightTurn(turn: InFlightTurn): InFlightTurn {
  const committed = commitAssistantDraft(turn)
  return {
    ...committed,
    entries: settleLastLoadingTool(committed.entries),
    phase: 'pending',
    processing: false,
  }
}

export function materializeInFlightTurn(turn: InFlightTurn): TurnGroup {
  const finalized = finalizeInFlightTurn(turn)
  const assistantSteps: RawMessage[] = []
  const toolCalls: ToolCallWithResult[] = []
  let endTime = finalized.userMessage.timestamp

  for (const entry of finalized.entries) {
    if (entry.kind === 'assistant') {
      assistantSteps.push(entry.message)
      if (entry.message.timestamp) endTime = entry.message.timestamp
      continue
    }

    toolCalls.push({
      call: entry.tool.call,
      result: entry.tool.result,
      callTimestamp: entry.tool.result?.timestamp,
      iteration: entry.tool.iteration,
    })

    if (entry.tool.result) {
      assistantSteps.push(entry.tool.result)
      if (entry.tool.result.timestamp) endTime = entry.tool.result.timestamp
    }
  }

  return {
    turnSeq: finalized.turnSeq,
    userMessage: finalized.userMessage,
    assistantSteps,
    isComplete: true,
    startTime: finalized.userMessage.timestamp,
    endTime,
    toolCalls,
  }
}

export function upsertInFlightTurn(
  turns: TurnGroup[],
  turn: InFlightTurn,
): TurnGroup[] {
  const materialized = materializeInFlightTurn(turn)
  if (typeof materialized.turnSeq === 'number') {
    const existingIndex = turns.findIndex((item) => item.turnSeq === materialized.turnSeq)
    if (existingIndex >= 0) {
      const nextTurns = [...turns]
      nextTurns[existingIndex] = materialized
      return nextTurns
    }
  }
  return [...turns, materialized]
}
