import { useEffect, useState } from 'react'
import { X, RefreshCw, ShieldAlert, ShieldOff, Expand, Minimize, FileText } from 'lucide-react'
import { api } from '../../api/client'
import type { ContextPreview } from './types'
import { formatTokenCount } from './utils'

const SECTION_LABELS: Record<string, string> = {
  identity: 'Identity',
  bootstrap: 'Bootstrap',
  memory: 'Memory',
  active_skills: 'Active Skills',
  skills_summary: 'Skills Summary',
  recent_history: 'Recent History',
  categorized_memory: 'Categorized Memory',
  background_tasks: 'Background Tasks',
}

function sectionLabel(name: string) {
  return SECTION_LABELS[name] || name.replaceAll('_', ' ')
}

function BlockPreview({ block }: { block: NonNullable<ContextPreview['messages'][number]['content_blocks']>[number] }) {
  if (block.type === 'text') {
    return (
      <pre className="whitespace-pre-wrap break-words text-xs text-[var(--text-primary)]">
        {block.text || ''}
      </pre>
    )
  }

  if (block.type === 'image_url') {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] p-2 text-xs text-[var(--text-secondary)]">
        {block.image_url?.url || '[image omitted]'}
      </div>
    )
  }

  return (
    <pre className="whitespace-pre-wrap break-words text-xs text-[var(--text-primary)]">
      {JSON.stringify(block, null, 2)}
    </pre>
  )
}

interface ContextInspectorProps {
  open: boolean
  sessionKey: string | null
  disabled?: boolean
  onClose: () => void
}

