import { useEffect, useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import {
  Brain,
  BookOpen,
  Save,
  RefreshCw,
  Calendar,
  Globe,
  User,
  ChevronLeft,
} from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../stores/auth';
import { cn } from '../lib/utils';
import { useResponsiveMode } from '../hooks/useResponsiveMode';
import yaml from 'js-yaml';

// ── Types ──────────────────────────────────────────────────────────────────

interface FileData {
  path: string;
  content: string;
  mtime: number;
}

interface Person {
  key: string;
  displayName: string;
}

interface DiaryEntry {
  date: string;
  filename: string;
}

// ── Helper Functions ───────────────────────────────────────────────────────

function parseHistoryEntries(
  content: string,
): Array<{ date: string; text: string }> {
  const entries: Array<{ date: string; text: string }> = [];
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const record = JSON.parse(trimmed) as { timestamp?: string; content?: string };
      entries.push({
        date: record.timestamp || '',
        text: record.content || '',
      });
    } catch {
      // skip malformed lines
    }
  }
  return entries.reverse();
}

// ── Memory Scope Menu ──────────────────────────────────────────────────────

type MemoryScope = { type: 'global' } | { type: 'person'; key: string; displayName: string };

function ScopeTabs({
  persons,
  scope,
  onSelect,
}: {
  persons: Person[];
  scope: MemoryScope;
  onSelect: (scope: MemoryScope) => void;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto scrollbar-none px-1" style={{ WebkitOverflowScrolling: 'touch' }}>
      <button
        onClick={() => onSelect({ type: 'global' })}
        className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors shrink-0',
          scope.type === 'global'
            ? 'bg-[var(--accent)] text-white'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
        )}
      >
        <Globe className="w-3.5 h-3.5" />
        全局记忆
      </button>
      {persons.map(p => (
        <button
          key={p.key}
          onClick={() => onSelect({ type: 'person', key: p.key, displayName: p.displayName })}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors shrink-0',
            scope.type === 'person' && scope.key === p.key
              ? 'bg-[var(--accent)] text-white'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
          )}
        >
          <User className="w-3.5 h-3.5" />
          {p.displayName}
        </button>
      ))}
    </div>
  );
}

// ── Memory Content (Memory + History tabs) ─────────────────────────────────

