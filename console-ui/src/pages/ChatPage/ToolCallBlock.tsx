import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, ChevronRight, Wrench, Loader2, Image, Eye, Mic, Globe, ExternalLink, Clock } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { ToolCallWithResult, TurnTokenStats, IterationTokenStats } from './types'
import { getContentText, imageUrl, extractImagePaths, formatTokenCount, formatTimestamp, calcDuration } from './utils'
import { ImageCarousel } from './ImageCarousel'
import { api } from '../../api/client'

interface MediaRecord {
  id: string
  output_images: string[]
  prompt: string
  status: string
}

interface MediaResponse {
  records: MediaRecord[]
}

interface ToolCallBlockProps {
  tc: ToolCallWithResult
  isLoading: boolean
  tokenStats?: TurnTokenStats
  iterationStats?: IterationTokenStats
  sessionKey?: string
  conversationId?: string
  turnSeq?: number | null
  callTimestamp?: string
  resultTimestamp?: string
}

const MEDIA_TOOLS: Record<string, { icon: typeof Image; label: string; color: string }> = {
  image_gen: { icon: Image, label: 'Image Generation', color: 'text-purple-400' },
  vision: { icon: Eye, label: 'Image Analysis', color: 'text-blue-400' },
  analyze_image: { icon: Eye, label: 'Image Analysis', color: 'text-blue-400' },
  transcribe: { icon: Mic, label: 'Voice Transcription', color: 'text-green-400' },
}

interface ClaudeCodeResult {
  status: string
  turns: number
  duration: string
  cost: string
  session: string
  body: string
}

function parseClaudeCodeResult(text: string): ClaudeCodeResult | null {
  const statusMatch = text.match(/\[Claude Code (\w+)\]/)
  if (!statusMatch) return null

  const metaMatch = text.match(/Turns:\s*(\d+)\s*\|\s*Duration:\s*(\d+)ms\s*\|\s*Cost:\s*\$([0-9.]+)/)
  const sessionMatch = text.match(/Session:\s*([a-f0-9-]+)/)

  const headerEnd = text.indexOf('\n\n')
  const body = headerEnd >= 0 ? text.slice(headerEnd + 2).trim() : ''

  return {
    status: statusMatch[1],
    turns: metaMatch ? parseInt(metaMatch[1]) : 0,
    duration: metaMatch ? `${(parseInt(metaMatch[2]) / 1000).toFixed(1)}s` : '?',
    cost: metaMatch ? `$${metaMatch[3]}` : '?',
    session: sessionMatch ? sessionMatch[1] : '',
    body,
  }
}

interface CodexResult {
  status: string
  turns: number
  duration: string
  runId: string
  body: string
}

function parseCodexResult(text: string): CodexResult | null {
  const statusMatch = text.match(/\[Codex (\w+)\]/)
  if (!statusMatch) return null

  const metaMatch = text.match(/Turns:\s*(\d+)\s*\|\s*Duration:\s*(\d+)ms/)
  const runMatch = text.match(/^(?:Run|Thread):\s*(.+)$/m)

  const headerEnd = text.indexOf('\n\n')
  const body = headerEnd >= 0 ? text.slice(headerEnd + 2).trim() : ''

  return {
    status: statusMatch[1],
    turns: metaMatch ? parseInt(metaMatch[1]) : 0,
    duration: metaMatch ? `${(parseInt(metaMatch[2]) / 1000).toFixed(1)}s` : '?',
    runId: runMatch ? runMatch[1].trim() : '',
    body,
  }
}

interface PageAgentResult {
  status: string
  steps: number
  duration: string
  sessionId: string
  url: string
  title: string
  body: string
}

function parsePageAgentResult(text: string): PageAgentResult | null {
  const statusMatch = text.match(/\[PageAgent (\w+)\]/)
  if (!statusMatch) return null

  const sessionMatch = text.match(/session=(\S+?)(?:\s*\||\s*$)/m)
  const stepsMatch = text.match(/Steps:\s*(\d+)/)
  const durationMatch = text.match(/Duration:\s*(\d+)ms/)
  const urlMatch = text.match(/^URL:\s*(.+)/m)
  const titleMatch = text.match(/^Title:\s*(.+)/m)

  const bodyStart = text.indexOf('\n\n')
  const body = bodyStart >= 0 ? text.slice(bodyStart + 2).trim() : ''

  return {
    status: statusMatch[1],
    steps: stepsMatch ? parseInt(stepsMatch[1]) : 0,
    duration: durationMatch ? `${(parseInt(durationMatch[1]) / 1000).toFixed(1)}s` : '?',
    sessionId: sessionMatch ? sessionMatch[1] : '',
    url: urlMatch ? urlMatch[1].trim() : '',
    title: titleMatch ? titleMatch[1].trim() : '',
    body,
  }
}

