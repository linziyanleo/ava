import type { ToolsConfig } from './types'
import { Section, FieldLabel, ArrayField, renderField } from './FormWidgets'

export function ToolsSection({
  config,
  readOnly,
  onChange,
}: {
  config: ToolsConfig
  readOnly: boolean
  onChange: (c: ToolsConfig) => void
}) {
  return (
    <Section title="工具配置" infoKey="tools.restrictToWorkspace">
      <div className="space-y-3">
        {renderField('restrictToWorkspace', config.restrictToWorkspace, 'tools.restrictToWorkspace', readOnly, (v) =>
          onChange({ ...config, restrictToWorkspace: v as boolean }),
        )}
        {renderField('restrictConfigFile', config.restrictConfigFile, 'tools.restrictConfigFile', readOnly, (v) =>
          onChange({ ...config, restrictConfigFile: v as boolean }),
        )}
      </div>

      {config.web && (
        <div className="mt-3">
          <Section title="网页工具" infoKey="tools.web.proxy" defaultOpen={false}>
            <div className="space-y-3">
              {renderField('proxy', config.web.proxy, 'tools.web.proxy', readOnly, (v) =>
                onChange({ ...config, web: { ...config.web!, proxy: (v as string) || null } }),
              )}
              {config.web.search && (
                <div>
                  <FieldLabel label="search" />
                  <div className="ml-3 pl-3 border-l border-[var(--border)] space-y-3">
                    {renderField('apiKey', config.web.search.apiKey, 'tools.web.search.apiKey', readOnly, (v) =>
                      onChange({ ...config, web: { ...config.web!, search: { ...config.web!.search, apiKey: v as string } } }),
                    )}
                    {renderField('maxResults', config.web.search.maxResults, 'tools.web.search.maxResults', readOnly, (v) =>
                      onChange({ ...config, web: { ...config.web!, search: { ...config.web!.search, maxResults: v as number } } }),
                    )}
                  </div>
                </div>
              )}
            </div>
          </Section>
        </div>
      )}

      {config.exec && (
        <div className="mt-3">
          <Section title="Shell 执行" infoKey="tools.exec.timeout" defaultOpen={false}>
            <div className="space-y-3">
              {renderField('timeout', config.exec.timeout, 'tools.exec.timeout', readOnly, (v) =>
                onChange({ ...config, exec: { ...config.exec!, timeout: v as number } }),
              )}
              {renderField('pathAppend', config.exec.pathAppend ?? '', 'tools.exec.pathAppend', readOnly, (v) =>
                onChange({ ...config, exec: { ...config.exec!, pathAppend: v as string } }),
              )}
              {renderField('autoVenv', config.exec.autoVenv ?? true, 'tools.exec.autoVenv', readOnly, (v) =>
                onChange({ ...config, exec: { ...config.exec!, autoVenv: v as boolean } }),
              )}
            </div>
          </Section>
        </div>
      )}

      {config.mcpServers && Object.keys(config.mcpServers).length > 0 && (
        <div className="mt-3">
          <Section title="MCP 服务器" infoKey="tools.mcpServers" defaultOpen={false}>
            <div className="space-y-3">
              {Object.entries(config.mcpServers).map(([serverName, serverConfig]) => (
                <Section key={serverName} title={serverName} defaultOpen={false}>
                  <div className="space-y-3">
                    {renderField('command', serverConfig.command, 'tools.mcpServers', readOnly, (v) =>
                      onChange({
                        ...config,
                        mcpServers: { ...config.mcpServers, [serverName]: { ...serverConfig, command: v as string } },
                      }),
                    )}
                    <div>
                      <FieldLabel label="args" />
                      <ArrayField
                        value={serverConfig.args ?? []}
                        onChange={(v) =>
                          onChange({
                            ...config,
                            mcpServers: { ...config.mcpServers, [serverName]: { ...serverConfig, args: v } },
                          })
                        }
                        readOnly={readOnly}
                      />
                    </div>
                    {renderField('url', serverConfig.url, 'tools.mcpServers', readOnly, (v) =>
                      onChange({
                        ...config,
                        mcpServers: { ...config.mcpServers, [serverName]: { ...serverConfig, url: v as string } },
                      }),
                    )}
                    {renderField('toolTimeout', serverConfig.toolTimeout, 'tools.mcpServers', readOnly, (v) =>
                      onChange({
                        ...config,
                        mcpServers: { ...config.mcpServers, [serverName]: { ...serverConfig, toolTimeout: v as number } },
                      }),
                    )}
                  </div>
                </Section>
              ))}
            </div>
          </Section>
        </div>
      )}
    </Section>
  )
}
