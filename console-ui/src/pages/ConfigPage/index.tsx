import { useEffect, useState, useRef, useCallback } from 'react'
import { Code, FormInput, Save, RefreshCw, FileJson } from 'lucide-react';
import { api } from '../../api/client'
import { AgentConfigForm } from '../../components/settings/AgentConfigForm'
import { RawConfigEditor } from '../../components/settings/RawConfigEditor'
import type { ConfigData, NanobotConfig, ChannelBase, GatewayConfig } from './types'
import { Section } from './FormWidgets'
import { AgentDefaultsSection } from './AgentDefaultsSection'
import { ChannelSection } from './ChannelSection'
import { ProviderSection } from './ProviderSection'
import { GatewaySection } from './GatewaySection'
import { ToolsSection } from './ToolsSection'
import { TokenStatsSection } from './TokenStatsSection'

type AgentSchemaResponse = { filename: string; schema: Record<string, unknown> }
type ServerFieldError = { path: string; message: string }
type AgentEditMode = 'visual' | 'raw'

function isJsonFormat(format: string | undefined): boolean {
  return (format || '').toLowerCase() === 'json'
}

function parseAgentContent(content: string, format: string): Record<string, unknown> | null {
  if (!content.trim()) return {}
  if (isJsonFormat(format)) {
    try {
      const parsed = JSON.parse(content)
      return typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : null
    } catch {
      return null
    }
  }
  // tiny TOML reader for the agent-config subset (top-level scalars + arrays of strings)
  const out: Record<string, unknown> = {}
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.replace(/#.*$/, '').trim()
    if (!line) continue
    const eq = line.indexOf('=')
    if (eq <= 0) continue
    const key = line.slice(0, eq).trim()
    const valueLiteral = line.slice(eq + 1).trim()
    out[key] = parseTomlValue(valueLiteral)
  }
  return out
}

function parseTomlValue(literal: string): unknown {
  if (!literal) return ''
  if (literal === 'true') return true
  if (literal === 'false') return false
  if (/^-?\d+$/.test(literal)) return Number.parseInt(literal, 10)
  if (/^-?\d+\.\d+$/.test(literal)) return Number.parseFloat(literal)
  if ((literal.startsWith('"') && literal.endsWith('"')) || (literal.startsWith("'") && literal.endsWith("'"))) {
    return literal.slice(1, -1)
  }
  if (literal.startsWith('[') && literal.endsWith(']')) {
    return literal
      .slice(1, -1)
      .split(',')
      .map((part) => parseTomlValue(part.trim()))
      .filter((value) => value !== '')
  }
  return literal
}

function serialiseAgentValue(value: Record<string, unknown>, format: string): string {
  if (isJsonFormat(format)) return JSON.stringify(value, null, 2)
  // tiny TOML writer for the same subset
  const lines: string[] = []
  for (const [key, raw] of Object.entries(value)) {
    if (raw === undefined || raw === null) continue
    if (typeof raw === 'string') {
      lines.push(`${key} = ${JSON.stringify(raw)}`)
    } else if (typeof raw === 'number' || typeof raw === 'boolean') {
      lines.push(`${key} = ${raw}`)
    } else if (Array.isArray(raw) && raw.every((item) => typeof item === 'string')) {
      lines.push(`${key} = [${(raw as string[]).map((item) => JSON.stringify(item)).join(', ')}]`)
    } else {
      // complex value — fall back to JSON inline (TOML inline tables would be more correct,
      // but the v1 schemas for the four adapters never reach here).
      lines.push(`${key} = ${JSON.stringify(raw)}`)
    }
  }
  return lines.join('\n') + (lines.length ? '\n' : '')
}

