import { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Trash2, Heart, Clock, CheckCircle2, Edit3, Save, X, RefreshCw } from 'lucide-react';
import { InfoButton } from './FormWidgets';
import { renderField, Section } from './FormWidgets';
import type { HeartbeatConfig } from './types';
import { api } from '../../api/client';

interface HeartbeatTask {
  id: string;
  title: string;
  body: string;
  section: 'active' | 'completed';
}

interface HeartbeatFileData {
  content: string;
  mtime: number;
}

function parseHeartbeatMd(content: string): HeartbeatTask[] {
  const tasks: HeartbeatTask[] = [];
  let currentSection: 'active' | 'completed' = 'active';
  let currentTask: HeartbeatTask | null = null;
  let bodyLines: string[] = [];
  let idCounter = 0;

  const flushTask = () => {
    if (currentTask) {
      currentTask.body = bodyLines.join('\n').trim();
      tasks.push(currentTask);
      currentTask = null;
      bodyLines = [];
    }
  };

  for (const line of content.split('\n')) {
    const trimmed = line.trim();

    if (/^## Active Tasks/i.test(trimmed) || /^## 活跃任务/i.test(trimmed)) {
      flushTask();
      currentSection = 'active';
      continue;
    }
    if (/^## Completed/i.test(trimmed) || /^## 已完成/i.test(trimmed)) {
      flushTask();
      currentSection = 'completed';
      continue;
    }
    if (/^# /.test(trimmed)) {
      continue;
    }

    if (/^### /.test(trimmed)) {
      flushTask();
      idCounter++;
      currentTask = {
        id: `task-${idCounter}`,
        title: trimmed.replace(/^### /, ''),
        body: '',
        section: currentSection,
      };
      continue;
    }

    if (currentTask) {
      if (!/^<!--.*-->$/.test(trimmed)) {
        bodyLines.push(line);
      }
    }
  }
  flushTask();

  return tasks;
}

function serializeHeartbeatMd(tasks: HeartbeatTask[], intervalMin: number): string {
  const active = tasks.filter(t => t.section === 'active');
  const completed = tasks.filter(t => t.section === 'completed');

  let md = `# Heartbeat Tasks\n\n`;
  md += `This file is checked every ${intervalMin} minutes by your nanobot agent.\n`;
  md += `Add tasks below that you want the agent to work on periodically.\n\n`;
  md += `If this file has no tasks (only headers and comments), the agent will skip the heartbeat.\n\n`;
  md += `## Active Tasks\n\n`;

  if (active.length === 0) {
    md += `<!-- Add your periodic tasks below this line -->\n\n`;
  } else {
    for (const task of active) {
      md += `### ${task.title}\n\n`;
      if (task.body.trim()) {
        md += `${task.body.trim()}\n\n`;
      }
    }
  }

  md += `## Completed\n\n`;
  if (completed.length === 0) {
    md += `<!-- Move completed tasks here or delete them -->\n`;
  } else {
    for (const task of completed) {
      md += `### ${task.title}\n\n`;
      if (task.body.trim()) {
        md += `${task.body.trim()}\n\n`;
      }
    }
  }

  return md;
}

function TaskCard({
  task,
  readOnly,
  onChange,
  onDelete,
  onMoveSection,
}: {
  task: HeartbeatTask;
  readOnly: boolean;
  onChange: (t: HeartbeatTask) => void;
  onDelete: () => void;
  onMoveSection: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(task.title);
  const [editBody, setEditBody] = useState(task.body);
  const isCompleted = task.section === 'completed';

  const handleSave = () => {
    onChange({ ...task, title: editTitle, body: editBody });
    setEditing(false);
  };

  const handleCancel = () => {
    setEditTitle(task.title);
    setEditBody(task.body);
    setEditing(false);
  };

  return (
    <div className={`bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden transition-opacity ${isCompleted ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <Heart className={`w-4 h-4 shrink-0 ${isCompleted ? 'text-[var(--text-secondary)]' : 'text-red-400'}`} />
          {editing ? (
            <input
              type="text"
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              className="flex-1 px-2 py-1 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
              autoFocus
            />
          ) : (
            <span className={`text-sm font-semibold truncate ${isCompleted ? 'line-through' : ''}`}>
              {task.title}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 ml-3">
          {!readOnly && !editing && (
            <>
              <button
                type="button"
                onClick={() => { setEditing(true); setEditTitle(task.title); setEditBody(task.body); }}
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors"
                title="编辑任务"
              >
                <Edit3 className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={onMoveSection}
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--success)] hover:bg-[var(--success)]/10 transition-colors"
                title={isCompleted ? '标记为活跃' : '标记为完成'}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={onDelete}
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[var(--danger)]/10 transition-colors"
                title="删除任务"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </>
          )}
          {editing && (
            <>
              <button type="button" onClick={handleSave}
                className="p-1.5 rounded-md text-[var(--success)] hover:bg-[var(--success)]/10 transition-colors" title="保存">
                <Save className="w-3.5 h-3.5" />
              </button>
              <button type="button" onClick={handleCancel}
                className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--danger)] transition-colors" title="取消">
                <X className="w-3.5 h-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {(task.body.trim() || editing) && (
        <div className="px-4 pb-3 border-t border-[var(--border)] pt-2">
          {editing ? (
            <textarea
              value={editBody}
              onChange={e => setEditBody(e.target.value)}
              rows={4}
              className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors resize-y"
            />
          ) : (
            <pre className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap font-mono leading-relaxed">
              {task.body}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function CountdownDisplay({ interval_s }: { interval_s: number }) {
  const [remaining, setRemaining] = useState<string>('');
  const startRef = useRef(Date.now());

  useEffect(() => {
    startRef.current = Date.now();
    const tick = () => {
      const elapsed = Math.floor((Date.now() - startRef.current) / 1000);
      const left = Math.max(0, interval_s - (elapsed % interval_s));
      const m = Math.floor(left / 60);
      const s = left % 60;
      setRemaining(`${m}:${String(s).padStart(2, '0')}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [interval_s]);

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
      <Clock className="w-4 h-4 text-[var(--accent)]" />
      <div>
        <p className="text-[10px] text-[var(--text-secondary)]">距下次心跳</p>
        <p className="text-sm font-mono font-semibold">{remaining}</p>
      </div>
    </div>
  );
}

export function HeartbeatEditor({
  heartbeatConfig,
  readOnly,
  onConfigChange,
}: {
  heartbeatConfig: HeartbeatConfig | undefined;
  readOnly: boolean;
  onConfigChange: (c: HeartbeatConfig) => void;
}) {
  const [tasks, setTasks] = useState<HeartbeatTask[]>([]);
  const [fileData, setFileData] = useState<HeartbeatFileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadHeartbeat = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<{ path: string; content: string; mtime: number }>(
        `/files/read?path=workspace/HEARTBEAT.md`,
      );
      setFileData({ content: data.content, mtime: data.mtime });
      setTasks(parseHeartbeatMd(data.content));
      setDirty(false);
    } catch {
      setTasks([]);
      setFileData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadHeartbeat(); }, [loadHeartbeat]);

  const intervalMin = heartbeatConfig?.interval_s ? Math.round(heartbeatConfig.interval_s / 60) : 60;

  const updateTasks = (newTasks: HeartbeatTask[]) => {
    setTasks(newTasks);
    setDirty(true);
  };

  const saveHeartbeat = async () => {
    setSaving(true);
    setMessage(null);
    const content = serializeHeartbeatMd(tasks, intervalMin);
    try {
      const result = await api<{ path: string; content: string; mtime: number }>(`/files/write`, {
        method: 'PUT',
        body: JSON.stringify({
          path: 'workspace/HEARTBEAT.md',
          content,
          expected_mtime: fileData?.mtime ?? 0,
        }),
      });
      setFileData({ content, mtime: result.mtime });
      setDirty(false);
      setMessage({ type: 'success', text: '保存成功' });
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  const addTask = () => {
    const newTask: HeartbeatTask = {
      id: `task-${Date.now()}`,
      title: '新任务',
      body: '',
      section: 'active',
    };
    updateTasks([...tasks, newTask]);
  };

  const deleteTask = (id: string) => {
    if (!confirm('确认删除此任务？')) return;
    updateTasks(tasks.filter(t => t.id !== id));
  };

  const moveSection = (id: string) => {
    updateTasks(tasks.map(t =>
      t.id === id ? { ...t, section: t.section === 'active' ? 'completed' : 'active' } : t,
    ));
  };

  const activeTasks = tasks.filter(t => t.section === 'active');
  const completedTasks = tasks.filter(t => t.section === 'completed');

  if (loading) {
    return <div className="text-center py-12 text-[var(--text-secondary)]">加载中...</div>;
  }

  return (
    <div className="space-y-4">
      {/* 心跳状态概览 */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Heart className="w-4 h-4 text-red-400" /> 心跳状态
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={loadHeartbeat}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-xs transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" /> 刷新
            </button>
            {!readOnly && dirty && (
              <button
                onClick={saveHeartbeat}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-xs font-medium transition-colors disabled:opacity-40"
              >
                <Save className="w-3.5 h-3.5" /> {saving ? '保存中...' : '保存任务'}
              </button>
            )}
          </div>
        </div>

        {message && (
          <div
            className={`mb-3 p-2 rounded-lg text-xs ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}
          >
            {message.text}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {heartbeatConfig && <CountdownDisplay interval_s={heartbeatConfig.interval_s} />}
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
            <div>
              <p className="text-[10px] text-[var(--text-secondary)]">心跳间隔</p>
              <p className="text-sm font-mono font-semibold">{intervalMin} 分钟</p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
            <div>
              <p className="text-[10px] text-[var(--text-secondary)]">活跃任务</p>
              <p className="text-sm font-semibold">{activeTasks.length}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
            <div>
              <p className="text-[10px] text-[var(--text-secondary)]">已完成</p>
              <p className="text-sm font-semibold">{completedTasks.length}</p>
            </div>
          </div>
        </div>
      </div>

      {/* 心跳基础配置 */}
      {heartbeatConfig && (
        <Section title="心跳配置" infoKey="agents.defaults.heartbeat.enabled" defaultOpen={false}>
          <div className="space-y-3">
            {renderField('enabled', heartbeatConfig.enabled, 'agents.defaults.heartbeat.enabled', readOnly, v =>
              onConfigChange({ ...heartbeatConfig, enabled: v as boolean }),
            )}
            {renderField(
              'interval_s',
              heartbeatConfig.interval_s,
              'agents.defaults.heartbeat.interval_s',
              readOnly,
              v => onConfigChange({ ...heartbeatConfig, interval_s: v as number }),
            )}
            {renderField(
              'phrase1.model',
              heartbeatConfig.phrase1?.model ?? '',
              'agents.defaults.heartbeat.phrase1.model',
              readOnly,
              v => onConfigChange({ ...heartbeatConfig, phrase1: { model: v as string } }),
            )}
            {renderField(
              'phrase2.model',
              heartbeatConfig.phrase2?.model ?? '',
              'agents.defaults.heartbeat.phrase2.model',
              readOnly,
              v => onConfigChange({ ...heartbeatConfig, phrase2: { model: v as string } }),
            )}
          </div>
        </Section>
      )}

      {/* 活跃任务 */}
      <div>
        <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2 flex items-center gap-1.5">
          活跃任务 <InfoButton tooltip="心跳检查时，LLM 会读取这些任务并决定是否执行" />
        </h3>
        <div className="space-y-3">
          {activeTasks.length === 0 && (
            <div className="text-center py-8 text-[var(--text-secondary)] text-sm">暂无活跃任务</div>
          )}
          {activeTasks.map(task => (
            <TaskCard
              key={task.id}
              task={task}
              readOnly={readOnly}
              onChange={t => updateTasks(tasks.map(x => (x.id === t.id ? t : x)))}
              onDelete={() => deleteTask(task.id)}
              onMoveSection={() => moveSection(task.id)}
            />
          ))}
          {!readOnly && (
            <button
              type="button"
              onClick={addTask}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 border-dashed border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
            >
              <Plus className="w-4 h-4" /> 添加任务
            </button>
          )}
        </div>
      </div>

      {/* 已完成任务 */}
      {completedTasks.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-2">已完成</h3>
          <div className="space-y-3">
            {completedTasks.map(task => (
              <TaskCard
                key={task.id}
                task={task}
                readOnly={readOnly}
                onChange={t => updateTasks(tasks.map(x => (x.id === t.id ? t : x)))}
                onDelete={() => deleteTask(task.id)}
                onMoveSection={() => moveSection(task.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
