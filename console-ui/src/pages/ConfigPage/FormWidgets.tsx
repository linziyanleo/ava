import { useState, useRef } from 'react'
import {
  Eye, EyeOff, Copy, Check, Plus, Trash2, Info,
  ChevronDown, ChevronRight,
} from 'lucide-react'
import { FIELD_INFO, isSensitiveKey } from './constants'

// ─── CopyableText ────────────────────────────────────────────────────────────

export function CopyableText({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      onClick={handleCopy}
      className="ml-1.5 p-1 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
      title="复制到剪贴板"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-[var(--success)]" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

// ─── InfoButton ──────────────────────────────────────────────────────────────

export function InfoButton({ tooltip }: { tooltip: string }) {
  const [show, setShow] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  return (
    <div className="relative inline-flex" ref={ref}>
      <button
        type="button"
        className="p-0.5 rounded text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onClick={e => e.preventDefault()}
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      {show && (
        <div className="absolute z-50 left-full left-2 mb-1.5 px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] whitespace-nowrap shadow-lg">
          {tooltip}
        </div>
      )}
    </div>
  );
}

// ─── SensitiveInput ──────────────────────────────────────────────────────────

function maskValue(val: string): string {
  if (val.length <= 8) return '••••••••'
  return val.slice(0, 4) + '•'.repeat(Math.min(val.length - 8, 24)) + val.slice(-4)
}

export function SensitiveInput({
  value,
  onChange,
  readOnly,
  copyable,
}: {
  value: string
  onChange: (v: string) => void
  readOnly: boolean
  copyable?: boolean
}) {
  const [revealed, setRevealed] = useState(false)

  return (
    <div className="flex items-center gap-1.5">
      <div className="relative flex-1">
        <input
          type="text"
          value={revealed ? value : maskValue(value)}
          onChange={(e) => { if (revealed) onChange(e.target.value) }}
          readOnly={readOnly || !revealed}
          className={`w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors ${readOnly ? 'opacity-70' : ''} ${!revealed ? 'text-[var(--text-secondary)]' : ''}`}
        />
      </div>
      <button
        type="button"
        onClick={() => setRevealed(!revealed)}
        className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
        title={revealed ? '隐藏' : '显示'}
      >
        {revealed ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
      </button>
      {copyable && value && <CopyableText text={value} />}
    </div>
  )
}

// ─── ModelBadge ──────────────────────────────────────────────────────────────

export function ModelBadge({ value }: { value: string }) {
  if (!value) return <span className="text-[var(--text-secondary)] text-sm">未设置</span>
  const parts = value.split('/')
  if (parts.length < 2) return <span className="font-mono text-sm">{value}</span>
  return (
    <span className="inline-flex items-center gap-1">
      <span className="px-1.5 py-0.5 rounded bg-[var(--accent)]/15 text-[var(--accent)] text-xs font-medium">{parts[0]}</span>
      <span className="text-[var(--text-secondary)] text-xs">/</span>
      <span className="font-mono text-sm">{parts.slice(1).join('/')}</span>
    </span>
  )
}

// ─── ArrayField ──────────────────────────────────────────────────────────────

export function ArrayField({
  value,
  onChange,
  readOnly,
}: {
  value: string[]
  onChange: (v: string[]) => void
  readOnly: boolean
}) {
  const addRow = () => onChange([...value, ''])
  const removeRow = (idx: number) => onChange(value.filter((_, i) => i !== idx))
  const updateRow = (idx: number, v: string) => onChange(value.map((item, i) => (i === idx ? v : item)))

  return (
    <div className="space-y-1.5">
      {value.map((item, idx) => (
        <div key={idx} className="flex items-center gap-1.5">
          <input
            type="text"
            value={item}
            onChange={(e) => updateRow(idx, e.target.value)}
            readOnly={readOnly}
            className="flex-1 px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
          {!readOnly && (
            <button
              type="button"
              onClick={() => removeRow(idx)}
              className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[var(--danger)]/10 transition-colors"
              title="删除"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ))}
      {!readOnly && (
        <button
          type="button"
          onClick={addRow}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors"
        >
          <Plus className="w-3 h-3" /> 添加
        </button>
      )}
    </div>
  )
}

// ─── ToggleSwitch ────────────────────────────────────────────────────────────

export function ToggleSwitch({
  value,
  onChange,
  readOnly,
}: {
  value: boolean
  onChange: (v: boolean) => void
  readOnly: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => !readOnly && onChange(!value)}
      className={`relative w-9 h-5 rounded-full transition-colors ${value ? 'bg-[var(--accent)]' : 'bg-[var(--bg-tertiary)] border border-[var(--border)]'} ${readOnly ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${value ? 'translate-x-4' : 'translate-x-0'}`} />
    </button>
  )
}

// ─── FieldLabel ──────────────────────────────────────────────────────────────

export function FieldLabel({ label, infoKey, children }: { label: string; infoKey?: string; children?: React.ReactNode }) {
  const info = infoKey && FIELD_INFO[infoKey]
  return (
    <div className="flex items-center gap-1.5 mb-1">
      <label className="text-xs font-medium text-[var(--text-secondary)]">{label}</label>
      {info && <InfoButton tooltip={info} />}
      {children}
    </div>
  )
}

// ─── Section (collapsible) ───────────────────────────────────────────────────

export function Section({
  title,
  infoKey,
  defaultOpen = true,
  badge,
  dimmed,
  headerRight,
  children,
}: {
  title: string
  infoKey?: string
  defaultOpen?: boolean
  badge?: React.ReactNode
  dimmed?: boolean
  headerRight?: React.ReactNode
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden transition-opacity ${dimmed ? 'opacity-40' : ''}`}>
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--bg-tertiary)]/30 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="w-4 h-4 text-[var(--text-secondary)]" /> : <ChevronRight className="w-4 h-4 text-[var(--text-secondary)]" />}
          <span className="text-sm font-semibold">{title}</span>
          {infoKey && FIELD_INFO[infoKey] && <InfoButton tooltip={FIELD_INFO[infoKey]} />}
          {badge}
        </div>
        {headerRight && <div onClick={(e) => e.stopPropagation()}>{headerRight}</div>}
      </button>
      {open && <div className="px-4 pb-4 space-y-3">{children}</div>}
    </div>
  )
}

// ─── Generic field renderer ──────────────────────────────────────────────────

export function renderField(
  key: string,
  value: unknown,
  infoPath: string,
  readOnly: boolean,
  onChange: (v: unknown) => void,
): React.ReactNode {
  if (value === null || value === undefined) {
    return (
      <div key={key}>
        <FieldLabel label={key} infoKey={infoPath} />
        <input
          type="text"
          value=""
          placeholder="null"
          onChange={(e) => onChange(e.target.value || null)}
          readOnly={readOnly}
          className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
        />
      </div>
    )
  }

  if (typeof value === 'boolean') {
    return (
      <div key={key} className="flex items-center justify-between">
        <FieldLabel label={key} infoKey={infoPath} />
        <ToggleSwitch value={value} onChange={(v) => onChange(v)} readOnly={readOnly} />
      </div>
    )
  }

  if (typeof value === 'number') {
    return (
      <div key={key}>
        <FieldLabel label={key} infoKey={infoPath} />
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          readOnly={readOnly}
          className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
        />
      </div>
    )
  }

  if (typeof value === 'string') {
    const isModel = key === 'model' || key === 'visionModel' || key === 'miniModel' || key === 'voiceModel' || key === 'imageGenModel'
    const isSensitive = isSensitiveKey(key)
    const isCopyable = key === 'apiKey' || key === 'apiBase'

    if (isModel && value.includes('/')) {
      return (
        <div key={key}>
          <FieldLabel label={key} infoKey={infoPath} />
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <input
                type="text"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                readOnly={readOnly}
                className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
              />
            </div>
            <ModelBadge value={value} />
          </div>
        </div>
      )
    }

    if (isSensitive) {
      return (
        <div key={key}>
          <FieldLabel label={key} infoKey={infoPath} />
          <SensitiveInput value={value} onChange={(v) => onChange(v)} readOnly={readOnly} copyable={isCopyable} />
        </div>
      )
    }

    return (
      <div key={key}>
        <FieldLabel label={key} infoKey={infoPath} />
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            readOnly={readOnly}
            className="flex-1 px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
          {isCopyable && value && <CopyableText text={value} />}
        </div>
      </div>
    )
  }

  if (Array.isArray(value)) {
    return (
      <div key={key}>
        <FieldLabel label={key} infoKey={infoPath} />
        <ArrayField
          value={(value as unknown[]).map((v) => String(v ?? ''))}
          onChange={(v) => onChange(v)}
          readOnly={readOnly}
        />
      </div>
    )
  }

  return null
}
