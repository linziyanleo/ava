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
  const imageGen = {
    timeout: config.imageGen?.timeout ?? 300,
    background: config.imageGen?.background ?? true,
    autoContinue: config.imageGen?.autoContinue ?? false,
    autoSend: config.imageGen?.autoSend ?? true,
  }

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

      <div className="mt-3">
        <Section title="图片生成" infoKey="tools.imageGen.timeout" defaultOpen={false}>
          <div className="space-y-3">
            {renderField('timeout', imageGen.timeout, 'tools.imageGen.timeout', readOnly, (v) =>
              onChange({ ...config, imageGen: { ...imageGen, timeout: v as number } }),
            )}
            {renderField('background', imageGen.background, 'tools.imageGen.background', readOnly, (v) =>
              onChange({ ...config, imageGen: { ...imageGen, background: v as boolean } }),
            )}
            {renderField('autoContinue', imageGen.autoContinue, 'tools.imageGen.autoContinue', readOnly, (v) =>
              onChange({ ...config, imageGen: { ...imageGen, autoContinue: v as boolean } }),
            )}
            {renderField('autoSend', imageGen.autoSend, 'tools.imageGen.autoSend', readOnly, (v) =>
              onChange({ ...config, imageGen: { ...imageGen, autoSend: v as boolean } }),
            )}
          </div>
        </Section>
      </div>

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
