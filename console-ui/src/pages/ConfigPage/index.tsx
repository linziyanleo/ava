import { useEffect, useState, useRef, useCallback } from 'react'
import { Save, RefreshCw, FileJson } from 'lucide-react';
import { api } from '../../api/client'
import { RawConfigEditor } from '../../components/settings/RawConfigEditor'
import type { ConfigData, NanobotConfig, ChannelBase, GatewayConfig } from './types'
import { Section } from './FormWidgets'
import { AgentDefaultsSection } from './AgentDefaultsSection'
import { ChannelSection } from './ChannelSection'
import { ProviderSection } from './ProviderSection'
import { GatewaySection } from './GatewaySection'
import { ToolsSection } from './ToolsSection'
import { TokenStatsSection } from './TokenStatsSection'

type ConfigTab = 'main';
type ConfigPageMode = 'nanobot' | 'console' | 'legacy' | 'codex' | 'claude_code' | 'image_gen'
type EditableConfig = Partial<NanobotConfig> & { gateway?: GatewayConfig }

const CONFIG_PATH: Record<ConfigPageMode, string> = {
  nanobot: 'nanobot-config.json',
  console: 'console-config.json',
  legacy: 'config.json',
  codex: 'codex-config.toml',
  claude_code: 'claude-code-settings.json',
  image_gen: 'image-gen-config.json',
}

const PAGE_COPY: Record<ConfigPageMode, { title: string; description: string; tab: string }> = {
  nanobot: {
    title: 'Nanobot 配置',
    description: 'Agent 专属模型、provider、channel 与工具配置',
    tab: 'Nanobot',
  },
  console: {
    title: 'Console 配置',
    description: 'Console / Gateway 通用运行配置',
    tab: 'Console',
  },
  legacy: {
    title: '配置管理',
    description: '兼容旧 config.json 编辑入口',
    tab: '主配置',
  },
  codex: {
    title: 'Codex 配置',
    description: 'AVA 管理的 Codex config.toml，保存后对后续任务生效',
    tab: 'Codex',
  },
  claude_code: {
    title: 'Claude Code 配置',
    description: 'AVA 管理的 Claude Code settings.json，保存后对后续任务生效',
    tab: 'Claude Code',
  },
  image_gen: {
    title: 'Image Gen 配置',
    description: 'AVA 管理的 Image Gen provider 配置，保存后对后续任务生效',
    tab: 'Image Gen',
  },
}

const AGENT_CONFIG_MODES = new Set<ConfigPageMode>(['nanobot', 'codex', 'claude_code', 'image_gen'])

function isAgentConfigMode(mode: ConfigPageMode): boolean {
  return AGENT_CONFIG_MODES.has(mode)
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err || '失败')
}

function parseConfigContent(content: string): EditableConfig {
  return JSON.parse(content) as EditableConfig
}

