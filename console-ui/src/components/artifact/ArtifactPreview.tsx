import { useEffect, useMemo, useState } from 'react'
import { Copy, Check, Download, FolderOpen, FileText, Image as ImageIcon, FileDiff, FileJson, Terminal, Folder, File as FileIcon } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { ArtifactRecord } from '../../stores/useWorkflowStore'
import { StatusBadge } from '../ui/StatusBadge'
import { CodeBlock } from '../markdown/CodeBlock'
import { MarkdownRenderer } from '../markdown/MarkdownRenderer'

interface AvaDesktopApi {
  revealArtifact?: (artifactId: string) => Promise<{ ok: boolean; error?: string }>
}

function desktopApi(): AvaDesktopApi | null {
  return (window as unknown as { avaDesktop?: AvaDesktopApi }).avaDesktop || null
}

const TYPE_META: Record<string, { label: string; icon: typeof FileText; tone: string }> = {
  text: { label: 'Text', icon: FileText, tone: 'bg-[var(--ava-running-soft)] text-[var(--ava-running)]' },
  image: { label: 'Image', icon: ImageIcon, tone: 'bg-[var(--ava-queued-soft)] text-[var(--ava-queued)]' },
  diff: { label: 'Diff', icon: FileDiff, tone: 'bg-[var(--ava-warning-soft)] text-[var(--ava-warning)]' },
  json: { label: 'JSON', icon: FileJson, tone: 'bg-[var(--ava-running-soft)] text-[var(--ava-running)]' },
  log: { label: 'Log', icon: Terminal, tone: 'bg-[var(--ava-idle-soft)] text-[var(--ava-text-muted)]' },
  file: { label: 'File', icon: FileIcon, tone: 'bg-[var(--ava-idle-soft)] text-[var(--ava-text-muted)]' },
  workspace: { label: 'Workspace', icon: Folder, tone: 'bg-[var(--ava-success-soft)] text-[var(--ava-success)]' },
}

function typeMeta(type: string) {
  return TYPE_META[type] ?? { label: type || 'Artifact', icon: FileIcon, tone: 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]' }
}

