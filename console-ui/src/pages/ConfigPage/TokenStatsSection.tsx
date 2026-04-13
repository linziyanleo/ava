import type { TokenStatsConfig } from './types'
import { Section, renderField } from './FormWidgets'

export function TokenStatsSection({
  config,
  readOnly,
  onChange,
}: {
  config: TokenStatsConfig
  readOnly: boolean
  onChange: (c: TokenStatsConfig) => void
}) {
  return (
    <Section title="Token 用量统计" infoKey="token_stats.enabled" defaultOpen={false}>
      <div className="space-y-3">
        {renderField('enabled', config.enabled, 'token_stats.enabled', readOnly, (v) =>
          onChange({ ...config, enabled: v as boolean }),
        )}
        {renderField('record_full_request_payload', config.record_full_request_payload, 'token_stats.record_full_request_payload', readOnly, (v) =>
          onChange({ ...config, record_full_request_payload: v as boolean }),
        )}
      </div>
    </Section>
  )
}
