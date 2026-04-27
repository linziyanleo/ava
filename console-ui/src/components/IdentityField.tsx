import { useState, type MouseEvent } from 'react'
import { Check, Copy } from 'lucide-react'

interface IdentityFieldProps {
  value?: string | null
  label: string
  copyTitle?: string
  className?: string
}

export default function IdentityField({
  value,
  label,
  copyTitle,
  className = '',
}: IdentityFieldProps) {
  const [copied, setCopied] = useState(false)

  if (!value) return null

  const handleCopy = async (event: MouseEvent) => {
    event.stopPropagation()
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className={`flex min-w-0 flex-wrap items-center gap-2 ${className}`}>
      <span className="text-xs text-[var(--text-secondary)]">{label}:</span>
      <span className="min-w-0 break-all font-mono text-xs text-[var(--text-primary)] select-all" title={value}>
        {value}
      </span>
      <button
        type="button"
        onClick={handleCopy}
        className="inline-flex items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
        title={copyTitle || `复制 ${label}`}
      >
        {copied ? (
          <>
            <Check className="h-3 w-3 text-[var(--success)]" />
            已复制
          </>
        ) : (
          <>
            <Copy className="h-3 w-3" />
            复制
          </>
        )}
      </button>
    </div>
  )
}
