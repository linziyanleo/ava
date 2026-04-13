import { useState, useMemo } from 'react';
import { Plus, Trash2, Clock, Calendar, Repeat, Zap, AlertCircle, CheckCircle2, XCircle } from 'lucide-react';
import type { CronJob, CronSchedule, CronPayload, CronStore } from './types';
import { ToggleSwitch, InfoButton } from './FormWidgets';

const SCHEDULE_KINDS: Array<{ value: CronSchedule['kind']; label: string; icon: React.ReactNode }> = [
  { value: 'cron', label: '周期执行', icon: <Calendar className="w-3.5 h-3.5" /> },
  { value: 'at', label: '定时触发', icon: <Clock className="w-3.5 h-3.5" /> },
  { value: 'every', label: '间隔循环', icon: <Repeat className="w-3.5 h-3.5" /> },
];

const CHANNELS = ['telegram', 'whatsapp', 'discord', 'feishu', 'dingtalk', 'email', 'slack', 'qq', 'mochat', 'matrix'];
const MODEL_TIERS: Array<{ value: string; label: string }> = [
  { value: 'default', label: '默认模型' },
  { value: 'mini', label: '轻量模型' },
];
const PAYLOAD_KINDS: Array<{ value: CronPayload['kind']; label: string }> = [
  { value: 'agent_turn', label: '代理对话' },
  { value: 'system_event', label: '系统事件' },
];
const COMMON_TZ = [
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'America/New_York',
  'America/Los_Angeles',
  'Europe/London',
  'UTC',
];

