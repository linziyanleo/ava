import { useState } from 'react'
import type { AgentDefaults, NanobotConfig } from './types'
import { Section, FieldLabel, renderField } from './FormWidgets'

const MODEL_FIELDS: Array<{ key: keyof AgentDefaults; label: string }> = [
  { key: 'model', label: 'model' },
  { key: 'visionModel', label: 'visionModel' },
  { key: 'miniModel', label: 'miniModel' },
  { key: 'voiceModel', label: 'voiceModel' },
]

const KNOWN_PROVIDERS = ['openai', 'anthropic', 'google', 'zenmux', 'ollama']

function splitModelValue(val: string | null | undefined): { provider: string; modelName: string } {
  if (!val) return { provider: '', modelName: '' }
  const idx = val.indexOf('/')
  if (idx > 0) return { provider: val.slice(0, idx), modelName: val.slice(idx + 1) }
  return { provider: '', modelName: val }
}

function joinModelValue(provider: string, modelName: string): string | null {
  if (!modelName) return null
  if (provider) return `${provider}/${modelName}`
  return modelName
}

function ModelFieldInput({
  label,
  value,
  infoKey,
  readOnly,
  providerOptions,
  onChange,
}: {
  label: string
  value: string | null | undefined
  infoKey: string
  readOnly: boolean
  providerOptions: string[]
  onChange: (val: string | null) => void
}) {
  const { provider, modelName } = splitModelValue(value as string)
  const [isCustom, setIsCustom] = useState(
    () => !!provider && !providerOptions.includes(provider)
  )

  const handleProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value
    if (v === '__custom__') {
      setIsCustom(true)
      onChange(modelName || null)
    } else {
      setIsCustom(false)
      onChange(joinModelValue(v, modelName))
    }
  }

  const handleModelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isCustom) {
      onChange(e.target.value || null)
    } else {
      onChange(joinModelValue(provider, e.target.value))
    }
  }

  const selectValue = isCustom ? '__custom__' : provider

  return (
    <div>
      <FieldLabel label={label} infoKey={infoKey} />
      {isCustom ? (
        <div className="flex items-center gap-1.5">
          <select
            value="__custom__"
            onChange={handleProviderChange}
            disabled={readOnly}
            className="shrink-0 px-2 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          >
            <option value="">无前缀</option>
            {providerOptions.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
            <option value="__custom__">自定义</option>
          </select>
          <span className="text-[var(--text-secondary)] text-sm">/</span>
          <input
            type="text"
            value={(value as string) ?? ''}
            placeholder="provider/model-name"
            onChange={e => onChange(e.target.value || null)}
            readOnly={readOnly}
            className="flex-1 min-w-0 px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
        </div>
      ) : (
        <div className="flex items-center gap-1.5">
          <select
            value={selectValue}
            onChange={handleProviderChange}
            disabled={readOnly}
            className="shrink-0 px-2 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          >
            <option value="">无前缀</option>
            {providerOptions.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
            <option value="__custom__">自定义</option>
          </select>
          <span className="text-[var(--text-secondary)] text-sm">/</span>
          <input
            type="text"
            value={modelName}
            placeholder="model-name"
            onChange={handleModelChange}
            readOnly={readOnly}
            className="flex-1 min-w-0 px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
        </div>
      )}
    </div>
  )
}

export function AgentDefaultsSection({
  config,
  readOnly,
  onChange,
  providers,
}: {
  config: AgentDefaults
  readOnly: boolean
  onChange: (c: AgentDefaults) => void
  providers?: NanobotConfig['providers']
}) {
  const providerNames = providers ? Object.keys(providers) : []
  const allProviders = Array.from(new Set([...KNOWN_PROVIDERS, ...providerNames]))

  const simpleFields: Array<{ key: keyof AgentDefaults; label: string }> = [
    { key: 'workspace', label: 'workspace' },
    { key: 'maxTokens', label: 'maxTokens' },
    { key: 'temperature', label: 'temperature' },
    { key: 'maxToolIterations', label: 'maxToolIterations' },
    { key: 'memoryWindow', label: 'memoryWindow' },
    { key: 'memoryTier', label: 'memoryTier' },
    { key: 'reasoningEffort', label: 'reasoningEffort' },
  ]

  return (
    <Section title="通用配置" infoKey="agents.defaults.model">
      <div className="space-y-3">
        {/* Provider select */}
        <div>
          <FieldLabel label="provider" infoKey="agents.defaults.provider" />
          <select
            value={config.provider ?? ''}
            onChange={e => onChange({ ...config, provider: e.target.value || undefined })}
            disabled={readOnly}
            className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          >
            <option value="">默认</option>
            {providerNames.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>

        {/* Model fields with provider selector */}
        {MODEL_FIELDS.map(({ key, label }) => (
          <ModelFieldInput
            key={key}
            label={label}
            value={config[key] as string | null}
            infoKey={`agents.defaults.${key}`}
            readOnly={readOnly}
            providerOptions={allProviders}
            onChange={val => onChange({ ...config, [key]: val })}
          />
        ))}

        {simpleFields.map(({ key, label }) => {
          const val = config[key];
          if (val !== undefined && typeof val === 'object' && val !== null) return null;
          return renderField(label, val, `agents.defaults.${key}`, readOnly, v => onChange({ ...config, [key]: v }));
        })}
      </div>

      {config.contextCompression && (
        <div className="mt-4">
          <Section title="上下文压缩" infoKey="agents.defaults.contextCompression.enabled" defaultOpen={false}>
            <div className="space-y-3">
              {Object.entries(config.contextCompression).map(([key, val]) =>
                renderField(key, val, `agents.defaults.contextCompression.${key}`, readOnly, v =>
                  onChange({ ...config, contextCompression: { ...config.contextCompression!, [key]: v } }),
                ),
              )}
            </div>
          </Section>
        </div>
      )}

      {config.inLoopTruncation && (
        <div className="mt-3">
          <Section title="循环内截断" infoKey="agents.defaults.inLoopTruncation.enabled" defaultOpen={false}>
            <div className="space-y-3">
              {Object.entries(config.inLoopTruncation).map(([key, val]) => {
                if (typeof val === 'function') return null;
                return renderField(key, val, `agents.defaults.inLoopTruncation.${key}`, readOnly, v =>
                  onChange({ ...config, inLoopTruncation: { ...config.inLoopTruncation!, [key]: v } }),
                );
              })}
            </div>
          </Section>
        </div>
      )}

    </Section>
  );
}
