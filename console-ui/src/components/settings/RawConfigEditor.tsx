import { AlertTriangle, Code2 } from 'lucide-react'

interface RawConfigEditorProps {
  content: string
  format: string
  readOnly: boolean
  parseError?: string
  onChange: (content: string) => void
}

export function RawConfigEditor({
  content,
  format,
  readOnly,
  parseError,
  onChange,
}: RawConfigEditorProps) {
  return (
    <div className="flex-1 overflow-y-auto space-y-3 pb-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <Code2 className="h-4 w-4" />
          <span className="font-mono">{format}</span>
        </div>
      </div>
      {parseError && (
        <div className="flex items-start gap-2 rounded-lg border border-[var(--ava-danger-border)] bg-[var(--ava-danger-soft)] p-3 text-sm text-[var(--ava-danger)]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{parseError}</span>
        </div>
      )}
      <textarea
        value={content}
        readOnly={readOnly}
        spellCheck={false}
        onChange={(event) => onChange(event.currentTarget.value)}
        className="min-h-[420px] w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] p-3 font-mono text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none disabled:opacity-60"
      />
      <p className="text-xs text-[var(--text-secondary)]">
        保存后对后续任务生效；运行中的任务需要重新派发或重启。
      </p>
    </div>
  )
}
