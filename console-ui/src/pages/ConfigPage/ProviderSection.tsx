import type { ProviderConfig } from './types'
import { Section, FieldLabel, SensitiveInput, CopyableText } from './FormWidgets'

export function ProviderSection({
  name,
  config,
  readOnly,
  onChange,
}: {
  name: string
  config: ProviderConfig
  readOnly: boolean
  onChange: (c: ProviderConfig) => void
}) {
  const hasKey = !!config.apiKey
  return (
    <Section
      title={name}
      infoKey="providers"
      defaultOpen={hasKey}
      badge={hasKey ? <span className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--success)]/15 text-[var(--success)]">已配置</span> : undefined}
    >
      <div className="space-y-3">
        <div>
          <FieldLabel label="apiKey" infoKey="providers" />
          <SensitiveInput value={config.apiKey} onChange={(v) => onChange({ ...config, apiKey: v })} readOnly={readOnly} copyable />
        </div>
        <div>
          <FieldLabel label="apiBase" infoKey="providers" />
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={config.apiBase ?? ''}
              placeholder="使用默认地址"
              onChange={(e) => onChange({ ...config, apiBase: e.target.value || null })}
              readOnly={readOnly}
              className="flex-1 px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
            />
            {config.apiBase && <CopyableText text={config.apiBase} />}
          </div>
        </div>
        <div>
          <FieldLabel label="extraHeaders" />
          <input
            type="text"
            value={config.extraHeaders ? JSON.stringify(config.extraHeaders) : ''}
            placeholder="null (JSON 对象)"
            onChange={(e) => {
              try {
                onChange({ ...config, extraHeaders: e.target.value ? JSON.parse(e.target.value) : null })
              } catch { /* ignore parse error while typing */ }
            }}
            readOnly={readOnly}
            className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
        </div>
      </div>
    </Section>
  )
}
