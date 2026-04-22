import { useEffect, useState } from 'react'
import { X, RefreshCw, FileText } from 'lucide-react'
import { MarkdownRenderer } from '../../components/markdown/MarkdownRenderer'
import { api } from '../../api/client'
import type { ContextPreview } from './types'
import { formatTokenCount } from './utils'

type ContextCategory = 'system' | 'runtime' | 'history' | 'tools'
type CategoryFilters = Record<ContextCategory, boolean>
type SectionRevealState = Record<string, boolean>
type ContextPreviewBlock = NonNullable<ContextPreview['messages'][number]['content_blocks']>[number]
type FullContentTarget =
  | { kind: 'system-section'; sectionName: string }
  | { kind: 'runtime-context' }
  | { kind: 'history-message'; index: number }

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

const CATEGORY_META: Record<
  ContextCategory,
  {
    label: string
    heading: string
    activeClass: string
    headingClass: string
  }
> = {
  system: {
    label: 'System',
    heading: 'System Sections',
    activeClass: 'border-sky-500/40 bg-sky-500/10',
    headingClass: 'text-sky-400',
  },
  runtime: {
    label: 'Runtime',
    heading: 'Runtime Context',
    activeClass: 'border-emerald-500/40 bg-emerald-500/10',
    headingClass: 'text-emerald-400',
  },
  history: {
    label: 'History',
    heading: 'History',
    activeClass: 'border-amber-500/40 bg-amber-500/10',
    headingClass: 'text-amber-400',
  },
  tools: {
    label: 'Tools',
    heading: 'Tool Schema',
    activeClass: 'border-fuchsia-500/40 bg-fuchsia-500/10',
    headingClass: 'text-fuchsia-400',
  },
}

function createDefaultCategoryFilters(): CategoryFilters {
  return {
    system: true,
    runtime: true,
    history: true,
    tools: true,
  }
}

function sectionLabel(name: string) {
  return SECTION_LABELS[name] || name.replaceAll('_', ' ')
}

function buildPreviewUrl(sessionKey: string, options?: { full?: boolean; reveal?: boolean }) {
  const params = new URLSearchParams()
  if (options?.full) params.set('full', 'true')
  if (options?.reveal) params.set('reveal', 'true')
  return `/chat/sessions/${encodeURIComponent(sessionKey)}/context-preview${params.size ? `?${params.toString()}` : ''}`
}

async function fetchContextPreview(sessionKey: string, options?: { full?: boolean; reveal?: boolean }) {
  return api<ContextPreview>(buildPreviewUrl(sessionKey, options))
}

function MarkdownContent({
  content,
  className = 'mt-3',
  truncated = false,
  onExpand,
  showActions = true,
  showCopy = true,
}: {
  content: string
  className?: string
  truncated?: boolean
  onExpand?: (() => void) | null
  showActions?: boolean
  showCopy?: boolean
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content || '')
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
  }

  return (
    <div
      className={[
        className,
        'group/content relative w-full min-w-0 rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3 text-xs text-[var(--text-primary)]',
      ].join(' ')}
    >
      {showActions && (showCopy || (truncated && onExpand)) && (
        <div className="pointer-events-none absolute top-2 right-2 z-10 flex items-center gap-2 rounded-md bg-[var(--bg-primary)]/90 p-1 opacity-0 shadow-sm backdrop-blur-sm transition-opacity group-hover/content:pointer-events-auto group-hover/content:opacity-100 group-focus-within/content:pointer-events-auto group-focus-within/content:opacity-100">
          {showCopy && (
            <button
              type="button"
              onClick={handleCopy}
              className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              {copied ? '已复制' : '复制'}
            </button>
          )}
          {truncated && onExpand && (
            <button
              type="button"
              onClick={onExpand}
              className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              展开
            </button>
          )}
        </div>
      )}
      <MarkdownRenderer content={content || ''} />
    </div>
  )
}