function stringifyToolResult(content: unknown): string | null {
  if (content === null || content === undefined) return null
  if (typeof content === 'string' || Array.isArray(content)) {
    return getContentText(content)
  }
  try {
    return JSON.stringify(content, null, 2)
  } catch {
    return String(content)
  }
}

function TokenStatsLink({
  sessionKey,
  conversationId,
  turnSeq,
}: {
  sessionKey?: string
  conversationId?: string
  turnSeq?: number | null
}) {
  const navigate = useNavigate()

  if (!sessionKey || turnSeq == null) return null

  return (
    <button
      onClick={() => {
        const params = new URLSearchParams({ session_key: sessionKey })
        if (conversationId) params.set('conversation_id', conversationId)
        params.set('turn_seq', String(turnSeq))
        navigate(`/tokens?${params.toString()}`)
      }}
      className="inline-flex items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-tertiary)] px-2 py-1 text-[10px] text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
      title="查看当前工具块对应的 Token 统计"
    >
      <ExternalLink className="w-3 h-3" />
      <span>Token 统计</span>
    </button>
  )
}

export function ToolCallBlock({
  tc,
  isLoading,
  tokenStats,
  iterationStats,
  sessionKey,
  conversationId,
  turnSeq,
  callTimestamp,
  resultTimestamp,
}: ToolCallBlockProps) {
  const callDuration = calcDuration(callTimestamp, resultTimestamp)

  const metaBar = (callTimestamp || callDuration || iterationStats) ? (
    <div className="flex items-center gap-2 px-3 py-1 text-[10px] text-[var(--text-secondary)]">
      {callTimestamp && (
        <span className="inline-flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {formatTimestamp(callTimestamp)}
        </span>
      )}
      {callDuration && (
        <span className="text-[var(--accent)]">({callDuration})</span>
      )}
      {iterationStats && (
        <span className="font-mono" title={`In: ${formatTokenCount(iterationStats.prompt_tokens)} / Out: ${formatTokenCount(iterationStats.completion_tokens)}${iterationStats.cached_tokens ? ` / Cache: ${formatTokenCount(iterationStats.cached_tokens)}` : ''}`}>
          ⚡ {formatTokenCount(iterationStats.total_tokens)}
        </span>
      )}
      {iterationStats?.model && (
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)]">{iterationStats.model}</span>
      )}
    </div>
  ) : null

  const [expanded, setExpanded] = useState(false)

  const fnName = tc.call.function.name
  const mediaTool = MEDIA_TOOLS[fnName]
  let args = ''
  let parsedArgs: Record<string, unknown> = {}
  try {
    parsedArgs = JSON.parse(tc.call.function.arguments)
    args = JSON.stringify(parsedArgs, null, 2)
  } catch {
    args = tc.call.function.arguments
  }

  const resultText = tc.result ? stringifyToolResult(tc.result.content) : null
  let resultPreview = ''
  if (resultText) {
    resultPreview = resultText.length > 120 ? resultText.slice(0, 120) + '...' : resultText
  }

  const regexImageUrls = useMemo(() => {
    if (fnName === 'image_gen' && resultText) {
      const refImg = parsedArgs.reference_image as string | undefined
      const refUrls = refImg && (refImg.startsWith('/') || refImg.startsWith('~'))
        ? [imageUrl(refImg)]
        : []
      return [...refUrls, ...extractImagePaths(resultText).map((p) => imageUrl(p))]
    }
    if ((fnName === 'vision' || fnName === 'analyze_image') && parsedArgs.url) {
      const u = parsedArgs.url as string
      if (u.startsWith('http://') || u.startsWith('https://')) return [u]
      if (u.startsWith('/') || u.startsWith('~')) return [imageUrl(u)]
    }
    return []
  }, [fnName, resultText, parsedArgs.url, parsedArgs.reference_image])

  const [apiImageUrls, setApiImageUrls] = useState<string[]>([])
  const prompt = (parsedArgs.prompt || '') as string

  useEffect(() => {
    if (fnName !== 'image_gen' || regexImageUrls.length > 0 || !prompt) return
    if (!resultText && !tc.result) return
    let cancelled = false
    const searchTerm = prompt.slice(0, 60)
    api<MediaResponse>(`/media/records?search=${encodeURIComponent(searchTerm)}&size=5`)
      .then((res) => {
        if (cancelled) return
        const match = res.records.find(
          (r) => r.status === 'success' && r.prompt === prompt && r.output_images.length > 0,
        )
        if (match) {
          setApiImageUrls(match.output_images.map((p) => imageUrl(p)))
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [fnName, prompt, regexImageUrls.length, resultText, tc.result])

  const mediaImageUrls = regexImageUrls.length > 0 ? regexImageUrls : apiImageUrls
  const effectiveConversationId = conversationId || iterationStats?.conversation_id || tokenStats?.conversation_id || ''

  if (fnName === 'claude_code') {
    const prompt = (parsedArgs.prompt || '') as string
    const mode = (parsedArgs.mode || 'standard') as string
    const projectPath = (parsedArgs.project_path || '') as string
    const sessionArg = (parsedArgs.session_id || '') as string
    const ccResult = resultText ? parseClaudeCodeResult(resultText) : null
    const isSuccess = ccResult?.status === 'SUCCESS'

    return (
      <div>
        {metaBar}
        <div className={cn(
          'rounded-lg border text-xs overflow-hidden',
          isSuccess ? 'border-cyan-500/30 bg-cyan-500/5' : 'border-[var(--border)] bg-[var(--bg-primary)]/50',
        )}>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 w-full px-3 py-2 text-left hover:bg-[var(--bg-tertiary)]/30 transition-colors"
        >
          {isLoading ? (
            <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-cyan-400" />
          ) : expanded ? (
            <ChevronDown className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          ) : (
            <ChevronRight className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          )}
          <span className="text-base shrink-0">💻</span>
          <span className="font-medium text-cyan-400">Claude Code</span>
          {mode === 'readonly' && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium ml-1 bg-blue-500/15 text-blue-400">
              readonly
            </span>
          )}
          {ccResult && (
            <span className="flex items-center gap-2 ml-2 text-[var(--text-secondary)]">
              <span>{ccResult.turns} turns</span>
              <span>{ccResult.duration}</span>
              <span className="text-amber-400">{ccResult.cost}</span>
            </span>
          )}
          {!expanded && prompt && (
            <span className="text-[var(--text-secondary)] truncate ml-2">— {prompt.slice(0, 60)}{prompt.length > 60 ? '...' : ''}</span>
          )}
        </button>

        {expanded && (
          <div className="px-3 pb-3 space-y-2 border-t border-[var(--border)]">
            {/* Metadata bar */}
            {ccResult && (
              <div className="flex flex-wrap gap-3 pt-2 text-[10px]">
                <div className={cn(
                  'px-2 py-1 rounded-md font-medium',
                  isSuccess ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400',
                )}>
                  {ccResult.status}
                </div>
                <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                  <span>Turns:</span>
                  <span className="text-[var(--text-primary)] font-medium">{ccResult.turns}</span>
                </div>
                <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                  <span>Duration:</span>
                  <span className="text-[var(--text-primary)] font-medium">{ccResult.duration}</span>
                </div>
                <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                  <span>Cost:</span>
                  <span className="text-amber-400 font-medium">{ccResult.cost}</span>
                </div>
                {ccResult.session && (
                  <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                    <span>Session:</span>
                    <span className="font-mono text-[9px]">{ccResult.session.slice(0, 8)}...</span>
                  </div>
                )}
              </div>
            )}

            {/* Prompt */}
            <div className="pt-1">
              <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Prompt</div>
              <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-48 overflow-y-auto">
                {prompt}
              </pre>
            </div>

            {/* Config */}
            {(projectPath || sessionArg) && (
              <div className="flex flex-wrap gap-3 text-[10px] text-[var(--text-secondary)]">
                {projectPath && <span>Project: <span className="font-mono text-[var(--text-primary)]">{projectPath}</span></span>}
                {sessionArg && <span>Resume: <span className="font-mono text-[var(--text-primary)]">{sessionArg.slice(0, 8)}...</span></span>}
              </div>
            )}

            <TokenStatsLink
              sessionKey={sessionKey}
              conversationId={effectiveConversationId}
              turnSeq={turnSeq}
            />

            {/* Result */}
            {ccResult && (
              <div>
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Result</div>
                <pre className={cn(
                  'rounded p-2 overflow-x-auto whitespace-pre-wrap max-h-80 overflow-y-auto',
                  'bg-[var(--bg-tertiary)] text-[var(--text-primary)]',
                )}>
                  {ccResult.body || '(no output)'}
                </pre>
              </div>
            )}
            {!ccResult && resultText && (
              <div>
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Raw Output</div>
                <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-64 overflow-y-auto">
                  {resultText}
                </pre>
              </div>
            )}
            {isLoading && !resultText && (
              <div className="flex items-center gap-1.5 text-cyan-400 py-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Claude Code is working...</span>
              </div>
            )}
          </div>
        )}
        </div>
      </div>
    )
  }

  if (fnName === 'codex') {
    const prompt = (parsedArgs.prompt || '') as string
    const mode = (parsedArgs.mode || 'standard') as string
    const projectPath = (parsedArgs.project_path || '') as string
    const codexResult = resultText ? parseCodexResult(resultText) : null
    const isSuccess = codexResult?.status === 'SUCCESS'

    return (
      <div>
        {metaBar}
        <div className={cn(
          'rounded-lg border text-xs overflow-hidden',
          isSuccess ? 'border-sky-500/30 bg-sky-500/5' : 'border-[var(--border)] bg-[var(--bg-primary)]/50',
        )}>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 w-full px-3 py-2 text-left hover:bg-[var(--bg-tertiary)]/30 transition-colors"
          >
            {isLoading ? (
              <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-sky-400" />
            ) : expanded ? (
              <ChevronDown className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
            ) : (
              <ChevronRight className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
            )}
            <span className="text-base shrink-0">💻</span>
            <span className="font-medium text-sky-400">Codex</span>
            {mode === 'readonly' && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium ml-1 bg-blue-500/15 text-blue-400">
                readonly
              </span>
            )}
            {codexResult && (
              <span className="flex items-center gap-2 ml-2 text-[var(--text-secondary)]">
                <span>{codexResult.turns} turns</span>
                <span>{codexResult.duration}</span>
                {codexResult.runId && (
                  <span className="font-mono text-[9px]">{codexResult.runId.slice(0, 18)}</span>
                )}
              </span>
            )}
            {!expanded && prompt && (
              <span className="text-[var(--text-secondary)] truncate ml-2">— {prompt.slice(0, 60)}{prompt.length > 60 ? '...' : ''}</span>
            )}
          </button>

          {expanded && (
            <div className="px-3 pb-3 space-y-2 border-t border-[var(--border)]">
              {codexResult && (
                <div className="flex flex-wrap gap-3 pt-2 text-[10px]">
                  <div className={cn(
                    'px-2 py-1 rounded-md font-medium',
                    isSuccess ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400',
                  )}>
                    {codexResult.status}
                  </div>
                  <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                    <span>Turns:</span>
                    <span className="text-[var(--text-primary)] font-medium">{codexResult.turns}</span>
                  </div>
                  <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                    <span>Duration:</span>
                    <span className="text-[var(--text-primary)] font-medium">{codexResult.duration}</span>
                  </div>
                  {codexResult.runId && (
                    <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                      <span>Run:</span>
                      <span className="font-mono text-[9px]">{codexResult.runId}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="pt-1">
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Prompt</div>
                <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-48 overflow-y-auto">
                  {prompt}
                </pre>
              </div>

              {projectPath && (
                <div className="flex flex-wrap gap-3 text-[10px] text-[var(--text-secondary)]">
                  <span>Project: <span className="font-mono text-[var(--text-primary)]">{projectPath}</span></span>
                </div>
              )}

              <TokenStatsLink
                sessionKey={sessionKey}
                conversationId={effectiveConversationId}
                turnSeq={turnSeq}
              />

              {codexResult && (
                <div>
                  <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Result</div>
                  <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-80 overflow-y-auto">
                    {codexResult.body || '(no output)'}
                  </pre>
                </div>
              )}
              {!codexResult && resultText && (
                <div>
                  <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Raw Output</div>
                  <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-64 overflow-y-auto">
                    {resultText}
                  </pre>
                </div>
              )}
              {isLoading && !resultText && (
                <div className="flex items-center gap-1.5 text-sky-400 py-1">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>Codex is working...</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (fnName === 'page_agent') {
    const instruction = (parsedArgs.instruction || '') as string
    const paResult = resultText ? parsePageAgentResult(resultText) : null
    const isSuccess = paResult?.status === 'SUCCESS'
    const isError = paResult?.status === 'ERROR' || paResult?.status === 'TIMEOUT'

    return (
      <div>
        {metaBar}
        <div className={cn(
          'rounded-lg border text-xs overflow-hidden',
          isSuccess ? 'border-emerald-500/30 bg-emerald-500/5'
            : isError ? 'border-red-500/30 bg-red-500/5'
            : 'border-[var(--border)] bg-[var(--bg-primary)]/50',
        )}>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 w-full px-3 py-2 text-left hover:bg-[var(--bg-tertiary)]/30 transition-colors"
        >
          {isLoading && !resultText ? (
            <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-emerald-400" />
          ) : expanded ? (
            <ChevronDown className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          ) : (
            <ChevronRight className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          )}
          <Globe className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
          <span className="font-medium text-emerald-400">Page Agent</span>
          {paResult && (
            <>
              <span className={cn(
                'px-1.5 py-0.5 rounded text-[10px] font-medium ml-1',
                isSuccess ? 'bg-emerald-500/15 text-emerald-400'
                  : paResult.status === 'TIMEOUT' ? 'bg-amber-500/15 text-amber-400'
                  : 'bg-red-500/15 text-red-400',
              )}>
                {paResult.status}
              </span>
              <span className="flex items-center gap-2 ml-2 text-[var(--text-secondary)]">
                <span>{paResult.steps} steps</span>
                <span>{paResult.duration}</span>
                {paResult.sessionId && (
                  <span className="font-mono text-[9px]">{paResult.sessionId.slice(0, 10)}</span>
                )}
              </span>
            </>
          )}
          {isLoading && !resultText && (
            <span className="text-emerald-400 ml-2">Browsing...</span>
          )}
          {!expanded && instruction && !isLoading && (
            <span className="text-[var(--text-secondary)] truncate ml-2">— {instruction.slice(0, 60)}{instruction.length > 60 ? '...' : ''}</span>
          )}
        </button>

        {expanded && (
          <div className="px-3 pb-3 space-y-2 border-t border-[var(--border)]">
            {paResult && (
              <div className="flex flex-wrap gap-3 pt-2 text-[10px]">
                <div className={cn(
                  'px-2 py-1 rounded-md font-medium',
                  isSuccess ? 'bg-emerald-500/15 text-emerald-400'
                    : paResult.status === 'TIMEOUT' ? 'bg-amber-500/15 text-amber-400'
                    : 'bg-red-500/15 text-red-400',
                )}>
                  {paResult.status}
                </div>
                <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                  <span>Steps:</span>
                  <span className="text-[var(--text-primary)] font-medium">{paResult.steps}</span>
                </div>
                <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                  <span>Duration:</span>
                  <span className="text-[var(--text-primary)] font-medium">{paResult.duration}</span>
                </div>
                {paResult.sessionId && (
                  <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                    <span>Session:</span>
                    <span className="font-mono text-[9px]">{paResult.sessionId}</span>
                  </div>
                )}
              </div>
            )}

            {instruction && (
              <div className="pt-1">
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Instruction</div>
                <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-48 overflow-y-auto">
                  {instruction}
                </pre>
              </div>
            )}

            <TokenStatsLink
              sessionKey={sessionKey}
              conversationId={effectiveConversationId}
              turnSeq={turnSeq}
            />

            {paResult?.url && paResult.url !== 'unknown' && (
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
                <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                  <span>URL:</span>
                  <a
                    href={paResult.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[var(--accent)] hover:underline font-mono truncate max-w-[300px]"
                  >
                    {paResult.url}
                  </a>
                </div>
                {paResult.title && paResult.title !== 'unknown' && (
                  <div className="flex items-center gap-1 text-[var(--text-secondary)]">
                    <span>Title:</span>
                    <span className="text-[var(--text-primary)]">{paResult.title}</span>
                  </div>
                )}
              </div>
            )}

            {paResult?.body && (
              <div>
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Result</div>
                <pre className={cn(
                  'rounded p-2 overflow-x-auto whitespace-pre-wrap max-h-80 overflow-y-auto',
                  'bg-[var(--bg-tertiary)] text-[var(--text-primary)]',
                )}>
                  {paResult.body}
                </pre>
              </div>
            )}
            {!paResult && resultText && (
              <div>
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Raw Output</div>
                <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-64 overflow-y-auto">
                  {resultText}
                </pre>
              </div>
            )}
            {isLoading && !resultText && (
              <div className="flex items-center gap-1.5 text-emerald-400 py-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Browsing...</span>
              </div>
            )}
          </div>
        )}
        </div>
      </div>
    )
  }

  if (mediaTool) {
    const ToolIcon = mediaTool.icon
    const displayPrompt = (parsedArgs.prompt || parsedArgs.query || '') as string
    return (
      <div>
        {metaBar}
        <div className={cn(
          'rounded-lg border text-xs',
          'border-[var(--border)] bg-[var(--bg-primary)]/50',
        )}>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 w-full px-3 py-2 text-left hover:bg-[var(--bg-tertiary)]/30 rounded-lg transition-colors"
        >
          {isLoading ? (
            <Loader2 className={cn('w-3.5 h-3.5 shrink-0 animate-spin', mediaTool.color)} />
          ) : expanded ? (
            <ChevronDown className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          ) : (
            <ChevronRight className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          )}
          <ToolIcon className={cn('w-3.5 h-3.5 shrink-0', mediaTool.color)} />
          <span className={cn('font-medium', mediaTool.color)}>{mediaTool.label}</span>
          {displayPrompt && !expanded && (
            <span className="text-[var(--text-secondary)] truncate ml-1">— {displayPrompt.slice(0, 60)}{displayPrompt.length > 60 ? '...' : ''}</span>
          )}
        </button>

        {expanded && (
          <div className="px-3 pb-2 space-y-2 border-t border-[var(--border)]">
            {displayPrompt && (
              <div className="pt-1.5">
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Prompt</div>
                <div className="text-[var(--text-primary)] text-[11px]">{displayPrompt}</div>
              </div>
            )}
            <TokenStatsLink
              sessionKey={sessionKey}
              conversationId={effectiveConversationId}
              turnSeq={turnSeq}
            />
            {args && args !== '{}' && !displayPrompt && (
              <div className="pt-1.5">
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Arguments</div>
                <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-48 overflow-y-auto">
                  {args}
                </pre>
              </div>
            )}
            {mediaImageUrls.length > 0 && (fnName === 'vision' || fnName === 'analyze_image') && (
              <div className="pt-1">
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Input Image</div>
                <ImageCarousel urls={mediaImageUrls} alt={displayPrompt || fnName} />
              </div>
            )}
            {mediaImageUrls.length > 0 && fnName !== 'vision' && fnName !== 'analyze_image' && (
              <div className="pt-1">
                <ImageCarousel urls={mediaImageUrls} alt={displayPrompt || fnName} />
              </div>
            )}
            {resultText !== null && (
              <div>
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Result</div>
                <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-64 overflow-y-auto">
                  {resultText}
                </pre>
              </div>
            )}
            {isLoading && !resultText && (
              <div className="flex items-center gap-1.5 text-[var(--warning)] py-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Processing...</span>
              </div>
            )}
          </div>
        )}
        </div>
      </div>
    )
  }

  return (
    <div>
      {metaBar}
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)]/50 text-xs">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 w-full px-3 py-2 text-left hover:bg-[var(--bg-tertiary)]/30 rounded-lg transition-colors"
        >
          {isLoading ? (
            <Loader2 className="w-3 h-3 shrink-0 text-[var(--warning)] animate-spin" />
          ) : expanded ? (
            <ChevronDown className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          ) : (
            <ChevronRight className="w-3 h-3 shrink-0 text-[var(--text-secondary)]" />
          )}
          <Wrench className="w-3 h-3 shrink-0 text-[var(--accent)]" />
          <span className="font-mono text-[var(--accent)]">{fnName}</span>
          {!expanded && resultPreview && (
            <span className="text-[var(--text-secondary)] truncate ml-2">{resultPreview}</span>
          )}
        </button>

        {expanded && (
          <div className="p-3 space-y-2">
            <TokenStatsLink
              sessionKey={sessionKey}
              conversationId={effectiveConversationId}
              turnSeq={turnSeq}
            />
            <div>
              <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Arguments</div>
              <pre className="bg-[var(--bg-tertiary)] rounded p-2 overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)] max-h-48 overflow-y-auto">
                {args}
              </pre>
            </div>
            {resultText !== null && (
              <div>
                <div className="text-[var(--text-secondary)] mb-0.5 font-medium">Result</div>
                <pre className={cn(
                  'rounded p-2 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto',
                  'bg-[var(--bg-tertiary)] text-[var(--text-primary)]',
                )}>
                  {resultText}
                </pre>
              </div>
            )}
            {isLoading && !resultText && (
              <div className="flex items-center gap-1.5 text-[var(--warning)] py-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Waiting for result...</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