function MemoryContent({ scope }: { scope: MemoryScope }) {
  const [activeTab, setActiveTab] = useState<'memory' | 'history'>('memory');
  const [memoryData, setMemoryData] = useState<FileData | null>(null);
  const [historyData, setHistoryData] = useState<FileData | null>(null);
  const [memoryEdit, setMemoryEdit] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const { canEdit } = useAuth();

  const basePath = scope.type === 'global' ? 'workspace/memory' : `workspace/memory/persons/${scope.key}`;

  const loadFiles = useCallback(async () => {
    setMessage(null);
    try {
      const [mem, hist] = await Promise.all([
        api<FileData>(`/files/read?path=${basePath}/MEMORY.md`).catch(() => null),
        api<FileData>(`/files/read?path=${basePath}/history.jsonl`).catch(() => null),
      ]);
      setMemoryData(mem);
      setMemoryEdit(mem?.content || '');
      setHistoryData(hist);
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载失败' });
    }
  }, [basePath]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const saveMemory = async () => {
    if (!memoryData) return;
    setSaving(true);
    setMessage(null);
    try {
      const result = await api<FileData>('/files/write', {
        method: 'PUT',
        body: JSON.stringify({ path: memoryData.path, content: memoryEdit, expected_mtime: memoryData.mtime }),
      });
      setMemoryData({ ...memoryData, content: memoryEdit, mtime: result.mtime });
      setMessage({ type: 'success', text: '保存成功' });
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  const historyEntries = historyData ? parseHistoryEntries(historyData.content) : [];
  const memoryChanged = memoryEdit !== memoryData?.content;

  const scopeLabel = scope.type === 'global' ? '全局' : scope.displayName;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Tabs */}
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4">
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('memory')}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === 'memory'
                ? 'text-[var(--accent)] border-[var(--accent)]'
                : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)]',
            )}
          >
            <Brain className="w-4 h-4" />
            Memory
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === 'history'
                ? 'text-[var(--accent)] border-[var(--accent)]'
                : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)]',
            )}
          >
            <BookOpen className="w-4 h-4" />
            History
            {historyEntries.length > 0 && (
              <span className="text-xs text-[var(--text-secondary)]">({historyEntries.length})</span>
            )}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[var(--text-secondary)]">{scopeLabel}</span>
          <button
            onClick={loadFiles}
            title="刷新"
            className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {message && (
        <div
          className={`mx-4 mt-3 p-2 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}
        >
          {message.text}
        </div>
      )}

      {/* Memory Tab */}
      {activeTab === 'memory' && (
        <div className="flex-1 flex flex-col min-h-0 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">MEMORY.md</h3>
            {canEdit() && memoryData && (
              <button
                onClick={saveMemory}
                disabled={!memoryChanged || saving}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-xs font-medium disabled:opacity-40"
              >
                <Save className="w-3.5 h-3.5" /> {saving ? '保存中...' : '保存'}
              </button>
            )}
          </div>
          <div className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden">
            {memoryData ? (
              <Editor
                height="100%"
                language="markdown"
                theme="vs-dark"
                value={memoryEdit}
                onChange={v => setMemoryEdit(v || '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  readOnly: !canEdit(),
                  wordWrap: 'on',
                  scrollBeyondLastLine: false,
                }}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-[var(--text-secondary)]">文件不存在</div>
            )}
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {historyEntries.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-[var(--text-secondary)]">暂无历史记录</div>
          ) : (
            historyEntries.map((entry, idx) => (
              <div
                key={idx}
                className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg overflow-hidden"
              >
                <div className="px-4 py-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-[var(--accent)] font-mono shrink-0">[{entry.date}]</span>
                  </div>
                  <p className="text-sm text-[var(--text-primary)] whitespace-pre-wrap">{entry.text}</p>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Diary Tab ──────────────────────────────────────────────────────────────

function DiaryTab({ isMobile }: { isMobile?: boolean }) {
  const [diaries, setDiaries] = useState<DiaryEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<FileData | null>(null);
  const [editing, setEditing] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const { canEdit } = useAuth();

  const loadDiaryList = useCallback(async () => {
    try {
      const tree = await api<{ children?: Array<{ name: string; path: string }> }>('/files/tree?root=workspace');
      const diaryFolder = tree.children?.find(c => c.name === 'diary');
      if (diaryFolder && 'children' in diaryFolder) {
        const entries: DiaryEntry[] = ((diaryFolder as { children?: Array<{ name: string }> }).children || [])
          .filter(f => f.name.endsWith('.md'))
          .map(f => ({ date: f.name.replace('.md', ''), filename: f.name }))
          .sort((a, b) => b.date.localeCompare(a.date));
        setDiaries(entries);
        if (entries.length > 0 && !selected) {
          setSelected(entries[0].date);
        }
      }
    } catch {
      setMessage({ type: 'error', text: '加载日记列表失败' });
    }
  }, [selected]);

  useEffect(() => {
    loadDiaryList();
  }, [loadDiaryList]);

  useEffect(() => {
    if (!selected) return;
    api<FileData>(`/files/read?path=workspace/diary/${selected}.md`)
      .then(data => {
        setContent(data);
        setEditing(data.content);
      })
      .catch(() => setContent(null));
  }, [selected]);

  const saveFile = async () => {
    if (!content) return;
    setSaving(true);
    setMessage(null);
    try {
      const result = await api<FileData>('/files/write', {
        method: 'PUT',
        body: JSON.stringify({ path: content.path, content: editing, expected_mtime: content.mtime }),
      });
      setContent({ ...content, content: editing, mtime: result.mtime });
      setMessage({ type: 'success', text: '保存成功' });
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = editing !== content?.content;

  const [showDiaryList, setShowDiaryList] = useState(!isMobile || !selected);

  const diaryListPanel = (
    <div className={cn('bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden', isMobile ? 'flex-1' : 'w-48 shrink-0')}>
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Calendar className="w-4 h-4 text-[var(--accent)]" />
          日记列表
        </h3>
      </div>
      <div className="overflow-y-auto max-h-[calc(100%-3rem)]">
        {diaries.map(d => (
          <button
            key={d.date}
            onClick={() => {
              setSelected(d.date);
              if (isMobile) setShowDiaryList(false);
            }}
            className={cn(
              'w-full px-4 py-2.5 text-left text-sm transition-colors',
              selected === d.date
                ? 'bg-[var(--accent)] text-white'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
            )}
          >
            {d.date}
          </button>
        ))}
        {diaries.length === 0 && (
          <div className="px-4 py-8 text-center text-[var(--text-secondary)] text-sm">暂无日记</div>
        )}
      </div>
    </div>
  );

  const editorPanel = (
    <div className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          {isMobile && (
            <button
              onClick={() => setShowDiaryList(true)}
              className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          )}
          <h3 className="text-sm font-semibold">{selected ? `${selected} 日记` : '选择日期'}</h3>
        </div>
        {canEdit() && content && (
          <button
            onClick={saveFile}
            disabled={!hasChanges || saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-xs font-medium disabled:opacity-40"
          >
            <Save className="w-3.5 h-3.5" /> {saving ? '保存中...' : '保存'}
          </button>
        )}
      </div>
      {message && (
        <div
          className={`mx-4 mt-3 p-2 rounded-lg text-xs ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}
        >
          {message.text}
        </div>
      )}
      <div className="flex-1">
        {content ? (
          <Editor
            height="100%"
            language="markdown"
            theme="vs-dark"
            value={editing}
            onChange={v => setEditing(v || '')}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              readOnly: !canEdit(),
              wordWrap: 'on',
              scrollBeyondLastLine: false,
            }}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-[var(--text-secondary)]">
            {selected ? '加载中...' : '请选择日期查看日记'}
          </div>
        )}
      </div>
    </div>
  );

  if (isMobile) {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        {showDiaryList ? diaryListPanel : editorPanel}
      </div>
    );
  }

  return (
    <div className="flex-1 flex gap-4 min-h-0">
      {diaryListPanel}
      {editorPanel}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

const TABS = [
  { id: 'memory', label: '记忆', icon: Brain },
  { id: 'diary', label: '日记', icon: BookOpen },
] as const;

type TabId = (typeof TABS)[number]['id'];

export default function MemoryPage() {
  const [activeTab, setActiveTab] = useState<TabId>('memory');
  const [persons, setPersons] = useState<Person[]>([]);
  const [scope, setScope] = useState<MemoryScope>({ type: 'global' });
  const { isMobile } = useResponsiveMode();

  // Load persons from identity_map.yaml
  useEffect(() => {
    api<FileData>('/files/read?path=workspace/memory/identity_map.yaml')
      .then(data => {
        const parsed = yaml.load(data.content) as { persons?: Record<string, { display_name?: string }> };
        if (parsed?.persons) {
          const list = Object.entries(parsed.persons).map(([key, val]) => ({
            key,
            displayName: val.display_name || key,
          }));
          setPersons(list);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Brain className="w-6 h-6 text-[var(--accent)]" />
          记忆管理
        </h1>
        <p className="text-[var(--text-secondary)] text-sm mt-1">管理全局记忆、个人记忆和日记</p>
      </div>

      {/* Top Tabs */}
      <div className="flex gap-1 mb-4 border-b border-[var(--border)]">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
              activeTab === tab.id
                ? 'text-[var(--accent)] border-[var(--accent)]'
                : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)]',
            )}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'memory' && (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="mb-3">
            <ScopeTabs persons={persons} scope={scope} onSelect={setScope} />
          </div>
          <div className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden flex flex-col min-h-0">
            <MemoryContent scope={scope} />
          </div>
        </div>
      )}
      {activeTab === 'diary' && <DiaryTab isMobile={isMobile} />}
    </div>
  );
}
