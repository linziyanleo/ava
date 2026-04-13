import type { GatewayConfig } from './types'
import { Section, renderField } from './FormWidgets'

export function GatewaySection({
  config,
  readOnly,
  onChange,
}: {
  config: GatewayConfig
  readOnly: boolean
  onChange: (c: GatewayConfig) => void
}) {
  return (
    <Section title="网关配置" infoKey="gateway.host">
      <div className="space-y-3">
        {renderField('host', config.host, 'gateway.host', readOnly, (v) => onChange({ ...config, host: v as string }))}
        {renderField('port', config.port, 'gateway.port', readOnly, (v) => onChange({ ...config, port: v as number }))}
      </div>
      {config.console && (
        <div className="mt-3">
          <Section title="Web 控制台" infoKey="gateway.console.enabled" defaultOpen={false}>
            <div className="space-y-3">
              {Object.entries(config.console).map(([key, val]) =>
                renderField(key, val, `gateway.console.${key}`, readOnly, (v) =>
                  onChange({ ...config, console: { ...config.console!, [key]: v } }),
                ),
              )}
            </div>
          </Section>
        </div>
      )}
    </Section>
  )
}