export default function ConfigPage({ mode = 'legacy' }: { mode?: ConfigPageMode }) {
  const [activeTab, setActiveTab] = useState<ConfigTab>('main');
  const [data, setData] = useState<ConfigData | null>(null);
  const [parsed, setParsed] = useState<EditableConfig | null>(null);
  const [rawContent, setRawContent] = useState('');
  const [parseError, setParseError] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [dirty, setDirty] = useState(false);
  const agentConfigMode = isAgentConfigMode(mode);

  const originalRef = useRef<string>('');

  const loadConfig = useCallback(async () => {
    try {
      const d = await api<ConfigData>(`/config/${CONFIG_PATH[mode]}`);
      setData(d);
      setRawContent(d.content);
      originalRef.current = d.content;
      setParseError('');
      if (isAgentConfigMode(mode)) {
        setParsed(null);
        setDirty(false);
        return;
      }
      try {
        const parsedContent = parseConfigContent(d.content);
        setParsed(parsedContent);
      } catch (err) {
        setParsed(null);
        setParseError(errorText(err));
      }
      setDirty(false);
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载失败' });
    }
  }, [mode]);

  useEffect(() => { loadConfig() }, [loadConfig]);

  const updateParsed = useCallback((updater: (prev: EditableConfig) => EditableConfig) => {
    setParsed(prev => {
      if (!prev) return prev;
      const next = updater(prev as EditableConfig);
      setDirty(true);
      return next;
    });
  }, []);

  const saveConfig = async () => {
    if (!data || (!agentConfigMode && !parsed)) return;
    setSaving(true);
    setMessage(null);
    const content = agentConfigMode ? rawContent : JSON.stringify(parsed as EditableConfig, null, 2);
    try {
      const result = await api<{ mtime: number }>(`/config/${CONFIG_PATH[mode]}`, {
        method: 'PUT',
        body: JSON.stringify({ content, mtime: data.mtime }),
      });
      setData({ ...data, content, mtime: result.mtime });
      setRawContent(content);
      originalRef.current = content;
      setDirty(false);
      setMessage({ type: 'success', text: agentConfigMode ? '保存成功；后续任务将读取新配置，运行中的任务需要重新派发或重启。' : '保存成功' });
    } catch (err: unknown) {
      const text = err instanceof Error ? err.message : '保存失败';
      setMessage({ type: 'error', text });
    } finally {
      setSaving(false);
    }
  };

  const readOnly = false;

  const TABS = [
    { id: 'main' as const, label: PAGE_COPY[mode].tab, icon: FileJson, desc: CONFIG_PATH[mode] },
  ];

  if (activeTab === 'main' && !data) {
    return (
      <div className="flex h-full min-h-0 flex-col p-4 md:p-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold">{PAGE_COPY[mode].title}</h1>
        </div>
        <div className="text-center py-20 text-[var(--text-secondary)]">加载中...</div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col p-4 md:p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">{PAGE_COPY[mode].title}</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{PAGE_COPY[mode].description}</p>
        </div>
        {activeTab === 'main' && (
          <div className="flex items-center gap-2">
            <button
              onClick={loadConfig}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              重载
            </button>
            <button
              onClick={saveConfig}
              disabled={!dirty || saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors disabled:opacity-40"
            >
              <Save className="w-4 h-4" />
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        )}
      </div>

      <div className="flex gap-1 mb-4 border-b border-[var(--border)]">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-[var(--accent)] text-[var(--accent)]'
                : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
            <span className="text-xs opacity-60">({tab.desc})</span>
          </button>
        ))}
      </div>

      {message && (
        <div
          className={`mb-3 p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}
        >
          {message.text}
        </div>
      )}

      {activeTab === 'main' && !agentConfigMode && parsed && (
        <div className="flex-1 overflow-y-auto space-y-4 pb-8">
          {mode !== 'console' && (parsed as EditableConfig).agents?.defaults && (
            <AgentDefaultsSection
              config={(parsed as EditableConfig).agents!.defaults}
              readOnly={readOnly}
              onChange={defaults => updateParsed(p => ({ ...p, agents: { ...p.agents!, defaults } }))}
              providers={(parsed as EditableConfig).providers}
            />
          )}

          {mode !== 'console' && (parsed as EditableConfig).token_stats && (
            <TokenStatsSection
              config={(parsed as EditableConfig).token_stats!}
              readOnly={readOnly}
              onChange={token_stats => updateParsed(p => ({ ...p, token_stats }))}
            />
          )}

          {mode !== 'console' && (parsed as EditableConfig).channels && (
            <Section title="消息渠道" infoKey="channels" defaultOpen={true}>
              <div className="space-y-3">
                {Object.entries((parsed as EditableConfig).channels!).map(([name, channelConfig]) => {
                  if (typeof channelConfig !== 'object' || channelConfig === null) return null;
                  if (!('enabled' in channelConfig)) return null;
                  return (
                    <ChannelSection
                      key={name}
                      name={name}
                      config={channelConfig as ChannelBase}
                      readOnly={readOnly}
                      onChange={c => updateParsed(p => ({ ...p, channels: { ...p.channels, [name]: c } }))}
                    />
                  );
                })}
              </div>
            </Section>
          )}

          {mode !== 'console' && (parsed as EditableConfig).providers && (
            <Section title="LLM 服务商" infoKey="providers" defaultOpen={true}>
              <div className="space-y-3">
                {Object.entries((parsed as EditableConfig).providers!).map(([name, providerConfig]) => (
                  <ProviderSection
                    key={name}
                    name={name}
                    config={providerConfig}
                    readOnly={readOnly}
                    onChange={c => updateParsed(p => ({ ...p, providers: { ...p.providers, [name]: c } }))}
                  />
                ))}
              </div>
            </Section>
          )}

          {(parsed as EditableConfig).gateway && (
            <GatewaySection
              config={(parsed as EditableConfig).gateway!}
              readOnly={readOnly}
              onChange={gateway => updateParsed(p => ({ ...p, gateway }))}
            />
          )}

          {mode !== 'console' && (parsed as EditableConfig).tools && (
            <ToolsSection
              config={(parsed as EditableConfig).tools!}
              readOnly={readOnly}
              onChange={tools => updateParsed(p => ({ ...p, tools }))}
            />
          )}
        </div>
      )}

      {activeTab === 'main' && (agentConfigMode || !parsed) && data && (
        <RawConfigEditor
          content={rawContent}
          format={data.format}
          readOnly={readOnly}
          parseError={parseError}
          onChange={(content) => {
            setRawContent(content);
            setDirty(true);
            setParseError('');
          }}
        />
      )}
    </div>
  );
}