function BlockPreview({ block }: { block: ContextPreviewBlock }) {
  if (block.type === 'text') {
    return <MarkdownContent content={block.text || ''} className="" />
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

function resolveSystemSection(
  preview: ContextPreview,
  revealedPreview: ContextPreview | null,
  revealedSections: SectionRevealState,
  sectionName: string,
) {
  if (revealedSections[sectionName] && revealedPreview) {
    return revealedPreview.system_sections.find((section) => section.name === sectionName)
      || preview.system_sections.find((section) => section.name === sectionName)
      || null
  }

  return preview.system_sections.find((section) => section.name === sectionName) || null
}

interface ContextSectionsProps {
  preview: ContextPreview
  revealedPreview: ContextPreview | null
  revealedSections: SectionRevealState
  filters: CategoryFilters
  showSectionActions?: boolean
  sectionLoadingName?: string | null
  onToggleSectionReveal?: (sectionName: string) => void
  onOpenFullModal?: (target: FullContentTarget) => void
}

function ContextSections({
  preview,
  revealedPreview,
  revealedSections,
  filters,
  showSectionActions = false,
  sectionLoadingName,
  onToggleSectionReveal,
  onOpenFullModal,
}: ContextSectionsProps) {
  const hasSelectedCategory = Object.values(filters).some(Boolean)

  if (!hasSelectedCategory) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4 text-sm text-[var(--text-secondary)]">
        当前没有选中的内容分类，请先在上方选择至少一个分块。
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {filters.system && (
        <section className="space-y-3">
          <div className={`text-xs font-medium uppercase tracking-wide ${CATEGORY_META.system.headingClass}`}>
            {CATEGORY_META.system.heading}
          </div>
          {preview.system_sections.length === 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4 text-sm text-[var(--text-secondary)]">
              当前没有可显示的 system sections。
            </div>
          )}
          {preview.system_sections.map((rawSection) => {
            const section = resolveSystemSection(preview, revealedPreview, revealedSections, rawSection.name)
            if (!section) return null

            const isRevealed = Boolean(revealedSections[rawSection.name])

            return (
              <div key={rawSection.name} className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className={`text-sm font-medium ${CATEGORY_META.system.headingClass}`}>
                      {sectionLabel(section.name)}
                    </div>
                    <div className="truncate text-xs text-[var(--text-secondary)]">{section.source}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-[var(--text-secondary)]">
                      {formatTokenCount(section.tokens)} tokens
                    </div>
                    {showSectionActions && onToggleSectionReveal && (
                      <button
                        type="button"
                        onClick={() => onToggleSectionReveal(rawSection.name)}
                        className="rounded-md border border-[var(--border)] bg-[var(--bg-primary)] px-2.5 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                      >
                        {sectionLoadingName === rawSection.name
                          ? '加载中...'
                          : isRevealed
                            ? '恢复脱敏'
                            : '显示未脱敏内容'}
                      </button>
                    )}
                  </div>
                </div>
                <MarkdownContent
                  content={section.content}
                  truncated={section.truncated}
                  onExpand={section.truncated && onOpenFullModal
                    ? () => onOpenFullModal({ kind: 'system-section', sectionName: rawSection.name })
                    : null}
                />
              </div>
            )
          })}
        </section>
      )}

      {filters.runtime && (
        <section className="space-y-3">
          <div className={`text-xs font-medium uppercase tracking-wide ${CATEGORY_META.runtime.headingClass}`}>
            {CATEGORY_META.runtime.heading}
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
            <div className="text-xs text-[var(--text-secondary)]">
              {formatTokenCount(preview.runtime_context.tokens)} tokens
            </div>
            <MarkdownContent
              content={preview.runtime_context.content}
              truncated={preview.runtime_context.truncated}
              onExpand={preview.runtime_context.truncated && onOpenFullModal
                ? () => onOpenFullModal({ kind: 'runtime-context' })
                : null}
            />
          </div>
        </section>
      )}

      {filters.history && (
        <section className="space-y-3">
          <div className={`text-xs font-medium uppercase tracking-wide ${CATEGORY_META.history.headingClass}`}>
            {CATEGORY_META.history.heading}
          </div>
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
                {message.name && <span className="text-xs text-[var(--text-secondary)]">tool: {message.name}</span>}
              </div>
              {message.content_type === 'text' ? (
                <MarkdownContent
                  content={message.content}
                  truncated={message.truncated}
                  onExpand={message.truncated && onOpenFullModal
                    ? () => onOpenFullModal({ kind: 'history-message', index })
                    : null}
                />
              ) : (
                <div className="mt-3 space-y-2">
                  <MarkdownContent
                    content={message.content}
                    className=""
                    truncated={message.truncated}
                    onExpand={message.truncated && onOpenFullModal
                      ? () => onOpenFullModal({ kind: 'history-message', index })
                      : null}
                  />
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
      )}

      {filters.tools && (
        <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
          <div className={`text-xs font-medium uppercase tracking-wide ${CATEGORY_META.tools.headingClass}`}>
            {CATEGORY_META.tools.heading}
          </div>
          <div className="mt-2 text-sm text-[var(--text-primary)]">
            {preview.tools.count} tools · {formatTokenCount(preview.tools.tokens)} tokens
          </div>
          <div className="mt-2 text-xs break-words text-[var(--text-secondary)]">
            {preview.tools.names.join(', ') || 'No registered tools'}
          </div>
        </section>
      )}
    </div>
  )
}

interface FullContentModalProps {
  open: boolean
  loading: boolean
  error: string
  title: string
  content: string
  onClose: () => void
}

function FullContentModal({
  open,
  loading,
  error,
  title,
  content,
  onClose,
}: FullContentModalProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="flex h-[min(88vh,52rem)] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-[var(--text-primary)]">{title}</div>
            <div className="truncate text-xs text-[var(--text-secondary)]">
              当前块的完整内容
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            title="关闭"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-5 w-5 animate-spin text-[var(--accent)]" />
            </div>
          )}

          {!loading && error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
              {error}
            </div>
          )}

          {!loading && !error && (
            <MarkdownContent
              content={content}
              className=""
              showActions
              showCopy
              truncated={false}
              onExpand={null}
            />
          )}
        </div>
      </div>
    </div>
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
  const [revealedPreview, setRevealedPreview] = useState<ContextPreview | null>(null)
  const [fullPreview, setFullPreview] = useState<ContextPreview | null>(null)
  const [fullRevealedPreview, setFullRevealedPreview] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [fullLoading, setFullLoading] = useState(false)
  const [error, setError] = useState('')
  const [fullError, setFullError] = useState('')
  const [reloadTick, setReloadTick] = useState(0)
  const [filters, setFilters] = useState<CategoryFilters>(createDefaultCategoryFilters)
  const [revealedSections, setRevealedSections] = useState<SectionRevealState>({})
  const [sectionLoadingName, setSectionLoadingName] = useState<string | null>(null)
  const [fullContentTarget, setFullContentTarget] = useState<FullContentTarget | null>(null)

  const hasRevealedSections = Object.values(revealedSections).some(Boolean)
  const showFullModal = fullContentTarget !== null

  useEffect(() => {
    if (!open) {
      setPreview(null)
      setRevealedPreview(null)
      setFullPreview(null)
      setFullRevealedPreview(null)
      setError('')
      setFullError('')
      setFilters(createDefaultCategoryFilters())
      setRevealedSections({})
      setSectionLoadingName(null)
      setFullContentTarget(null)
    }
  }, [open])

  useEffect(() => {
    setPreview(null)
    setRevealedPreview(null)
    setFullPreview(null)
    setFullRevealedPreview(null)
    setError('')
    setFullError('')
    setFilters(createDefaultCategoryFilters())
    setRevealedSections({})
    setSectionLoadingName(null)
    setFullContentTarget(null)
  }, [sessionKey])

  useEffect(() => {
    if (!open || !sessionKey || disabled) return

    let cancelled = false

    const load = async () => {
      setLoading(true)
      try {
        const [nextPreview, nextRevealedPreview] = await Promise.all([
          fetchContextPreview(sessionKey),
          hasRevealedSections ? fetchContextPreview(sessionKey, { reveal: true }) : Promise.resolve(null),
        ])

        if (!cancelled) {
          setPreview(nextPreview)
          setRevealedPreview(nextRevealedPreview)
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
  }, [open, sessionKey, disabled, reloadTick, hasRevealedSections])

  useEffect(() => {
    if (!showFullModal || !sessionKey || disabled) return

    let cancelled = false

    const loadFullPreview = async () => {
      setFullLoading(true)
      try {
        const [nextFullPreview, nextFullRevealedPreview] = await Promise.all([
          fetchContextPreview(sessionKey, { full: true }),
          hasRevealedSections ? fetchContextPreview(sessionKey, { full: true, reveal: true }) : Promise.resolve(null),
        ])

        if (!cancelled) {
          setFullPreview(nextFullPreview)
          setFullRevealedPreview(nextFullRevealedPreview)
          setFullError('')
        }
      } catch (err: any) {
        if (!cancelled) {
          setFullError(err?.message || 'Failed to load full context preview')
        }
      } finally {
        if (!cancelled) {
          setFullLoading(false)
        }
      }
    }

    void loadFullPreview()

    return () => {
      cancelled = true
    }
  }, [showFullModal, sessionKey, disabled, reloadTick, hasRevealedSections])

  useEffect(() => {
    if (!showFullModal) return

    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFullContentTarget(null)
    }

    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [showFullModal])

  const resolveFullContent = () => {
    if (!fullContentTarget) return { title: '完整内容', content: '' }

    if (fullContentTarget.kind === 'system-section') {
      const useRevealed = Boolean(revealedSections[fullContentTarget.sectionName]) && fullRevealedPreview
      const sourcePreview = useRevealed ? fullRevealedPreview : fullPreview
      const section = sourcePreview?.system_sections.find((item) => item.name === fullContentTarget.sectionName)
      return {
        title: section ? `${sectionLabel(section.name)} · 完整内容` : 'System Section · 完整内容',
        content: section?.content || '',
      }
    }

    if (fullContentTarget.kind === 'runtime-context') {
      return {
        title: 'Runtime Context · 完整内容',
        content: fullPreview?.runtime_context.content || '',
      }
    }

    const message = fullPreview?.messages[fullContentTarget.index]
    return {
      title: message ? `History · ${message.role} · 完整内容` : 'History · 完整内容',
      content: message?.content || '',
    }
  }

  const fullContent = resolveFullContent()

  const handleToggleCategory = (category: ContextCategory) => {
    setFilters((current) => ({
      ...current,
      [category]: !current[category],
    }))
  }

  const handleToggleSectionReveal = async (sectionName: string) => {
    if (!sessionKey) return

    if (revealedSections[sectionName]) {
      setRevealedSections((current) => ({
        ...current,
        [sectionName]: false,
      }))
      return
    }

    if (!revealedPreview) {
      setSectionLoadingName(sectionName)
      try {
        const nextRevealedPreview = await fetchContextPreview(sessionKey, { reveal: true })
        setRevealedPreview(nextRevealedPreview)
      } catch (err: any) {
        setError(err?.message || 'Failed to load revealed context preview')
        setSectionLoadingName(null)
        return
      }
      setSectionLoadingName(null)
    }

    setRevealedSections((current) => ({
      ...current,
      [sectionName]: true,
    }))
  }

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
                type="button"
                onClick={() => setReloadTick((value) => value + 1)}
                className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
                title="刷新"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading || fullLoading ? 'animate-spin' : ''}`} />
              </button>
              <button
                type="button"
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
                  {(['system', 'runtime', 'history', 'tools'] as ContextCategory[]).map((category) => {
                    const meta = CATEGORY_META[category]
                    const isActive = filters[category]
                    const tokens = category === 'system'
                      ? preview.totals.system_tokens
                      : category === 'runtime'
                        ? preview.totals.runtime_tokens
                        : category === 'history'
                          ? preview.totals.history_tokens
                          : preview.totals.tool_tokens

                    return (
                      <button
                        key={category}
                        type="button"
                        onClick={() => handleToggleCategory(category)}
                        aria-pressed={isActive}
                        className={[
                          'rounded-xl border p-3 text-left transition-colors',
                          isActive
                            ? meta.activeClass
                            : 'border-[var(--border)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)]/40',
                        ].join(' ')}
                      >
                        <div className={`text-[10px] uppercase tracking-wide ${isActive ? meta.headingClass : 'text-[var(--text-secondary)]'}`}>
                          {meta.label}
                        </div>
                        <div className="mt-1 text-sm font-medium text-[var(--text-primary)]">
                          {formatTokenCount(tokens)}
                        </div>
                      </button>
                    )
                  })}
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

                <ContextSections
                  preview={preview}
                  revealedPreview={revealedPreview}
                  revealedSections={revealedSections}
                  filters={filters}
                  showSectionActions
                  sectionLoadingName={sectionLoadingName}
                  onToggleSectionReveal={handleToggleSectionReveal}
                  onOpenFullModal={(target) => setFullContentTarget(target)}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      <FullContentModal
        open={showFullModal}
        loading={fullLoading}
        error={fullError}
        title={fullContent.title}
        content={fullContent.content}
        onClose={() => setFullContentTarget(null)}
      />
    </>
  )
}