function parseServerErrors(detail: unknown): ServerFieldError[] {
  if (!detail) return []
  if (typeof detail === 'string') return [{ path: '/', message: detail }]
  if (typeof detail === 'object') {
    const obj = detail as { errors?: unknown }
    if (Array.isArray(obj.errors)) {
      return obj.errors.flatMap((row) => {
        if (row && typeof row === 'object' && 'path' in row && 'message' in row) {
          const r = row as ServerFieldError
          return [{ path: String(r.path), message: String(r.message) }]
        }
        return []
      })
    }
  }
  return []
}

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
  const [agentSchema, setAgentSchema] = useState<Record<string, unknown> | null>(null);
  const [agentValue, setAgentValue] = useState<Record<string, unknown> | null>(null);
  const [agentEditMode, setAgentEditMode] = useState<AgentEditMode>('visual');
  const [serverErrors, setServerErrors] = useState<ServerFieldError[]>([]);
  const agentConfigMode = isAgentConfigMode(mode);

  const originalRef = useRef<string>('');

  const loadConfig = useCallback(async () => {
    try {
      const d = await api<ConfigData>(`/config/${CONFIG_PATH[mode]}`);
      setData(d);
      setRawContent(d.content);
      originalRef.current = d.content;
      setParseError('');
      setServerErrors([]);
      if (isAgentConfigMode(mode)) {
        setParsed(null);
        setDirty(false);
        // Best-effort schema fetch; on 404 fall back to Raw mode quietly.
        try {
          const schemaResp = await api<AgentSchemaResponse>(`/config/${CONFIG_PATH[mode]}/schema`);
          setAgentSchema(schemaResp.schema);
          const parsedAgent = parseAgentContent(d.content, d.format);
          if (parsedAgent !== null) {
            setAgentValue(parsedAgent);
            setAgentEditMode('visual');
          } else {
            setAgentValue(null);
            setAgentEditMode('raw');
          }
        } catch {
          setAgentSchema(null);
          setAgentValue(null);
          setAgentEditMode('raw');
        }
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
    setServerErrors([]);
    let content: string;
    if (!agentConfigMode) {
      content = JSON.stringify(parsed as EditableConfig, null, 2);
    } else if (agentEditMode === 'visual' && agentValue) {
      content = serialiseAgentValue(agentValue, data.format);
    } else {
      content = rawContent;
    }
    const url = `/api/config/${CONFIG_PATH[mode]}`;
    const res = await fetch(url, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, mtime: data.mtime }),
    });
    if (res.status === 422) {
      const body = await res.json().catch(() => ({}));
      const errs = parseServerErrors(body?.detail);
      setServerErrors(errs);
      setMessage({
        type: 'error',
        text: errs.length
          ? `保存失败：${errs.length} 项校验错误`
          : '保存失败：服务端 schema 校验未通过',
      });
      setSaving(false);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const text = typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`;
      setMessage({ type: 'error', text });
      setSaving(false);
      return;
    }
    const result = (await res.json()) as { mtime: number };
    setData({ ...data, content, mtime: result.mtime });
    setRawContent(content);
    originalRef.current = content;
    setDirty(false);
    setMessage({
      type: 'success',
      text: agentConfigMode
        ? '保存成功；后续任务将读取新配置，运行中的任务需要重新派发或重启。'
        : '保存成功',
    });
    setSaving(false);
  };

  const switchAgentEditMode = useCallback(
    (next: AgentEditMode) => {
      if (!data) return;
      if (next === 'visual') {
        const parsedNow = parseAgentContent(rawContent, data.format);
        if (parsedNow === null) {
          setMessage({
            type: 'error',
            text: '当前内容无法解析为 visual 表单（语法错误），请先在 Raw 模式修正。',
          });
          return;
        }
        setAgentValue(parsedNow);
        setMessage(null);
        setAgentEditMode('visual');
      } else {
        if (agentValue) {
          const next = serialiseAgentValue(agentValue, data.format);
          setRawContent(next);
        }
        setAgentEditMode('raw');
      }
    },
    [agentValue, data, rawContent],
  );

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
          className={`mb-3 p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--ava-success-soft)] text-[var(--ava-success)]' : 'bg-[var(--ava-danger-soft)] text-[var(--ava-danger)]'}`}
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

      {activeTab === 'main' && agentConfigMode && data && (
        <div className="flex-1 overflow-y-auto pb-8 space-y-3">
          {agentSchema && (
            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={() => switchAgentEditMode('visual')}
                className={`inline-flex items-center gap-1 rounded border px-2 py-1 ${
                  agentEditMode === 'visual'
                    ? 'bg-zinc-100 dark:bg-zinc-800'
                    : 'hover:bg-zinc-50 dark:hover:bg-zinc-900'
                }`}
                disabled={readOnly}
              >
                <FormInput className="h-4 w-4" /> Visual
              </button>
              <button
                type="button"
                onClick={() => switchAgentEditMode('raw')}
                className={`inline-flex items-center gap-1 rounded border px-2 py-1 ${
                  agentEditMode === 'raw'
                    ? 'bg-zinc-100 dark:bg-zinc-800'
                    : 'hover:bg-zinc-50 dark:hover:bg-zinc-900'
                }`}
                disabled={readOnly}
              >
                <Code className="h-4 w-4" /> Raw
              </button>
              {agentEditMode === 'visual' && (
                <span className="text-zinc-500">schema-driven 表单 · 字段错误实时校验</span>
              )}
              {agentEditMode === 'raw' && (
                <span className="text-zinc-500">直接编辑 {data.format.toUpperCase()} 文本</span>
              )}
            </div>
          )}
          {!agentSchema && (
            <div className="text-xs text-zinc-500">
              该配置文件未提供 JSON Schema（GET /schema 404），已 fallback 到 Raw 模式。
            </div>
          )}
          {agentEditMode === 'visual' && agentSchema && agentValue && (
            <AgentConfigForm
              schema={agentSchema}
              value={agentValue}
              readOnly={readOnly}
              serverErrors={serverErrors}
              onChange={(next) => {
                setAgentValue(next);
                setDirty(true);
              }}
            />
          )}
          {agentEditMode === 'raw' && (
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
      )}

      {activeTab === 'main' && !agentConfigMode && !parsed && data && (
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