function formatTimestamp(ts: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function imageSrcFromUri(uri: string): string {
  if (uri.startsWith('http://') || uri.startsWith('https://') || uri.startsWith('data:') || uri.startsWith('/api/')) return uri
  const filename = uri.split('/').pop() || uri
  return `/api/media/images/${filename}`
}

export interface ArtifactPreviewProps {
  artifact: ArtifactRecord
  className?: string
}

export function ArtifactPreview({ artifact, className }: ArtifactPreviewProps) {
  const [copied, setCopied] = useState(false)
  const [revealError, setRevealError] = useState<string | null>(null)
  const meta = typeMeta(artifact.artifact_type)
  const Icon = meta.icon
  const reveal = desktopApi()?.revealArtifact

  const sourceAgent = useMemo(() => {
    const candidate = artifact.metadata?.source_agent ?? artifact.metadata?.agent ?? artifact.metadata?.tool
    return typeof candidate === 'string' ? candidate : null
  }, [artifact.metadata])

  const generationStatus = useMemo(() => {
    const status = artifact.metadata?.status
    if (typeof status === 'string' && status !== 'completed' && status !== 'succeeded') return status
    return null
  }, [artifact.metadata])

  const previewText = artifact.preview || ''

  useEffect(() => {
    if (!copied) return
    const t = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(t)
  }, [copied])

  const handleCopy = async () => {
    if (!navigator.clipboard || !previewText) return
    try {
      await navigator.clipboard.writeText(previewText)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  const handleReveal = async () => {
    if (!reveal) return
    setRevealError(null)
    try {
      const result = await reveal(artifact.artifact_id)
      if (!result.ok) setRevealError(result.error ?? 'Reveal failed')
    } catch (err) {
      setRevealError(err instanceof Error ? err.message : 'Reveal failed')
    }
  }

  return (
    <div className={cn('flex flex-col rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] overflow-hidden', className)}>
      {/* DESIGN_DETAILS §8.5 — Header: type, agent, linked task/workflow, time, status if incomplete */}
      <header className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-[var(--border)] bg-[var(--bg-primary)]">
        <span className={cn('inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium', meta.tone)}>
          <Icon className="w-3.5 h-3.5" />
          {meta.label}
        </span>
        {sourceAgent && (
          <span className="text-xs text-[var(--text-secondary)]">
            来源 <span className="text-[var(--text-primary)] font-medium">{sourceAgent}</span>
          </span>
        )}
        {(artifact.task_id || artifact.chain_id) && (
          <span className="text-xs text-[var(--text-secondary)] font-mono">
            {artifact.task_id && <span title="task">task:{artifact.task_id.slice(0, 8)}</span>}
            {artifact.task_id && artifact.chain_id && <span className="opacity-50"> · </span>}
            {artifact.chain_id && <span title="chain">chain:{artifact.chain_id.slice(0, 8)}</span>}
          </span>
        )}
        <span className="text-xs text-[var(--text-secondary)] ml-auto">{formatTimestamp(artifact.created_at)}</span>
        {generationStatus && (
          <StatusBadge kind="running" label={generationStatus} />
        )}
      </header>

      {/* Body — type-dispatched. Diff/code/log follow §7.6 (dark surface, mono). */}
      <div className="flex-1 min-h-0 overflow-auto">
        <ArtifactBody artifact={artifact} />
      </div>

      {/* Errors surfaced before raw output (§8.5) */}
      {typeof artifact.metadata?.error === 'string' && artifact.metadata.error && (
        <div className="border-t border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] px-4 py-3 text-sm text-[var(--ava-danger)]">
          <p className="font-medium mb-1">错误概要</p>
          <p className="whitespace-pre-wrap break-words">{artifact.metadata.error}</p>
        </div>
      )}

      {/* Actions */}
      <footer className="flex items-center gap-2 px-4 py-2 border-t border-[var(--border)] bg-[var(--bg-primary)]">
        <button
          type="button"
          onClick={handleCopy}
          disabled={!previewText}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-[var(--ava-success)]" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? '已复制' : '复制'}
        </button>
        {artifact.uri && (
          <a
            href={artifact.uri.startsWith('/') || artifact.uri.startsWith('http') ? artifact.uri : `/api/media/images/${artifact.uri.split('/').pop()}`}
            target="_blank"
            rel="noreferrer"
            download
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            下载
          </a>
        )}
        {reveal && (
          <button
            type="button"
            onClick={handleReveal}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            在 Finder 打开
          </button>
        )}
        {revealError && <span className="text-xs text-[var(--ava-danger)] ml-auto">{revealError}</span>}
      </footer>
    </div>
  )
}

function ArtifactBody({ artifact }: { artifact: ArtifactRecord }) {
  const preview = artifact.preview || ''

  switch (artifact.artifact_type) {
    case 'image':
      return (
        <div className="flex items-center justify-center bg-[var(--bg-tertiary)] p-4">
          <img
            src={imageSrcFromUri(artifact.uri)}
            alt={typeof artifact.metadata?.alt === 'string' ? artifact.metadata.alt : artifact.artifact_id}
            className="max-h-[60vh] max-w-full rounded-lg object-contain"
          />
        </div>
      )

    case 'diff':
      return (
        <div className="p-4">
          <CodeBlock language="diff" code={preview || '(no diff preview)'} />
        </div>
      )

    case 'json':
      return (
        <div className="p-4">
          <CodeBlock language="json" code={preview || '{}'} />
        </div>
      )

    case 'log':
      // §7.6: dedicated log/code panels stay dark in both themes.
      return (
        <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words bg-[#0f1512] text-[#ecf4ef] p-4 m-0 overflow-auto">
          {preview || '(no log content)'}
        </pre>
      )

    case 'workspace':
      return <WorkspaceTree paths={extractWorkspacePaths(artifact)} root={String(artifact.metadata?.root ?? '')} />

    case 'file': {
      const language = inferLanguageFromUri(artifact.uri)
      if (language) {
        return (
          <div className="p-4">
            <CodeBlock language={language} code={preview || '(no file preview)'} />
          </div>
        )
      }
      return (
        <div className="p-4">
          <p className="text-xs uppercase text-[var(--text-secondary)] mb-2">File · {artifact.uri}</p>
          {preview ? (
            <pre className="text-sm font-mono text-[var(--text-primary)] whitespace-pre-wrap break-words">{preview}</pre>
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">No preview available.</p>
          )}
        </div>
      )
    }

    case 'text':
    default:
      return (
        <div className="p-4">
          {preview ? (
            <MarkdownRenderer content={preview} />
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">No content.</p>
          )}
        </div>
      )
  }
}

function extractWorkspacePaths(artifact: ArtifactRecord): string[] {
  const candidate = artifact.metadata?.paths
  if (Array.isArray(candidate)) return candidate.filter((p): p is string => typeof p === 'string')
  const preview = artifact.preview || ''
  return preview ? preview.split('\n').map(s => s.trim()).filter(Boolean) : []
}

function WorkspaceTree({ paths, root }: { paths: string[]; root: string }) {
  if (paths.length === 0) {
    return <p className="p-4 text-sm text-[var(--text-secondary)]">空 workspace</p>
  }
  return (
    <div className="p-4">
      {root && (
        <p className="text-xs font-mono text-[var(--text-secondary)] mb-2 inline-flex items-center gap-1.5">
          <Folder className="w-3.5 h-3.5" />
          {root}
        </p>
      )}
      <ul className="space-y-0.5">
        {paths.map(path => (
          <li key={path} className="text-xs font-mono text-[var(--text-primary)] inline-flex items-center gap-1.5 w-full">
            <FileIcon className="w-3 h-3 text-[var(--text-secondary)]" />
            <span className="truncate">{path}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function inferLanguageFromUri(uri: string): string | null {
  const ext = uri.split('.').pop()?.toLowerCase()
  if (!ext) return null
  const map: Record<string, string> = {
    ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx',
    py: 'python', rb: 'ruby', go: 'go', rs: 'rust', java: 'java',
    md: 'markdown', json: 'json', yaml: 'yaml', yml: 'yaml',
    sh: 'bash', bash: 'bash', sql: 'sql', html: 'html', css: 'css',
    toml: 'toml', xml: 'xml',
  }
  return map[ext] ?? null
}
