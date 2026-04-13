import { useEffect, useState, useCallback, useRef } from 'react'
import { Save, RefreshCw, AlertCircle, Info } from 'lucide-react';
import { api } from '../../api/client'
import type { ConfigData } from './types'

interface ExtraConfigEditorProps {
  readOnly: boolean;
}

export function ExtraConfigEditor({ readOnly }: ExtraConfigEditorProps) {
  const [data, setData] = useState<ConfigData | null>(null);
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const originalRef = useRef('');

  const loadExtra = useCallback(async () => {
    setMessage(null);
    setNotFound(false);
    try {
      const d = await api<ConfigData>('/config/extra_config.json');
      setData(d);
      const formatted = formatJson(d.content);
      setContent(formatted);
      originalRef.current = formatted;
      setDirty(false);
      setJsonError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('404') || msg.includes('not found') || msg.includes('Not Found')) {
        setNotFound(true);
        const template = JSON.stringify(EXTRA_CONFIG_TEMPLATE, null, 2);
        setContent(template);
        originalRef.current = '';
        setDirty(false);
      } else {
        setMessage({ type: 'error', text: msg || '加载失败' });
      }
    }
  }, []);

  useEffect(() => { loadExtra() }, [loadExtra]);

  const handleContentChange = (value: string) => {
    setContent(value);
    setDirty(value !== originalRef.current);
    try {
      JSON.parse(value);
      setJsonError(null);
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'JSON 格式错误');
    }
  };

  const saveExtra = async () => {
    if (jsonError) return;
    setSaving(true);
    setMessage(null);
    try {
      const formatted = formatJson(content);
      const mtime = data?.mtime ?? 0;
      const result = await api<{ mtime: number }>('/config/extra_config.json', {
        method: 'PUT',
        body: JSON.stringify({ content: formatted, mtime }),
      });
      setData({ content: formatted, mtime: result.mtime, format: 'json' });
      setContent(formatted);
      originalRef.current = formatted;
      setDirty(false);
      setNotFound(false);
      setMessage({ type: 'success', text: '保存成功' });
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <Info className="w-4 h-4" />
          <span>扩展配置会 deep merge 到主配置之上，扩展配置优先级更高。不纳入 Git 版本控制。</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadExtra}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            重载
          </button>
          {!readOnly && (
            <button
              onClick={saveExtra}
              disabled={!dirty || saving || !!jsonError}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors disabled:opacity-40"
            >
              <Save className="w-4 h-4" />
              {saving ? '保存中...' : notFound ? '创建文件' : '保存'}
            </button>
          )}
        </div>
      </div>

      {message && (
        <div className={`mb-3 p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}>
          {message.text}
        </div>
      )}

      {notFound && (
        <div className="mb-3 p-3 rounded-lg text-sm bg-[var(--warning,#f59e0b)]/10 text-[var(--warning,#f59e0b)] flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          extra_config.json 尚未创建。下方为模板内容，编辑后点击「创建文件」即可生成。
        </div>
      )}

      {jsonError && (
        <div className="mb-3 p-2 rounded-lg text-xs bg-[var(--danger)]/10 text-[var(--danger)] font-mono">
          JSON 语法错误: {jsonError}
        </div>
      )}

      <textarea
        value={content}
        onChange={e => handleContentChange(e.target.value)}
        readOnly={readOnly}
        spellCheck={false}
        className="flex-1 w-full p-4 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-[var(--text-primary)] font-mono text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)]"
        placeholder='{ "providers": { ... }, "agents": { "defaults": { ... } } }'
      />
    </div>
  );
}

function formatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

const EXTRA_CONFIG_TEMPLATE = {
  providers: {
    anthropic: {
      apiKey: "",
      apiBase: null
    },
    openai: {
      apiKey: "",
      apiBase: null
    },
    gemini: {
      apiKey: "",
      apiBase: null
    }
  },
  channels: {
    telegram: {
      token: ""
    }
  },
  tools: {
    claudeCode: {
      apiKey: "",
      baseUrl: ""
    },
    web: {
      search: {
        apiKey: ""
      }
    }
  }
};