const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];
const WEEKDAY_CRON = [1, 2, 3, 4, 5, 6, 0];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatMs(ms: number | null): string {
  if (!ms) return '—';
  return new Date(ms).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// export function msToDatetimeLocal(ms: number | null): string {
//   if (!ms) return '';
//   const d = new Date(ms);
//   const offset = d.getTimezoneOffset();
//   const local = new Date(d.getTime() - offset * 60000);
//   return local.toISOString().slice(0, 16);
// }

// export function datetimeLocalToMs(val: string): number | null {
//   if (!val) return null;
//   return new Date(val).getTime();
// }

function msToDateAndTime(ms: number | null): { date: string; time: string } {
  if (!ms) return { date: '', time: '' };
  const d = new Date(ms);
  const offset = d.getTimezoneOffset();
  const local = new Date(d.getTime() - offset * 60000);
  const iso = local.toISOString();
  return { date: iso.slice(0, 10), time: iso.slice(11, 16) };
}

function dateAndTimeToMs(date: string, time: string): number | null {
  if (!date || !time) return null;
  return new Date(`${date}T${time}:00`).getTime();
}

function msToIntervalParts(ms: number | null): { value: number; unit: string } {
  if (!ms || ms <= 0) return { value: 0, unit: 'min' };
  if (ms % 3600000 === 0) return { value: ms / 3600000, unit: 'hour' };
  if (ms % 60000 === 0) return { value: ms / 60000, unit: 'min' };
  return { value: ms / 1000, unit: 'sec' };
}

function intervalPartsToMs(value: number, unit: string): number {
  if (unit === 'hour') return value * 3600000;
  if (unit === 'min') return value * 60000;
  return value * 1000;
}

interface CronParts {
  hour: number;
  minute: number;
  weekdays: number[]; // cron weekdays: 0=Sun, 1=Mon, ...
  isDaily: boolean;
}

function parseCronExpr(expr: string | null): CronParts {
  if (!expr) return { hour: 9, minute: 0, weekdays: [], isDaily: true };
  const parts = expr.trim().split(/\s+/);
  if (parts.length < 5) return { hour: 9, minute: 0, weekdays: [], isDaily: true };
  const minute = parts[0] === '*' ? 0 : parseInt(parts[0], 10) || 0;
  const hour = parts[1] === '*' ? 0 : parseInt(parts[1], 10) || 0;
  const dowField = parts[4];
  if (dowField === '*') {
    return { hour, minute, weekdays: [], isDaily: true };
  }
  const weekdays: number[] = [];
  for (const seg of dowField.split(',')) {
    if (seg.includes('-')) {
      const [a, b] = seg.split('-').map(Number);
      for (let i = a; i <= b; i++) weekdays.push(i);
    } else {
      weekdays.push(Number(seg));
    }
  }
  return { hour, minute, weekdays, isDaily: false };
}

function buildCronExpr(p: CronParts): string {
  const dow = p.isDaily || p.weekdays.length === 0 ? '*' : p.weekdays.sort((a, b) => a - b).join(',');
  return `${p.minute} ${p.hour} * * ${dow}`;
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-[var(--text-secondary)] text-xs">未运行</span>;
  const map: Record<string, { icon: React.ReactNode; cls: string; label: string }> = {
    ok: { icon: <CheckCircle2 className="w-3 h-3" />, cls: 'text-[var(--success)]', label: '成功' },
    error: { icon: <XCircle className="w-3 h-3" />, cls: 'text-[var(--danger)]', label: '失败' },
    skipped: { icon: <AlertCircle className="w-3 h-3" />, cls: 'text-yellow-400', label: '跳过' },
  };
  const s = map[status] ?? { icon: null, cls: 'text-[var(--text-secondary)]', label: status };
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${s.cls}`}>
      {s.icon} {s.label}
    </span>
  );
}

// ─── CronTimeEditor ──────────────────────────────────────────────────────────

function CronTimeEditor({
  expr,
  tz,
  readOnly,
  onExprChange,
  onTzChange,
}: {
  expr: string | null;
  tz: string | null;
  readOnly: boolean;
  onExprChange: (e: string) => void;
  onTzChange: (t: string) => void;
}) {
  const parsed = useMemo(() => parseCronExpr(expr), [expr]);
  const [showRaw, setShowRaw] = useState(false);

  const update = (patch: Partial<CronParts>) => {
    onExprChange(buildCronExpr({ ...parsed, ...patch }));
  };

  const toggleWeekday = (dow: number) => {
    const next = parsed.weekdays.includes(dow) ? parsed.weekdays.filter(d => d !== dow) : [...parsed.weekdays, dow];
    update({ weekdays: next, isDaily: next.length === 0 });
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Time picker */}
        <div>
          <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
            执行时间 <InfoButton tooltip="每天/每周几的几点几分执行" />
          </label>
          <input
            type="time"
            value={`${String(parsed.hour).padStart(2, '0')}:${String(parsed.minute).padStart(2, '0')}`}
            onChange={e => {
              const [h, m] = e.target.value.split(':').map(Number);
              update({ hour: h || 0, minute: m || 0 });
            }}
            readOnly={readOnly}
            className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
        </div>
        {/* Timezone */}
        <div>
          <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
            时区 <InfoButton tooltip="Cron 表达式使用的时区" />
          </label>
          <select
            value={tz ?? 'Asia/Shanghai'}
            onChange={e => onTzChange(e.target.value)}
            disabled={readOnly}
            className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          >
            {COMMON_TZ.map(t => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        {/* Raw toggle */}
        <div>
          <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
            Cron 表达式 <InfoButton tooltip="自动生成的 cron 表达式，可手动编辑" />
          </label>
          {showRaw ? (
            <input
              type="text"
              value={expr ?? ''}
              onChange={e => onExprChange(e.target.value)}
              readOnly={readOnly}
              className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
            />
          ) : (
            <div
              className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono text-[var(--text-secondary)] cursor-pointer hover:border-[var(--accent)] transition-colors"
              onClick={() => !readOnly && setShowRaw(true)}
              title="点击编辑原始表达式"
            >
              {expr || '0 9 * * *'}
            </div>
          )}
        </div>
      </div>

      {/* Weekday selector */}
      <div>
        <div className="flex items-center gap-2 mb-1.5">
          <label className="text-xs text-[var(--text-secondary)] flex items-center gap-1">
            重复日 <InfoButton tooltip="选择每周哪几天执行，不选则每天执行" />
          </label>
          {!parsed.isDaily && (
            <button
              type="button"
              onClick={() => update({ weekdays: [], isDaily: true })}
              disabled={readOnly}
              className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              重置为每天
            </button>
          )}
        </div>
        <div className="flex gap-1.5">
          {WEEKDAY_LABELS.map((label, idx) => {
            const dow = WEEKDAY_CRON[idx];
            const active = !parsed.isDaily && parsed.weekdays.includes(dow);
            return (
              <button
                key={dow}
                type="button"
                disabled={readOnly}
                onClick={() => toggleWeekday(dow)}
                className={`w-9 h-9 rounded-lg text-xs font-medium transition-colors ${
                  active
                    ? 'bg-[var(--accent)] text-white'
                    : parsed.isDaily
                      ? 'bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/30'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                } ${readOnly ? 'cursor-not-allowed' : ''}`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <p className="text-[10px] text-[var(--text-secondary)] mt-1">
          {parsed.isDaily
            ? '每天执行'
            : `每周${parsed.weekdays
                .map(d => {
                  const idx = WEEKDAY_CRON.indexOf(d);
                  return idx >= 0 ? WEEKDAY_LABELS[idx] : d;
                })
                .join('、')}执行`}
        </p>
      </div>
    </div>
  );
}

// ─── AtTimeEditor ────────────────────────────────────────────────────────────

function AtTimeEditor({
  atMs,
  readOnly,
  onChange,
}: {
  atMs: number | null;
  readOnly: boolean;
  onChange: (ms: number | null) => void;
}) {
  const { date, time } = msToDateAndTime(atMs);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div>
        <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
          日期 <InfoButton tooltip="任务执行的日期" />
        </label>
        <input
          type="date"
          value={date}
          onChange={e => onChange(dateAndTimeToMs(e.target.value, time || '12:00'))}
          readOnly={readOnly}
          className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
        />
      </div>
      <div>
        <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
          时间 <InfoButton tooltip="任务执行的时间" />
        </label>
        <input
          type="time"
          value={time}
          onChange={e => onChange(dateAndTimeToMs(date || new Date().toISOString().slice(0, 10), e.target.value))}
          readOnly={readOnly}
          className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
        />
      </div>
    </div>
  );
}

// ─── Single Job Card ─────────────────────────────────────────────────────────

function JobCard({
  job,
  readOnly,
  onChange,
  onDelete,
}: {
  job: CronJob;
  readOnly: boolean;
  onChange: (j: CronJob) => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const disabled = !job.enabled;

  const updateSchedule = (patch: Partial<CronSchedule>) => {
    onChange({ ...job, schedule: { ...job.schedule, ...patch } });
  };
  const updatePayload = (patch: Partial<CronPayload>) => {
    onChange({ ...job, payload: { ...job.payload, ...patch } });
  };

  const intervalParts = msToIntervalParts(job.schedule.everyMs);
  const [intervalUnit, setIntervalUnit] = useState(intervalParts.unit);

  return (
    <div
      className={`bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden transition-opacity ${disabled ? 'opacity-50' : ''}`}
    >
      {/* Card Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <button
          type="button"
          className="flex-1 flex items-center gap-3 text-left min-w-0"
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex items-center gap-2 min-w-0">
            <Zap
              className={`w-4 h-4 shrink-0 ${job.enabled ? 'text-[var(--accent)]' : 'text-[var(--text-secondary)]'}`}
            />
            <span className="text-sm font-semibold truncate">{job.name || job.id}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {job.deleteAfterRun && (
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-yellow-500/15 text-yellow-400">一次性</span>
            )}
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
              {job.source === 'schedule' ? '预设' : 'CLI'}
            </span>
            <StatusBadge status={job.state.lastStatus} />
          </div>
        </button>
        <div className="flex items-center gap-2 ml-3" onClick={e => e.stopPropagation()}>
          {!readOnly && (
            <button
              type="button"
              onClick={onDelete}
              className="p-1.5 rounded-md text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[var(--danger)]/10 transition-colors"
              title="删除任务"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
          <ToggleSwitch value={job.enabled} onChange={v => onChange({ ...job, enabled: v })} readOnly={readOnly} />
        </div>
      </div>

      {/* Card Body */}
      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-[var(--border)]">
          {/* ── 基本信息 ── */}
          <div className="pt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                任务名称 <InfoButton tooltip="任务的显示名称" />
              </label>
              <input
                type="text"
                value={job.name}
                onChange={e => onChange({ ...job, name: e.target.value })}
                readOnly={readOnly}
                className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                任务 ID <InfoButton tooltip="任务的唯一标识符" />
              </label>
              <input
                type="text"
                value={job.id}
                readOnly
                className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono text-[var(--text-secondary)] opacity-70"
              />
            </div>
          </div>

          {/* ── 调度设置 ── */}
          <div>
            <label className="text-xs font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" /> 调度方式{' '}
              <InfoButton tooltip="选择任务的调度类型：周期执行 / 定时触发 / 间隔循环" />
            </label>
            <div className="flex gap-1.5 mb-3">
              {SCHEDULE_KINDS.map(sk => (
                <button
                  key={sk.value}
                  type="button"
                  disabled={readOnly}
                  onClick={() => updateSchedule({ kind: sk.value })}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    job.schedule.kind === sk.value
                      ? 'bg-[var(--accent)] text-white'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  } ${readOnly ? 'cursor-not-allowed' : ''}`}
                >
                  {sk.icon} {sk.label}
                </button>
              ))}
            </div>

            {job.schedule.kind === 'cron' && (
              <CronTimeEditor
                expr={job.schedule.expr}
                tz={job.schedule.tz}
                readOnly={readOnly}
                onExprChange={e => updateSchedule({ expr: e })}
                onTzChange={t => updateSchedule({ tz: t })}
              />
            )}

            {job.schedule.kind === 'at' && (
              <AtTimeEditor
                atMs={job.schedule.atMs}
                readOnly={readOnly}
                onChange={ms => updateSchedule({ atMs: ms })}
              />
            )}

            {job.schedule.kind === 'every' && (
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                    间隔时长 <InfoButton tooltip="每隔多长时间执行一次" />
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={intervalParts.value || ''}
                    onChange={e => {
                      const v = Number(e.target.value) || 0;
                      updateSchedule({ everyMs: intervalPartsToMs(v, intervalUnit) });
                    }}
                    readOnly={readOnly}
                    className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
                  />
                </div>
                <select
                  value={intervalUnit}
                  onChange={e => {
                    setIntervalUnit(e.target.value);
                    updateSchedule({ everyMs: intervalPartsToMs(intervalParts.value, e.target.value) });
                  }}
                  disabled={readOnly}
                  className="px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
                >
                  <option value="sec">秒</option>
                  <option value="min">分钟</option>
                  <option value="hour">小时</option>
                </select>
              </div>
            )}
          </div>

          {/* ── 执行内容 ── */}
          <div>
            <label className="text-xs font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-1">
              <Zap className="w-3.5 h-3.5" /> 执行配置 <InfoButton tooltip="任务触发时执行的动作" />
            </label>
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                    动作类型 <InfoButton tooltip="agent_turn: 发起代理对话; system_event: 触发系统事件" />
                  </label>
                  <select
                    value={job.payload.kind}
                    onChange={e => updatePayload({ kind: e.target.value as CronPayload['kind'] })}
                    disabled={readOnly}
                    className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
                  >
                    {PAYLOAD_KINDS.map(pk => (
                      <option key={pk.value} value={pk.value}>
                        {pk.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                    模型层级 <InfoButton tooltip="default: 使用主力模型; mini: 使用轻量模型" />
                  </label>
                  <select
                    value={job.payload.modelTier ?? 'default'}
                    onChange={e => updatePayload({ modelTier: e.target.value as 'default' | 'mini' })}
                    disabled={readOnly}
                    className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
                  >
                    {MODEL_TIERS.map(mt => (
                      <option key={mt.value} value={mt.value}>
                        {mt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                  消息内容 <InfoButton tooltip="发送给代理的消息文本" />
                </label>
                <textarea
                  value={job.payload.message}
                  onChange={e => updatePayload({ message: e.target.value })}
                  readOnly={readOnly}
                  rows={2}
                  className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors resize-y"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="flex items-center justify-between md:col-span-1">
                  <label className="text-xs text-[var(--text-secondary)] flex items-center gap-1">
                    推送回复 <InfoButton tooltip="是否将执行结果推送到指定渠道" />
                  </label>
                  <ToggleSwitch
                    value={job.payload.deliver}
                    onChange={v => updatePayload({ deliver: v })}
                    readOnly={readOnly}
                  />
                </div>
                {job.payload.deliver && (
                  <>
                    <div>
                      <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                        推送渠道 <InfoButton tooltip="回复推送到哪个消息渠道" />
                      </label>
                      <select
                        value={job.payload.channel ?? ''}
                        onChange={e => updatePayload({ channel: e.target.value || null })}
                        disabled={readOnly}
                        className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
                      >
                        <option value="">请选择</option>
                        {CHANNELS.map(ch => (
                          <option key={ch} value={ch}>
                            {ch}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-xs text-[var(--text-secondary)] mb-1 flex items-center gap-1">
                        目标用户 <InfoButton tooltip="接收消息的用户 ID（如手机号、Telegram user ID 等）" />
                      </label>
                      <input
                        type="text"
                        value={job.payload.to ?? ''}
                        onChange={e => updatePayload({ to: e.target.value || null })}
                        readOnly={readOnly}
                        className="w-full px-3 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
                      />
                    </div>
                  </>
                )}
              </div>

              <div className="flex items-center justify-between">
                <label className="text-xs text-[var(--text-secondary)] flex items-center gap-1">
                  执行后删除 <InfoButton tooltip="开启后任务执行一次就自动删除" />
                </label>
                <ToggleSwitch
                  value={job.deleteAfterRun}
                  onChange={v => onChange({ ...job, deleteAfterRun: v })}
                  readOnly={readOnly}
                />
              </div>
            </div>
          </div>

          {/* ── 运行状态 ── */}
          <div className="border-t border-[var(--border)] pt-3">
            <label className="text-xs font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-1">
              运行状态 <InfoButton tooltip="任务的运行时状态信息（只读）" />
            </label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div className="px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
                <p className="text-[10px] text-[var(--text-secondary)] mb-0.5">上次运行</p>
                <p className="text-xs font-mono">{formatMs(job.state.lastRunAtMs)}</p>
              </div>
              <div className="px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
                <p className="text-[10px] text-[var(--text-secondary)] mb-0.5">下次运行</p>
                <p className="text-xs font-mono">{formatMs(job.state.nextRunAtMs)}</p>
              </div>
              <div className="px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
                <p className="text-[10px] text-[var(--text-secondary)] mb-0.5">上次状态</p>
                <StatusBadge status={job.state.lastStatus} />
              </div>
              <div className="px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
                <p className="text-[10px] text-[var(--text-secondary)] mb-0.5">创建时间</p>
                <p className="text-xs font-mono">{formatMs(job.createdAtMs)}</p>
              </div>
            </div>
            {job.state.lastError && (
              <div className="mt-2 px-3 py-2 rounded-lg bg-[var(--danger)]/10 text-[var(--danger)] text-xs">
                {job.state.lastError}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Editor ─────────────────────────────────────────────────────────────

export function CronJobsEditor({
  store,
  readOnly,
  onChange,
}: {
  store: CronStore;
  readOnly: boolean;
  onChange: (s: CronStore) => void;
}) {
  const updateJob = (idx: number, job: CronJob) => {
    const jobs = [...store.jobs];
    jobs[idx] = { ...job, updatedAtMs: Date.now() };
    onChange({ ...store, jobs });
  };

  const deleteJob = (idx: number) => {
    if (!confirm(`确认删除任务「${store.jobs[idx].name || store.jobs[idx].id}」？`)) return;
    onChange({ ...store, jobs: store.jobs.filter((_, i) => i !== idx) });
  };

  const addJob = () => {
    const newJob: CronJob = {
      id: Math.random().toString(36).slice(2, 10),
      name: '新任务',
      enabled: false,
      schedule: { kind: 'cron', atMs: null, everyMs: null, expr: '0 9 * * *', tz: 'Asia/Shanghai' },
      payload: { kind: 'agent_turn', message: '', deliver: false, channel: null, to: null, modelTier: 'default' },
      state: {
        nextRunAtMs: null,
        lastRunAtMs: null,
        lastStatus: null,
        lastError: null,
        taskCompletedAtMs: null,
        taskCycleId: null,
      },
      createdAtMs: Date.now(),
      updatedAtMs: Date.now(),
      deleteAfterRun: false,
      source: 'cli',
    };
    onChange({ ...store, jobs: [...store.jobs, newJob] });
  };

  return (
    <div className="space-y-4">
      {store.jobs.length === 0 && <div className="text-center py-12 text-[var(--text-secondary)]">暂无定时任务</div>}
      {store.jobs.map((job, idx) => (
        <JobCard
          key={job.id}
          job={job}
          readOnly={readOnly}
          onChange={j => updateJob(idx, j)}
          onDelete={() => deleteJob(idx)}
        />
      ))}
      {!readOnly && (
        <button
          type="button"
          onClick={addJob}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 border-dashed border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
        >
          <Plus className="w-4 h-4" /> 添加任务
        </button>
      )}
    </div>
  );
}