export function ContextInspector({ open, sessionKey, disabled, onClose }: ContextInspectorProps) {
  const [preview, setPreview] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [full, setFull] = useState(false)
  const [reveal, setReveal] = useState(false)
  const [reloadTick, setReloadTick] = useState(0)

  useEffect(() => {
    if (!open) {
      setPreview(null)
      setError('')
    }
  }, [open])

  useEffect(() => {
    if (!open || !sessionKey || disabled) return

    let cancelled = false

    const load = async () => {
      setLoading(true)
      try {
        const params = new URLSearchParams()
        if (full) params.set('full', 'true')
        if (reveal) params.set('reveal', 'true')
        const next = await api<ContextPreview>(
          `/chat/sessions/${encodeURIComponent(sessionKey)}/context-preview${params.size ? `?${params.toString()}` : ''}`,
        )
        if (!cancelled) {
          setPreview(next)
          setError('')
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load context preview')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    const timer = window.setInterval(load, 5000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [open, sessionKey, disabled, full, reveal, reloadTick])

  return (
    <>
      {open && <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />}
      <div
        className={[
          'fixed inset-y-0 right-0 z-50 w-full max-w-[44rem] border-l border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl transition-transform duration-200',
          open ? 'translate-x-0' : 'translate-x-full',
        ].join(' ')}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-primary)]">
                <FileText className="h-4 w-4" />
                <span>Context Inspector</span>
              </div>
              <div className="truncate text-xs text-[var(--text-secondary)]">
                {sessionKey || 'No session selected'}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setFull((value) => !value)}
                className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                title={full ? '切回截断预览' : '显示完整内容'}
              >
                {full ? <Minimize className="h-3.5 w-3.5" /> : <Expand className="h-3.5 w-3.5" />}
              </button>
              <button
                onClick={() => setReveal((value) => !value)}
                className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                title={reveal ? '恢复脱敏' : '显示未脱敏内容'}
              >
                {reveal ? <ShieldOff className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}
              </button>
              <button
                onClick={() => {
                  setReloadTick((value) => value + 1)
                }}
                className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                title="刷新"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                title="关闭"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {disabled && (
              <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4 text-sm text-[var(--text-secondary)]">
                当前会话是只读历史分支，Inspector 只对当前活跃会话开放。
              </div>
            )}

            {!disabled && error && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
                {error}
              </div>
            )}

            {!disabled && !error && !preview && loading && (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="h-5 w-5 animate-spin text-[var(--accent)]" />
              </div>
            )}

            {!disabled && preview && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-3">
                    <div className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">System</div>
                    <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                      {formatTokenCount(preview.totals.system_tokens)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-3">
                    <div className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">Runtime</div>
                    <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                      {formatTokenCount(preview.totals.runtime_tokens)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-3">
                    <div className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">History</div>
                    <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                      {formatTokenCount(preview.totals.history_tokens)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-3">
                    <div className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">Tools</div>
                    <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                      {formatTokenCount(preview.totals.tool_tokens)}
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-secondary)]">
                    <span>{preview.provider.name || 'provider'} / {preview.provider.model || 'unknown model'}</span>
                    <span>总计 {formatTokenCount(preview.totals.request_total_tokens)} tokens</span>
                    <span>{preview.totals.utilization_pct}% of budget</span>
                    {preview.flags.sanitized && <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-300">已脱敏</span>}
                    {preview.flags.in_flight && <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-sky-300">执行中，显示 idle baseline</span>}
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
                    <div
                      className="h-full rounded-full bg-[var(--accent)]"
                      style={{ width: `${Math.min(preview.totals.utilization_pct, 100)}%` }}
                    />
                  </div>
                  <div className="mt-2 text-xs text-[var(--text-secondary)]">
                    ctx budget {formatTokenCount(preview.totals.ctx_budget)} / window {formatTokenCount(preview.totals.context_window)}
                  </div>
                </div>

                <section className="space-y-3">
                  <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">System Sections</div>
                  {preview.system_sections.map((section) => (
                    <div key={section.name} className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <div className="text-sm font-medium text-[var(--text-primary)]">{sectionLabel(section.name)}</div>
                          <div className="text-xs text-[var(--text-secondary)]">{section.source}</div>
                        </div>
                        <div className="text-xs text-[var(--text-secondary)]">{formatTokenCount(section.tokens)} tokens</div>
                      </div>
                      <pre className="mt-3 whitespace-pre-wrap break-words text-xs text-[var(--text-primary)]">{section.content}</pre>
                    </div>
                  ))}
                </section>

                <section className="space-y-3">
                  <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">Runtime Context</div>
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                    <div className="text-xs text-[var(--text-secondary)]">{formatTokenCount(preview.runtime_context.tokens)} tokens</div>
                    <pre className="mt-3 whitespace-pre-wrap break-words text-xs text-[var(--text-primary)]">
                      {preview.runtime_context.content}
                    </pre>
                  </div>
                </section>

                <section className="space-y-3">
                  <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">History</div>
                  {preview.messages.length === 0 && (
                    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4 text-sm text-[var(--text-secondary)]">
                      当前没有未归档历史消息。
                    </div>
                  )}
                  {preview.messages.map((message, index) => (
                    <div key={`${message.role}-${index}`} className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 text-xs text-[var(--text-primary)]">
                          {message.role}
                        </span>
                        <span className="text-xs text-[var(--text-secondary)]">{formatTokenCount(message.tokens)} tokens</span>
                        {message.truncated && <span className="text-xs text-amber-300">truncated</span>}
                        {message.name && <span className="text-xs text-[var(--text-secondary)]">tool: {message.name}</span>}
                      </div>
                      {message.content_type === 'text' ? (
                        <pre className="mt-3 whitespace-pre-wrap break-words text-xs text-[var(--text-primary)]">{message.content}</pre>
                      ) : (
                        <div className="mt-3 space-y-2">
                          <div className="text-xs text-[var(--text-secondary)]">{message.content}</div>
                          {message.content_blocks?.map((block, blockIndex) => (
                            <BlockPreview key={`${block.type}-${blockIndex}`} block={block} />
                          ))}
                        </div>
                      )}
                      {message.tool_calls && message.tool_calls.length > 0 && (
                        <pre className="mt-3 whitespace-pre-wrap break-words rounded-lg bg-[var(--bg-tertiary)] p-2 text-xs text-[var(--text-primary)]">
                          {JSON.stringify(message.tool_calls, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </section>

                <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                  <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">Tool Schema</div>
                  <div className="mt-2 text-sm text-[var(--text-primary)]">
                    {preview.tools.count} tools · {formatTokenCount(preview.tools.tokens)} tokens
                  </div>
                  <div className="mt-2 text-xs text-[var(--text-secondary)] break-words">
                    {preview.tools.names.join(', ') || 'No registered tools'}
                  </div>
                </section>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
