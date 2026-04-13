import { useEffect, useState, useRef, useCallback } from 'react'
import { Save, RefreshCw, FileJson } from 'lucide-react';
import { api } from '../../api/client'
import { useAuth } from '../../stores/auth'
import type { ConfigData, NanobotConfig, ChannelBase } from './types'
import { Section } from './FormWidgets'
import { AgentDefaultsSection } from './AgentDefaultsSection'
import { ChannelSection } from './ChannelSection'
import { ProviderSection } from './ProviderSection'
import { GatewaySection } from './GatewaySection'
import { ToolsSection } from './ToolsSection'
import { TokenStatsSection } from './TokenStatsSection'

type ConfigTab = 'main';

export default function ConfigPage() {
  const [activeTab, setActiveTab] = useState<ConfigTab>('main');
  const [data, setData] = useState<ConfigData | null>(null);
  const [parsed, setParsed] = useState<NanobotConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [dirty, setDirty] = useState(false);
  const { canEdit } = useAuth();

  const originalRef = useRef<string>('');

  const loadConfig = useCallback(async () => {
    try {
      const d = await api<ConfigData>('/config/config.json');
      setData(d);
      originalRef.current = d.content;
      try {
        setParsed(JSON.parse(d.content));
      } catch {
        setParsed(null);
      }
      setDirty(false);
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载失败' });
    }
  }, []);

  useEffect(() => { loadConfig() }, [loadConfig]);

  const updateParsed = useCallback((updater: (prev: NanobotConfig) => NanobotConfig) => {
    setParsed(prev => {
      if (!prev) return prev;
      const next = updater(prev);
      setDirty(true);
      return next;
    });
  }, []);

  const saveConfig = async () => {
    if (!data || !parsed) return;
    setSaving(true);
    setMessage(null);
    const content = JSON.stringify(parsed, null, 2);
    try {
      const result = await api<{ mtime: number }>('/config/config.json', {
        method: 'PUT',
        body: JSON.stringify({ content, mtime: data.mtime }),
      });
      setData({ ...data, content, mtime: result.mtime });
      originalRef.current = content;
      setDirty(false);
      setMessage({ type: 'success', text: '保存成功' });
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  const readOnly = !canEdit();

  const TABS = [
    { id: 'main' as const, label: '主配置', icon: FileJson, desc: 'config.json' },
  ];

  if (activeTab === 'main' && !parsed) {
    return (
      <div className="h-[calc(100vh-3rem)] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold">配置管理</h1>
        </div>
        <div className="text-center py-20 text-[var(--text-secondary)]">加载中...</div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">配置管理</h1>
        {activeTab === 'main' && (
          <div className="flex items-center gap-2">
            <button
              onClick={loadConfig}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              重载
            </button>
            {canEdit() && (
              <button
                onClick={saveConfig}
                disabled={!dirty || saving}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors disabled:opacity-40"
              >
                <Save className="w-4 h-4" />
                {saving ? '保存中...' : '保存'}
              </button>
            )}
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

      {activeTab === 'main' && parsed && (
        <div className="flex-1 overflow-y-auto space-y-4 pb-8">
          {parsed.agents?.defaults && (
            <AgentDefaultsSection
              config={parsed.agents.defaults}
              readOnly={readOnly}
              onChange={defaults => updateParsed(p => ({ ...p, agents: { ...p.agents, defaults } }))}
              providers={parsed.providers}
            />
          )}

          {parsed.token_stats && (
            <TokenStatsSection
              config={parsed.token_stats}
              readOnly={readOnly}
              onChange={token_stats => updateParsed(p => ({ ...p, token_stats }))}
            />
          )}

          {parsed.channels && (
            <Section title="消息渠道" infoKey="channels" defaultOpen={true}>
              <div className="space-y-3">
                {Object.entries(parsed.channels).map(([name, channelConfig]) => {
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

          {parsed.providers && (
            <Section title="LLM 服务商" infoKey="providers" defaultOpen={true}>
              <div className="space-y-3">
                {Object.entries(parsed.providers).map(([name, providerConfig]) => (
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

          {parsed.gateway && (
            <GatewaySection
              config={parsed.gateway}
              readOnly={readOnly}
              onChange={gateway => updateParsed(p => ({ ...p, gateway }))}
            />
          )}

          {parsed.tools && (
            <ToolsSection
              config={parsed.tools}
              readOnly={readOnly}
              onChange={tools => updateParsed(p => ({ ...p, tools }))}
            />
          )}
        </div>
      )}
    </div>
  );
}
