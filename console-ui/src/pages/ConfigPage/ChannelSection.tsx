import type { ChannelBase } from './types'
import { Section, ToggleSwitch, FieldLabel, renderField } from './FormWidgets'

export function ChannelSection({
  name,
  config,
  readOnly,
  onChange,
}: {
  name: string
  config: ChannelBase
  readOnly: boolean
  onChange: (c: ChannelBase) => void
}) {
  const enabled = config.enabled

  const handleToggle = (v: boolean) => {
    onChange({ ...config, enabled: v })
  }

  const entries = Object.entries(config).filter(([k]) => k !== 'enabled')

  const updateField = (key: string, val: unknown) => {
    onChange({ ...config, [key]: val })
  }

  return (
    <Section
      title={name}
      infoKey={`channels.${name}`}
      defaultOpen={enabled}
      dimmed={!enabled}
      headerRight={
        <ToggleSwitch value={enabled} onChange={handleToggle} readOnly={readOnly} />
      }
    >
      <div className="space-y-3">
        {entries.map(([key, val]) => {
          if (val !== null && typeof val === 'object' && !Array.isArray(val)) {
            return (
              <div key={key}>
                <FieldLabel label={key} infoKey={`channels.${name}`} />
                <div className="ml-3 pl-3 border-l border-[var(--border)] space-y-3">
                  {Object.entries(val as Record<string, unknown>).map(([subKey, subVal]) =>
                    renderField(
                      subKey,
                      subVal,
                      `channels.${name}`,
                      readOnly || !enabled,
                      (v) => updateField(key, { ...(val as Record<string, unknown>), [subKey]: v }),
                    ),
                  )}
                </div>
              </div>
            )
          }
          return renderField(key, val, `channels.${name}`, readOnly || !enabled, (v) => updateField(key, v))
        })}
      </div>
    </Section>
  )
}
