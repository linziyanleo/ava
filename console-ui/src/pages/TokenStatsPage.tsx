import { useEffect, useState, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  RefreshCw,
  BarChart3,
  List,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Search,
  X,
  SlidersHorizontal,
} from 'lucide-react';
import { useResponsiveMode } from '../hooks/useResponsiveMode';
import ConversationHistoryView from '../components/ConversationHistoryView';
import IdentityField from '../components/IdentityField';
import TraceTimelineDrawer from '../components/TraceTimelineDrawer';
import type { ConversationMeta, TurnGroup as ChatTurnGroup } from './ChatPage/types';
import { getContentText, groupTurns } from './ChatPage/utils';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { api } from '../api/client';
import { useAuth } from '../stores/auth';
import { cn } from '../lib/utils';

interface TokenRecord {
  timestamp: string;
  model: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  session_key: string;
  conversation_id: string;
  turn_seq: number | null;
  iteration: number;
  user_message: string;
  output_content: string;
  system_prompt_preview: string;
  conversation_history: string;
  full_request_payload: string;
  finish_reason: string;
  model_role: string;
  cached_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number;
  tool_names: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string;
}

interface ModelStats {
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
}

interface ProviderStats {
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
}

interface TokenSummary {
  totals: { prompt_tokens: number; completion_tokens: number; total_tokens: number; total_calls: number };
  by_model: ModelStats[];
  by_provider: ProviderStats[];
}

interface RecordsResponse {
  records: TokenRecord[];
  total: number;
}

interface TurnSummaryRecord {
  conversation_id: string;
  turn_seq: number | null;
  trace_id?: string;
  span_id?: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  llm_calls: number;
  models: string;
}

interface TurnIterationRecord {
  conversation_id: string;
  turn_seq: number | null;
  iteration: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cache_creation_tokens: number;
  model: string;
  model_role: string;
  tool_names: string;
  finish_reason: string;
  trace_id?: string;
  span_id?: string;
  parent_span_id?: string;
}

type TokenStatsView = 'records' | 'turns' | 'charts';
type ConversationScope = string | null;
type ChatTurnMap = Record<string, ChatTurnGroup>;

const PIE_COLORS = ['#3b82f6', '#8b5cf6'];

function fmtTooltip(v: number | string | ReadonlyArray<number | string> | undefined): string {
  const raw = Array.isArray(v) ? v[0] : v;
  const numeric = typeof raw === 'number' ? raw : Number(raw);
  return formatTokens(Number.isFinite(numeric) ? numeric : 0);
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function shortModel(model: string): string {
  const parts = model.split('/');
  return parts[parts.length - 1];
}

function parseTurnSeq(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}

function makeTurnKey(convId: string, turnSeq: number): string {
  return `${convId}::${turnSeq}`;
}

function parseTurnKey(value: string | null): { conversationId: string; turnSeq: number } | null {
  if (!value) return null;
  const separator = value.lastIndexOf('::');
  if (separator < 0) return null;
  const turnSeq = Number(value.slice(separator + 2));
  if (!Number.isInteger(turnSeq)) return null;
  return {
    conversationId: value.slice(0, separator),
    turnSeq,
  };
}

function buildConversationQuery(conversationId: ConversationScope): string {
  if (conversationId === null) return '';
  return `&conversation_id=${encodeURIComponent(conversationId)}`;
}

function buildSessionDebugScope(sessionKey: string, conversationId: ConversationScope): string {
  return `${sessionKey}::${conversationId === null ? '__all__' : conversationId}`;
}

function matchesSessionDebugScope(currentScope: string, sessionKey: string, conversationId: string): boolean {
  return (
    currentScope === buildSessionDebugScope(sessionKey, conversationId) ||
    currentScope === buildSessionDebugScope(sessionKey, null)
  );
}

function turnDomId(turnKey: string): string {
  return `token-turn-${encodeURIComponent(turnKey)}`;
}

function truncateLine(text: string, maxLength: number = 96): string {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (!normalized) return '（空输入）';
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}…` : normalized;
}

function getTurnUserPreview(turn?: ChatTurnGroup): string {
  if (!turn) return '无法解析用户输入';
  return truncateLine(getContentText(turn.userMessage.content), 120);
}

function getTurnUserMessage(turn?: ChatTurnGroup): string {
  if (!turn) return '';
  return getContentText(turn.userMessage.content);
}

function getTurnFinalAssistantText(turn?: ChatTurnGroup): string {
  if (!turn) return '';
  const finalAssistant = [...turn.assistantSteps]
    .reverse()
    .find(msg => msg.role === 'assistant' && !msg.tool_calls && getContentText(msg.content));
  return finalAssistant ? getContentText(finalAssistant.content) : '';
}

function getTurnStatus(
  records: TokenRecord[],
  iterations: TurnIterationRecord[],
): {
  label: string;
  className: string;
} {
  const source = records.length > 0 ? records : iterations;
  if (source.some(item => item.model_role === 'pending')) {
    return { label: 'Processing', className: 'bg-amber-500/15 text-amber-400' };
  }
  if (source.some(item => item.model_role === 'error' || /error/i.test(item.finish_reason || ''))) {
    return { label: 'Error', className: 'bg-rose-500/15 text-rose-400' };
  }
  return { label: 'Completed', className: 'bg-emerald-500/15 text-emerald-400' };
}

function sortTurnRecords(records: TokenRecord[]): TokenRecord[] {
  return [...records].sort((a, b) => {
    const iterDiff = (a.iteration ?? 0) - (b.iteration ?? 0);
    if (iterDiff !== 0) return iterDiff;
    return a.timestamp.localeCompare(b.timestamp);
  });
}

// Model role icons with tooltip
const MODEL_ROLE_CONFIG: Record<string, { icon: string; label: string }> = {
  default: { icon: '🤖', label: '主模型' },
  mini: { icon: '⚡', label: '轻量模型' },
  vision: { icon: '👁️', label: '视觉模型' },
  voice: { icon: '🎙️', label: '语音模型' },
  imageGen: { icon: '🎨', label: '图像生成' },
  claude_code: { icon: '💻', label: 'Claude Code' },
  codex: { icon: '💻', label: 'Codex' },
  'page-agent': { icon: '🌐', label: 'Page Agent' },
  pending: { icon: '⏳', label: 'Processing...' },
  error: { icon: '❌', label: '异常终止' },
};

function ModelRoleIcon({ role }: { role: string }) {
  const config = MODEL_ROLE_CONFIG[role] || MODEL_ROLE_CONFIG.default;
  return (
    <span className="relative group/role cursor-help text-base">
      {config.icon}
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded bg-[var(--bg-tertiary)] border border-[var(--border)] text-[10px] text-[var(--text-primary)] whitespace-nowrap opacity-0 group-hover/role:opacity-100 transition-opacity pointer-events-none z-10 shadow-lg">
        {config.label}
      </span>
    </span>
  );
}

function normalizeToolNames(toolNames?: string): string {
  const normalized = toolNames?.trim();
  if (!normalized) return '';

  try {
    const parsed: unknown = JSON.parse(normalized);
    if (Array.isArray(parsed)) {
      return parsed
        .map(item => {
          if (typeof item === 'string') return item.trim();
          if (item == null) return '';
          return typeof item === 'object' ? JSON.stringify(item) : String(item);
        })
        .filter(Boolean)
        .join(', ');
    }
    if (typeof parsed === 'string') {
      return parsed.trim();
    }
  } catch {
    if (normalized.startsWith('[') && normalized.endsWith(']')) {
      return normalized
        .slice(1, -1)
        .split(',')
        .map(part => part.trim().replace(/^['"]|['"]$/g, ''))
        .filter(Boolean)
        .join(', ');
    }
  }

  return normalized;
}

function getCallLabel(toolNames: string, finishReason: string): string {
  const toolLabel = normalizeToolNames(toolNames);
  if (toolLabel) return toolLabel;
  return finishReason === 'end_turn' || finishReason === 'stop' ? 'end' : finishReason || '-';
}

function getCallLabelTone(toolNames: string, finishReason: string): string {
  if (normalizeToolNames(toolNames)) return 'bg-amber-500/15 text-amber-400';
  if (finishReason === 'end_turn' || finishReason === 'stop') return 'bg-emerald-500/15 text-emerald-400';
  return 'bg-gray-500/15 text-gray-400';
}

function CallLabelBadge({
  label,
  className,
  widthClass = 'max-w-[80px]',
  toneClass = 'bg-amber-500/15 text-amber-400',
}: {
  label: string;
  className?: string;
  widthClass?: string;
  toneClass?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex min-w-0 items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-medium',
        toneClass,
        widthClass,
        className,
      )}
      title={label}
    >
      <span className="block min-w-0 max-w-full truncate text-center">{label}</span>
    </span>
  );
}

function formatCacheStatus(cachedTokens: number, cacheCreationTokens: number): React.ReactNode {
  if (!cachedTokens && !cacheCreationTokens) {
    return <span className="text-[var(--text-secondary)]">-</span>;
  }

  const parts: React.ReactNode[] = [];

  if (cacheCreationTokens > 0) {
    parts.push(
      <span key="write" className="text-amber-400" title={`写入缓存 ${cacheCreationTokens.toLocaleString()} tokens`}>
        ✍️ {formatTokens(cacheCreationTokens)}
      </span>,
    );
  }

  if (cachedTokens > 0) {
    parts.push(
      <span key="hit" className="text-emerald-400" title={`命中缓存 ${cachedTokens.toLocaleString()} tokens`}>
        🎯 {formatTokens(cachedTokens)}
      </span>,
    );
  }

  return (
    <span className="flex items-center gap-1.5 text-xs">
      {parts.map((part, i) => (
        <span key={i}>{part}</span>
      ))}
    </span>
  );
}

type TimePreset = 'all' | 'today' | '7d' | '30d' | 'custom';

function getPresetRange(preset: TimePreset): { start?: string; end?: string } {
  if (preset === 'all') return {};
  const now = new Date();
  const end = now.toISOString();
  if (preset === 'today') {
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
    return { start, end };
  }
  if (preset === '7d') {
    const start = new Date(now.getTime() - 7 * 86400000).toISOString();
    return { start, end };
  }
  if (preset === '30d') {
    const start = new Date(now.getTime() - 30 * 86400000).toISOString();
    return { start, end };
  }
  return {};
}

type ModelRoleFilter = 'all' | 'coder' | 'chat' | 'page-agent' | 'mini' | 'voice' | 'vision' | 'error';

const MODEL_ROLE_FILTER_OPTIONS: { value: ModelRoleFilter; label: string; icon: string }[] = [
  { value: 'all', label: '全部', icon: '📊' },
  { value: 'coder', label: 'Coder', icon: '💻' },
  { value: 'chat', label: '主模型', icon: '🤖' },
  { value: 'page-agent', label: 'Page Agent', icon: '🌐' },
  { value: 'mini', label: 'Mini', icon: '⚡' },
  { value: 'voice', label: 'Voice', icon: '🎙️' },
  { value: 'vision', label: 'Vision', icon: '👁️' },
  { value: 'error', label: '异常终止', icon: '❌' },
];

function buildFilterStr(
  sk: string,
  conversationId: string,
  model: string,
  provider: string,
  turnSeq: string,
  preset: TimePreset,
  cStart: string,
  cEnd: string,
  modelRole: ModelRoleFilter,
  traceId: string,
  spanId: string,
): string {
  const params = new URLSearchParams();
  if (sk) params.set('session_key', sk);
  if (conversationId) params.set('conversation_id', conversationId);
  if (model) params.set('model', model);
  if (provider) params.set('provider', provider);
  if (turnSeq) params.set('turn_seq', turnSeq);
  if (traceId) params.set('trace_id', traceId);
  if (spanId) params.set('span_id', spanId);
  if (modelRole && modelRole !== 'all') params.set('model_role', modelRole);
  if (preset === 'custom') {
    if (cStart) params.set('start_time', new Date(cStart).toISOString());
    if (cEnd) params.set('end_time', new Date(cEnd + 'T23:59:59').toISOString());
  } else {
    const { start, end } = getPresetRange(preset);
    if (start) params.set('start_time', start);
    if (end) params.set('end_time', end);
  }
  return params.toString();
}

export default function TokenStatsPage() {
  const { isMobile } = useResponsiveMode();
  const [searchParams, setSearchParams] = useSearchParams();
  const appliedSessionKey = searchParams.get('session_key') || '';
  const hasAppliedConversationFilter = searchParams.has('conversation_id');
  const appliedConversationScope: ConversationScope = hasAppliedConversationFilter
    ? (searchParams.get('conversation_id') ?? '')
    : null;
  const appliedConversationId = appliedConversationScope ?? '';
  const appliedTurnSeq = parseTurnSeq(searchParams.get('turn_seq'));
  const appliedTurnKey =
    appliedTurnSeq != null && appliedConversationScope !== null
      ? makeTurnKey(appliedConversationId, appliedTurnSeq)
      : null;
  const isSessionMode = Boolean(appliedSessionKey);
  const [view, setView] = useState<TokenStatsView>(() => (
    searchParams.get('trace_id') ? 'records' : (searchParams.get('session_key') ? 'turns' : 'records')
  ));
  const [summary, setSummary] = useState<TokenSummary | null>(null);
  const [records, setRecords] = useState<TokenRecord[]>([]);
  const [sessionTurnSummaries, setSessionTurnSummaries] = useState<TurnSummaryRecord[]>([]);
  const [sessionTurnIterations, setSessionTurnIterations] = useState<TurnIterationRecord[]>([]);
  const [sessionChatTurnsByKey, setSessionChatTurnsByKey] = useState<ChatTurnMap>({});
  const [expandedTurnKey, setExpandedTurnKey] = useState<string | null>(appliedTurnKey);
  const [loadingSessionTurns, setLoadingSessionTurns] = useState(false);
  const [turnRecordsByKey, setTurnRecordsByKey] = useState<Record<string, TokenRecord[]>>({});
  const [loadingTurnRecords, setLoadingTurnRecords] = useState<Record<string, boolean>>({});
  const [filtersExpanded, setFiltersExpanded] = useState(!isMobile);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(searchParams.get('trace_id'));
  const [loading, setLoading] = useState(false);
  useAuth();
  const pageSize = 50;

  const [filterSessionKey, setFilterSessionKey] = useState(searchParams.get('session_key') || '');
  const [filterConversationId, setFilterConversationId] = useState(searchParams.get('conversation_id') || '');
  const [filterModel, setFilterModel] = useState(searchParams.get('model') || '');
  const [filterProvider, setFilterProvider] = useState(searchParams.get('provider') || '');
  const [filterTurnSeq, setFilterTurnSeq] = useState(searchParams.get('turn_seq') || '');
  const [filterTraceId, setFilterTraceId] = useState(searchParams.get('trace_id') || '');
  const [filterSpanId, setFilterSpanId] = useState(searchParams.get('span_id') || '');
  const [filterModelRole, setFilterModelRole] = useState<ModelRoleFilter>('all');
  const [timePreset, setTimePreset] = useState<TimePreset>('all');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const sessionDebugScopeRef = useRef(buildSessionDebugScope(appliedSessionKey, appliedConversationScope));

  const filtersRef = useRef({
    filterSessionKey,
    filterConversationId,
    filterModel,
    filterProvider,
    filterTurnSeq,
    filterTraceId,
    filterSpanId,
    filterModelRole,
    timePreset,
    customStart,
    customEnd,
  });
  useEffect(() => {
    sessionDebugScopeRef.current = buildSessionDebugScope(appliedSessionKey, appliedConversationScope);
  }, [appliedConversationScope, appliedSessionKey]);
  useEffect(() => {
    filtersRef.current = {
      filterSessionKey,
      filterConversationId,
      filterModel,
      filterProvider,
      filterTurnSeq,
      filterTraceId,
      filterSpanId,
      filterModelRole,
      timePreset,
      customStart,
      customEnd,
    };
  }, [
    filterSessionKey,
    filterConversationId,
    filterModel,
    filterProvider,
    filterTurnSeq,
    filterTraceId,
    filterSpanId,
    filterModelRole,
    timePreset,
    customStart,
    customEnd,
  ]);

  const loadSummary = useCallback(async () => {
    try {
      const s = await api<TokenSummary>('/stats/tokens');
      setSummary(s);
    } catch {
      /* ignore */
    }
  }, []);

  const loadRecords = useCallback(async (p: number = 0) => {
    setLoading(true);
    try {
      const f = filtersRef.current;
      const filterStr = buildFilterStr(
        f.filterSessionKey,
        f.filterConversationId,
        f.filterModel,
        f.filterProvider,
        f.filterTurnSeq,
        f.timePreset,
        f.customStart,
        f.customEnd,
        f.filterModelRole,
        f.filterTraceId,
        f.filterSpanId,
      );
      const sep = filterStr ? '&' : '';
      const r = await api<RecordsResponse>(
        `/stats/tokens/records?limit=${pageSize}&offset=${p * pageSize}${sep}${filterStr}`,
      );
      setRecords(r.records);
      setTotal(r.total);
      setPage(p);
    } catch {
      /* ignore */
    }
    setLoading(false);
  }, []);

  const loadSessionDebugData = useCallback(async (sessionKey: string, conversationId: ConversationScope = null) => {
    setLoadingSessionTurns(true);
    const convFilter = buildConversationQuery(conversationId);
    const [turnSummaryResult, turnIterationResult, chatTurnsResult] = await Promise.allSettled([
      api<TurnSummaryRecord[]>(`/stats/tokens/by-session?session_key=${encodeURIComponent(sessionKey)}${convFilter}`),
      api<TurnIterationRecord[]>(
        `/stats/tokens/by-session/detailed?session_key=${encodeURIComponent(sessionKey)}${convFilter}`,
      ),
      (async (): Promise<ChatTurnMap> => {
        const toTurnMap = (messages: Parameters<typeof groupTurns>[0], scope: string): ChatTurnMap => {
          const grouped = groupTurns(messages);
          return grouped.reduce<ChatTurnMap>((acc, turn) => {
            if (turn.turnSeq != null) {
              acc[makeTurnKey(scope, turn.turnSeq)] = turn;
            }
            return acc;
          }, {});
        };

        if (conversationId !== null) {
          const messages = await api<Parameters<typeof groupTurns>[0]>(
            `/chat/messages?session_key=${encodeURIComponent(sessionKey)}${convFilter}`,
          );
          return toTurnMap(messages, conversationId);
        }

        const conversations = await api<ConversationMeta[]>(
          `/chat/conversations?session_key=${encodeURIComponent(sessionKey)}`,
        );
        const messageResults = await Promise.allSettled(
          conversations.map(async conversation => {
            const messages = await api<Parameters<typeof groupTurns>[0]>(
              `/chat/messages?session_key=${encodeURIComponent(sessionKey)}${buildConversationQuery(conversation.conversation_id)}`,
            );
            return {
              conversationId: conversation.conversation_id,
              messages,
            };
          }),
        );

        return messageResults.reduce<ChatTurnMap>((acc, result) => {
          if (result.status !== 'fulfilled') return acc;
          return {
            ...acc,
            ...toTurnMap(result.value.messages, result.value.conversationId),
          };
        }, {});
      })(),
    ]);

    if (sessionDebugScopeRef.current !== buildSessionDebugScope(sessionKey, conversationId)) {
      return;
    }

    setSessionTurnSummaries(turnSummaryResult.status === 'fulfilled' ? turnSummaryResult.value : []);
    setSessionTurnIterations(turnIterationResult.status === 'fulfilled' ? turnIterationResult.value : []);
    setSessionChatTurnsByKey(chatTurnsResult.status === 'fulfilled' ? chatTurnsResult.value : {});
    setLoadingSessionTurns(false);
  }, []);

  const ensureTurnRecords = useCallback(
    async (sessionKey: string, turnKey: string, force: boolean = false) => {
      const hasCachedRecords = Object.prototype.hasOwnProperty.call(turnRecordsByKey, turnKey);
      if (!force && (hasCachedRecords || loadingTurnRecords[turnKey])) return;

      const parsed = parseTurnKey(turnKey);
      if (!parsed) return;

      setLoadingTurnRecords(prev => ({ ...prev, [turnKey]: true }));
      try {
        const convFilter = buildConversationQuery(parsed.conversationId);
        const result = await api<RecordsResponse>(
          `/stats/tokens/records?session_key=${encodeURIComponent(sessionKey)}${convFilter}&turn_seq=${parsed.turnSeq}&limit=200`,
        );
        if (!matchesSessionDebugScope(sessionDebugScopeRef.current, sessionKey, parsed.conversationId)) {
          return;
        }
        setTurnRecordsByKey(prev => ({ ...prev, [turnKey]: sortTurnRecords(result.records) }));
      } catch {
        if (matchesSessionDebugScope(sessionDebugScopeRef.current, sessionKey, parsed.conversationId)) {
          setTurnRecordsByKey(prev => ({ ...prev, [turnKey]: [] }));
        }
      } finally {
        if (matchesSessionDebugScope(sessionDebugScopeRef.current, sessionKey, parsed.conversationId)) {
          setLoadingTurnRecords(prev => ({ ...prev, [turnKey]: false }));
        }
      }
    },
    [loadingTurnRecords, turnRecordsByKey],
  );

  // Initial load
  useEffect(() => {
    queueMicrotask(() => {
      void loadSummary();
      void loadRecords(0);
    });
  }, [loadSummary, loadRecords]);

  // Auto-refresh when pending records exist
  const AUTO_REFRESH_MS = 5_000;
  useEffect(() => {
    const hasPendingRecords = records.some(r => r.model_role === 'pending');
    const hasPendingTurns = sessionTurnIterations.some(r => r.model_role === 'pending');
    const shouldRefreshTurns = view === 'turns' && isSessionMode && hasPendingTurns;
    if (!hasPendingRecords && !shouldRefreshTurns) return;

    const timer = setInterval(() => {
      if (shouldRefreshTurns) {
        void loadSessionDebugData(appliedSessionKey, appliedConversationScope);
        if (expandedTurnKey != null) {
          void ensureTurnRecords(appliedSessionKey, expandedTurnKey, true);
        }
      } else {
        void loadRecords(page);
      }
    }, AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [
    appliedConversationScope,
    appliedSessionKey,
    ensureTurnRecords,
    expandedTurnKey,
    isSessionMode,
    loadRecords,
    loadSessionDebugData,
    page,
    records,
    sessionTurnIterations,
    view,
  ]);

  // When URL params change (navigation from other page), sync state and reload
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const sk = searchParams.get('session_key') || '';
    const cv = searchParams.get('conversation_id') || '';
    const m = searchParams.get('model') || '';
    const p = searchParams.get('provider') || '';
    const ts = searchParams.get('turn_seq') || '';
    const tr = searchParams.get('trace_id') || '';
    const sp = searchParams.get('span_id') || '';
    queueMicrotask(() => {
      setFilterSessionKey(sk);
      setFilterConversationId(cv);
      setFilterModel(m);
      setFilterProvider(p);
      setFilterTurnSeq(ts);
      setFilterTraceId(tr);
      setFilterSpanId(sp);
      setSelectedTraceId(tr || null);
      setView(tr ? 'records' : (sk ? 'turns' : 'records'));
      filtersRef.current = {
        ...filtersRef.current,
        filterSessionKey: sk,
        filterConversationId: cv,
        filterModel: m,
        filterProvider: p,
        filterTurnSeq: ts,
        filterTraceId: tr,
        filterSpanId: sp,
      };
      void loadRecords(0);
    });
  }, [searchParams, loadRecords]);

  useEffect(() => {
    if (!appliedSessionKey) {
      setSessionTurnSummaries([]);
      setSessionTurnIterations([]);
      setSessionChatTurnsByKey({});
      setExpandedTurnKey(null);
      setTurnRecordsByKey({});
      setLoadingTurnRecords({});
      setLoadingSessionTurns(false);
      return;
    }

    setTurnRecordsByKey({});
    setLoadingTurnRecords({});
    void loadSessionDebugData(appliedSessionKey, appliedConversationScope);
  }, [appliedConversationScope, appliedSessionKey, loadSessionDebugData]);

  useEffect(() => {
    setExpandedTurnKey(appliedTurnKey);
  }, [appliedSessionKey, appliedTurnKey]);

  useEffect(() => {
    if (!appliedSessionKey || expandedTurnKey == null) return;
    if (Object.prototype.hasOwnProperty.call(turnRecordsByKey, expandedTurnKey) || loadingTurnRecords[expandedTurnKey]) return;
    void ensureTurnRecords(appliedSessionKey, expandedTurnKey, false);
  }, [
    appliedSessionKey,
    ensureTurnRecords,
    expandedTurnKey,
    loadingTurnRecords,
    turnRecordsByKey,
  ]);

  const handleSearch = () => {
    const newParams: Record<string, string> = {};
    if (filterSessionKey) newParams.session_key = filterSessionKey;
    if (filterConversationId) newParams.conversation_id = filterConversationId;
    if (filterModel) newParams.model = filterModel;
    if (filterProvider) newParams.provider = filterProvider;
    if (filterTurnSeq) newParams.turn_seq = filterTurnSeq;
    if (filterTraceId) newParams.trace_id = filterTraceId;
    if (filterSpanId) newParams.span_id = filterSpanId;
    setSelectedTraceId(filterTraceId || null);
    setView(filterTraceId ? 'records' : (filterSessionKey ? 'turns' : 'records'));
    setSearchParams(newParams, { replace: true });
    loadRecords(0);
  };

  const handleClearFilters = () => {
    setFilterSessionKey('');
    setFilterConversationId('');
    setFilterModel('');
    setFilterProvider('');
    setFilterTurnSeq('');
    setFilterTraceId('');
    setFilterSpanId('');
    setFilterModelRole('all');
    setTimePreset('all');
    setCustomStart('');
    setCustomEnd('');
    setSearchParams({}, { replace: true });
	    filtersRef.current = {
	      filterSessionKey: '',
      filterConversationId: '',
      filterModel: '',
      filterProvider: '',
      filterTurnSeq: '',
      filterTraceId: '',
      filterSpanId: '',
      filterModelRole: 'all',
      timePreset: 'all',
      customStart: '',
	      customEnd: '',
	    };
	    setSelectedTraceId(null);
	    setView('records');
    loadRecords(0);
  };

  const handleLeaveSessionMode = () => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('session_key');
    nextParams.delete('conversation_id');
    nextParams.delete('turn_seq');
    setView('records');
    setSearchParams(nextParams, { replace: true });
  };

  const hasFilters =
    filterSessionKey ||
    filterConversationId ||
    filterModel ||
    filterProvider ||
    filterTurnSeq ||
    filterTraceId ||
    filterSpanId ||
    filterModelRole !== 'all' ||
    timePreset !== 'all';

  const totalPages = Math.ceil(total / pageSize);

  const pieData = summary
    ? [
        { name: 'Prompt', value: summary.totals.prompt_tokens },
        { name: 'Completion', value: summary.totals.completion_tokens },
      ]
    : [];

  const turnIterationsByKey = new Map<string, TurnIterationRecord[]>();
  for (const item of sessionTurnIterations) {
    if (item.turn_seq == null) continue;
    const key = makeTurnKey(item.conversation_id || '', item.turn_seq);
    const existing = turnIterationsByKey.get(key) || [];
    existing.push(item);
    turnIterationsByKey.set(key, existing);
  }

  // When turn_seq is specified, filter turn summaries to only show matching turns
  const filteredTurnSummaries = sessionTurnSummaries.filter(turn => {
    if (appliedConversationScope !== null && (turn.conversation_id || '') !== appliedConversationId) {
      return false;
    }
    if (appliedTurnSeq != null && turn.turn_seq !== appliedTurnSeq) {
      return false;
    }
    return true;
  });

  let sessionPromptTokens = 0;
  let sessionCompletionTokens = 0;
  let sessionTotalTokens = 0;
  let sessionLlmCalls = 0;
  const sessionModels = new Set<string>();
  for (const turn of filteredTurnSummaries) {
    sessionPromptTokens += turn.prompt_tokens;
    sessionCompletionTokens += turn.completion_tokens;
    sessionTotalTokens += turn.total_tokens;
    sessionLlmCalls += turn.llm_calls;
    turn.models
      .split(',')
      .map(model => model.trim())
      .filter(Boolean)
      .forEach(model => sessionModels.add(model));
  }
  const sessionTurnCount =
    filteredTurnSummaries.length ||
    Object.entries(sessionChatTurnsByKey).filter(([key, turn]) => {
      if (turn.turnSeq == null) return false;
      if (appliedConversationScope !== null && !key.startsWith(`${appliedConversationId}::`)) {
        return false;
      }
      return appliedTurnSeq == null || turn.turnSeq === appliedTurnSeq;
    }).length;
  const activeTurnLabel = appliedTurnSeq != null ? `Turn #${appliedTurnSeq}` : '全部 Turn';
  const scrollTargetTurnKey =
    appliedTurnKey ??
    (appliedTurnSeq != null && filteredTurnSummaries.length === 1 && filteredTurnSummaries[0]?.turn_seq != null
      ? makeTurnKey(filteredTurnSummaries[0].conversation_id || '', filteredTurnSummaries[0].turn_seq)
      : null);

  useEffect(() => {
    if (appliedTurnKey) {
      setExpandedTurnKey(appliedTurnKey);
      return;
    }
    if (appliedTurnSeq == null) {
      return;
    }
    if (filteredTurnSummaries.length === 1 && filteredTurnSummaries[0]?.turn_seq != null) {
      setExpandedTurnKey(makeTurnKey(filteredTurnSummaries[0].conversation_id || '', filteredTurnSummaries[0].turn_seq));
    }
  }, [appliedTurnKey, appliedTurnSeq, filteredTurnSummaries]);

  useEffect(() => {
    if (view !== 'turns' || scrollTargetTurnKey == null || loadingSessionTurns) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById(turnDomId(scrollTargetTurnKey))?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
    return () => cancelAnimationFrame(frame);
  }, [loadingSessionTurns, scrollTargetTurnKey, view]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {!isMobile && <h1 className="text-2xl font-bold">Token 统计</h1>}
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-medium',
              isSessionMode ? 'bg-cyan-500/15 text-cyan-400' : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
            )}
          >
            {isSessionMode ? '单 Session 调试' : '全局审计'}
          </span>
          <div className="flex bg-[var(--bg-tertiary)] rounded-lg p-0.5">
            <button
              onClick={() => setView('records')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                view === 'records'
                  ? 'bg-[var(--accent)] text-white'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              <List className="w-3.5 h-3.5" />
              {!isMobile && ' 明细'}
            </button>
            {isSessionMode && (
              <button
                onClick={() => setView('turns')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  view === 'turns'
                    ? 'bg-[var(--accent)] text-white'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                {!isMobile && ' Turn 视图'}
                {isMobile && 'T'}
              </button>
            )}
            {!isSessionMode && (
              <button
                onClick={() => {
                  setView('charts');
                  loadSummary();
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  view === 'charts'
                    ? 'bg-[var(--accent)] text-white'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                <BarChart3 className="w-3.5 h-3.5" />
                {!isMobile && ' 聚合'}
              </button>
            )}
          </div>
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={() => {
              if (view === 'records') {
                loadRecords(page);
              }
              if (isSessionMode) {
                void loadSessionDebugData(appliedSessionKey, appliedConversationScope);
                if (view === 'turns' && expandedTurnKey != null) {
                  void ensureTurnRecords(appliedSessionKey, expandedTurnKey, true);
                }
              } else {
                loadSummary();
              }
            }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm"
            title="刷新"
          >
            <RefreshCw className="w-4 h-4" />
            {!isMobile && ' 刷新'}
          </button>
        </div>
      </div>

      {/* Overview Cards */}
      {isSessionMode ? (
        isMobile ? (
          <div className="flex items-center gap-3 mb-3 px-1 text-xs overflow-x-auto">
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">Session:</span>{' '}
              <span className="font-mono text-[var(--text-primary)]">{truncateLine(appliedSessionKey, 28)}</span>
            </span>
            <span className="text-[var(--border)]">|</span>
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">Turns:</span>{' '}
              <span className="font-semibold text-cyan-400">{sessionTurnCount}</span>
            </span>
            <span className="text-[var(--border)]">|</span>
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">Calls:</span>{' '}
              <span className="font-semibold text-purple-400">{sessionLlmCalls}</span>
            </span>
            <span className="text-[var(--border)]">|</span>
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">Total:</span>{' '}
              <span className="font-semibold text-[var(--accent)]">{formatTokens(sessionTotalTokens)}</span>
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">当前 Session</p>
              <p className="text-sm font-mono text-[var(--text-primary)] truncate" title={appliedSessionKey}>
                {appliedSessionKey}
              </p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">Turn 数</p>
              <p className="text-xl font-bold text-cyan-400">{sessionTurnCount}</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">LLM 调用</p>
              <p className="text-xl font-bold text-purple-400">{sessionLlmCalls}</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">Session Token</p>
              <p className="text-xl font-bold text-[var(--accent)]">{formatTokens(sessionTotalTokens)}</p>
            </div>
          </div>
        )
      ) : (
        summary &&
        (isMobile ? (
          <div className="flex items-center gap-3 mb-3 px-1 text-xs overflow-x-auto">
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">Total:</span>{' '}
              <span className="font-semibold text-[var(--accent)]">{formatTokens(summary.totals.total_tokens)}</span>
            </span>
            <span className="text-[var(--border)]">|</span>
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">Calls:</span>{' '}
              <span className="font-semibold text-purple-400">{summary.totals.total_calls}</span>
            </span>
            <span className="text-[var(--border)]">|</span>
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">In:</span>{' '}
              <span className="font-semibold text-cyan-400">{formatTokens(summary.totals.prompt_tokens)}</span>
            </span>
            <span className="text-[var(--border)]">|</span>
            <span className="shrink-0">
              <span className="text-[var(--text-secondary)]">Out:</span>{' '}
              <span className="font-semibold text-emerald-400">{formatTokens(summary.totals.completion_tokens)}</span>
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">总 Token</p>
              <p className="text-xl font-bold text-[var(--accent)]">{formatTokens(summary.totals.total_tokens)}</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">LLM 调用</p>
              <p className="text-xl font-bold text-purple-400">{summary.totals.total_calls}</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">Prompt Tokens</p>
              <p className="text-xl font-bold text-cyan-400">{formatTokens(summary.totals.prompt_tokens)}</p>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">Completion Tokens</p>
              <p className="text-xl font-bold text-emerald-400">{formatTokens(summary.totals.completion_tokens)}</p>
            </div>
          </div>
        ))
      )}

      {view === 'turns' && isSessionMode && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-secondary)] mb-1">
              Session Debug Mode
            </div>
            <div className="font-mono text-sm text-[var(--text-primary)] truncate" title={appliedSessionKey}>
              {appliedSessionKey}
            </div>
            {appliedConversationScope !== null && (
              <div
                className="font-mono text-xs text-[var(--text-secondary)] mt-0.5 truncate"
                title={appliedConversationId || 'legacy'}
              >
                conversation: {appliedConversationId || 'legacy'}
              </div>
            )}
            <div className="flex flex-wrap gap-2 mt-2 text-xs text-[var(--text-secondary)]">
              <span className="px-2 py-1 rounded-full bg-[var(--bg-tertiary)]">{activeTurnLabel}</span>
              <span className="px-2 py-1 rounded-full bg-[var(--bg-tertiary)]">{sessionModels.size || 0} models</span>
              <span className="px-2 py-1 rounded-full bg-[var(--bg-tertiary)]">
                prompt {formatTokens(sessionPromptTokens)} / completion {formatTokens(sessionCompletionTokens)}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {appliedTurnSeq != null && (
              <button
                onClick={() => {
                  const nextParams = new URLSearchParams(searchParams);
                  nextParams.delete('turn_seq');
                  setSearchParams(nextParams, { replace: true });
                }}
                className="px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                查看全部 Turn
              </button>
            )}
            <button
              onClick={() => setView('records')}
              className="px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              查看调用明细
            </button>
            <button
              onClick={handleLeaveSessionMode}
              className="px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              返回全局
            </button>
          </div>
        </div>
      )}

      {/* Search / Filter Bar */}
      {view === 'records' && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 mb-4">
          {/* Primary filters: 功能角色 / 时间范围 / 模型 */}
          <div className="flex flex-wrap gap-1 items-end">
            <div>
              <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">功能角色</label>
              <div className="flex bg-[var(--bg-primary)] rounded-lg border border-[var(--border)] p-0.5">
                {MODEL_ROLE_FILTER_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setFilterModelRole(opt.value);
                      filtersRef.current = { ...filtersRef.current, filterModelRole: opt.value };
                      loadRecords(0);
                    }}
                    title={opt.label}
                    className={`px-1.5 py-1 rounded-md text-[10px] font-medium transition-colors flex items-center gap-0.5 ${
                      filterModelRole === opt.value
                        ? 'bg-[var(--accent)] text-white'
                        : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    <span>{opt.icon}</span>
                    {opt.value === 'all' && <span>全部</span>}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">时间范围</label>
              <div className="flex bg-[var(--bg-primary)] rounded-lg border border-[var(--border)] p-0.5">
                {(['all', 'today', '7d', '30d', 'custom'] as TimePreset[]).map(p => (
                  <button
                    key={p}
                    onClick={() => {
                      setTimePreset(p);
                      if (p !== 'custom') {
                        filtersRef.current = { ...filtersRef.current, timePreset: p };
                        loadRecords(0);
                      }
                    }}
                    className={`px-1 py-1 rounded-md text-[10px] font-medium transition-colors ${
                      timePreset === p
                        ? 'bg-[var(--accent)] text-white'
                        : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    {p === 'all'
                      ? '全部'
                      : p === 'today'
                        ? '今天'
                        : p === '7d'
                          ? '7天'
                          : p === '30d'
                            ? '30天'
                            : '自定义'}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 min-w-[100px]">
              <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">模型</label>
              <input
                type="text"
                value={filterModel}
                onChange={e => setFilterModel(e.target.value)}
                placeholder="claude-sonnet"
                className="w-full px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:border-[var(--accent)] outline-none"
              />
            </div>
            <div className="flex gap-1.5">
              <button
                onClick={handleSearch}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-xs font-medium hover:opacity-90"
              >
                <Search className="w-3 h-3" />
              </button>
              <button
                onClick={handleClearFilters}
                className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] text-xs hover:text-[var(--text-primary)] ${
                  hasFilters ? 'visible' : 'invisible'
                }`}
              >
                <X className="w-3 h-3" />
              </button>
              <button
                onClick={() => setFiltersExpanded(!filtersExpanded)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] text-xs hover:text-[var(--text-primary)]"
                title="更多筛选"
              >
                <SlidersHorizontal className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Extended filters (collapsible) */}
          {filtersExpanded && (
            <div className="flex flex-wrap gap-1 items-end mt-2 pt-2 border-t border-[var(--border)]">
              <div className="flex-1 min-w-[120px]">
                <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">Session ID</label>
                <input
                  type="text"
                  value={filterSessionKey}
                  onChange={e => setFilterSessionKey(e.target.value)}
                  placeholder="telegram:12345"
                  className="w-full px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:border-[var(--accent)] outline-none"
                />
              </div>
              <div className="flex-1 min-w-[80px]">
                <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">Provider</label>
                <input
                  type="text"
                  value={filterProvider}
                  onChange={e => setFilterProvider(e.target.value)}
                  placeholder="openai"
                  className="w-full px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:border-[var(--accent)] outline-none"
                />
              </div>
              <div className="w-[70px]">
                <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">Turn</label>
                <input
                  type="text"
                  value={filterTurnSeq}
                  onChange={e => setFilterTurnSeq(e.target.value)}
                  placeholder="0"
                  className="w-full px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:border-[var(--accent)] outline-none"
                />
              </div>
              <div className="flex-1 min-w-[160px]">
                <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">Trace ID</label>
                <input
                  type="text"
                  value={filterTraceId}
                  onChange={e => setFilterTraceId(e.target.value)}
                  placeholder="32 hex chars"
                  className="w-full px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:border-[var(--accent)] outline-none"
                />
              </div>
              <div className="flex-1 min-w-[140px]">
                <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">Span ID</label>
                <input
                  type="text"
                  value={filterSpanId}
                  onChange={e => setFilterSpanId(e.target.value)}
                  placeholder="16 hex chars"
                  className="w-full px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]/50 focus:border-[var(--accent)] outline-none"
                />
              </div>
              {timePreset === 'custom' && (
                <>
                  <div>
                    <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">开始日期</label>
                    <input
                      type="date"
                      value={customStart}
                      onChange={e => setCustomStart(e.target.value)}
                      className="px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] focus:border-[var(--accent)] outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-[var(--text-secondary)] mb-1 block">结束日期</label>
                    <input
                      type="date"
                      value={customEnd}
                      onChange={e => setCustomEnd(e.target.value)}
                      className="px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-xs text-[var(--text-primary)] focus:border-[var(--accent)] outline-none"
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {view === 'records' ? (
        /* ============ Records View ============ */
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm table-fixed">
              <colgroup>
                <col className="w-[120px]" />
                <col className="min-w-[160px]" />
                <col className="w-[60px]" />
                <col className="w-[100px]" />
                <col className="w-[85px]" />
                <col className="w-[90px]" />
                <col className="w-[120px]" />
                <col className="w-[100px]" />
                <col className="w-[80px]" />
                <col className="w-[85px]" />
                <col className="w-[50px]" />
              </colgroup>
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--text-secondary)] text-xs">
                  <th className="text-left px-4 py-3 font-medium">时间</th>
                  <th className="text-left px-4 py-3 font-medium">模型</th>
                  <th className="text-left px-4 py-3 font-medium">功能</th>
                  <th className="text-left px-4 py-3 font-medium">提供者</th>
                  <th className="text-right px-4 py-3 font-medium">Prompt</th>
                  <th className="text-right px-4 py-3 font-medium">Completion</th>
                  <th className="text-center px-4 py-3 font-medium">缓存</th>
                  <th className="text-center px-4 py-3 font-medium">调用</th>
                  <th className="text-right px-4 py-3 font-medium">Total</th>
                  <th className="text-right px-4 py-3 font-medium">Cost</th>
                  <th className="text-center px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={11} className="text-center py-8 text-[var(--text-secondary)]">
                      加载中...
                    </td>
                  </tr>
                ) : records.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="text-center py-8 text-[var(--text-secondary)]">
                      暂无数据
                    </td>
                  </tr>
                ) : (
                  records.map((r, i) => (
                    <RecordRow
                      key={`${r.timestamp}-${i}`}
                      record={r}
                      expanded={expandedRow === i}
                      onToggle={() => setExpandedRow(expandedRow === i ? null : i)}
                      onViewTrace={traceId => setSelectedTraceId(traceId)}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)]">
              <span className="text-xs text-[var(--text-secondary)]">
                共 {total} 条 · 第 {page + 1}/{totalPages} 页
              </span>
              <div className="flex items-center gap-1">
                <button
                  disabled={page === 0}
                  onClick={() => loadRecords(page - 1)}
                  className="px-2.5 py-1 rounded text-xs bg-[var(--bg-tertiary)] text-[var(--text-secondary)] disabled:opacity-30 hover:text-[var(--text-primary)]"
                >
                  &lsaquo;
                </button>
                <PageNumbers current={page} total={totalPages} onPage={loadRecords} />
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => loadRecords(page + 1)}
                  className="px-2.5 py-1 rounded text-xs bg-[var(--bg-tertiary)] text-[var(--text-secondary)] disabled:opacity-30 hover:text-[var(--text-primary)]"
                >
                  &rsaquo;
                </button>
              </div>
            </div>
          )}
        </div>
      ) : view === 'turns' ? (
        <TurnClusterList
          loading={loadingSessionTurns}
          sessionKey={appliedSessionKey}
          activeTurnKey={appliedTurnKey}
          activeTurnSeq={appliedTurnSeq}
          expandedTurnKey={expandedTurnKey}
          onToggleTurn={turnKey => {
            setExpandedTurnKey(prev => (prev === turnKey ? null : turnKey));
          }}
          turnSummaries={filteredTurnSummaries}
          turnIterationsByKey={turnIterationsByKey}
          turnKey={makeTurnKey}
	          chatTurnsByKey={sessionChatTurnsByKey}
	          turnRecordsByKey={turnRecordsByKey}
	          loadingTurnRecords={loadingTurnRecords}
	          onViewTrace={traceId => setSelectedTraceId(traceId)}
	        />
      ) : (
        /* ============ Charts View ============ */
        <div className="space-y-6">
          {/* By Model */}
          {summary && summary.by_model.length > 0 && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
              <h2 className="text-sm font-semibold mb-4">按模型统计</h2>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={summary.by_model.map(m => ({ ...m, label: shortModel(m.model) }))}
                    layout="vertical"
                    margin={{ left: 10 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis
                      type="number"
                      tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                      tickFormatter={formatTokens}
                    />
                    <YAxis
                      type="category"
                      dataKey="label"
                      width={140}
                      tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--bg-tertiary)',
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      labelStyle={{ color: 'var(--text-primary)' }}
                      formatter={fmtTooltip}
                    />
                    <Bar dataKey="prompt_tokens" name="Prompt" fill="#3b82f6" stackId="a" radius={[0, 0, 0, 0]} />
                    <Bar
                      dataKey="completion_tokens"
                      name="Completion"
                      fill="#8b5cf6"
                      stackId="a"
                      radius={[0, 4, 4, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* By Provider */}
            {summary && summary.by_provider.length > 0 && (
              <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
                <h2 className="text-sm font-semibold mb-4">按 Provider 统计</h2>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={summary.by_provider}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="provider" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                      <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={formatTokens} />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--bg-tertiary)',
                          border: '1px solid var(--border)',
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                        formatter={fmtTooltip}
                      />
                      <Bar dataKey="prompt_tokens" name="Prompt" fill="#06b6d4" />
                      <Bar dataKey="completion_tokens" name="Completion" fill="#10b981" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Pie Chart */}
            {summary && summary.totals.total_tokens > 0 && (
              <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
                <h2 className="text-sm font-semibold mb-4">Prompt / Completion 占比</h2>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={90}
                        dataKey="value"
                        label={({ name, percent }: { name?: string; percent?: number }) =>
                          `${name ?? ''} ${((percent ?? 0) * 100).toFixed(0)}%`
                        }
                      >
                        {pieData.map((_, idx) => (
                          <Cell key={idx} fill={PIE_COLORS[idx]} />
                        ))}
                      </Pie>
                      <Legend wrapperStyle={{ fontSize: 12, color: 'var(--text-secondary)' }} />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--bg-tertiary)',
                          border: '1px solid var(--border)',
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                        formatter={fmtTooltip}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>

          {/* Calls per model table */}
          {summary && summary.by_model.length > 0 && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--text-secondary)] text-xs">
                    <th className="text-left px-4 py-3 font-medium">模型</th>
                    <th className="text-right px-4 py-3 font-medium">调用次数</th>
                    <th className="text-right px-4 py-3 font-medium">Prompt</th>
                    <th className="text-right px-4 py-3 font-medium">Completion</th>
                    <th className="text-right px-4 py-3 font-medium">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_model.map(m => (
                    <tr key={m.model} className="border-b border-[var(--border)]/50 hover:bg-[var(--bg-tertiary)]/30">
                      <td className="px-4 py-2.5 font-mono text-xs">{m.model}</td>
                      <td className="px-4 py-2.5 text-right text-[var(--text-secondary)]">{m.calls}</td>
                      <td className="px-4 py-2.5 text-right">{formatTokens(m.prompt_tokens)}</td>
                      <td className="px-4 py-2.5 text-right">{formatTokens(m.completion_tokens)}</td>
                      <td className="px-4 py-2.5 text-right font-medium">{formatTokens(m.total_tokens)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      {selectedTraceId && (
        <TraceTimelineDrawer traceId={selectedTraceId} onClose={() => setSelectedTraceId(null)} />
      )}
    </div>
  );
}

function CopyablePre({ children, className }: { children: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const text = preRef.current?.textContent ?? children;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="relative group/copy">
      <pre ref={preRef} className={className}>
        {children}
      </pre>
      <button
        onClick={handleCopy}
        className="absolute bottom-2 right-2 p-1.5 rounded-md bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] opacity-0 group-hover/copy:opacity-100 transition-opacity"
        title="复制到剪贴板"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-[var(--success)]" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}

function ClaudeCodeMeta({ record }: { record: TokenRecord }) {
  const { user_message, cost_usd, prompt_tokens, completion_tokens, cached_tokens, cache_creation_tokens } = record;
  const parsed: Record<string, string> = {};
  const firstLine = user_message.split('\n')[0];
  const match = firstLine.match(/\[claude_code\]\s*(.*)/);
  if (match) {
    for (const part of match[1].split(/\s+/)) {
      const [k, v] = part.split('=');
      if (k && v) parsed[k] = v;
    }
  }

  const promptSection = user_message.match(/--- Prompt ---\n([\s\S]*)/);
  const promptText = promptSection ? promptSection[1].trim() : '';

  const nonCachedInput = prompt_tokens - (cached_tokens || 0) - (cache_creation_tokens || 0);

  return (
    <div className="space-y-2">
      {/* Meta bar */}
      <div className="flex flex-wrap gap-3 py-1.5 px-3 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
        <div className="flex items-center gap-1.5">
          <span className="text-base">💻</span>
          <span className="font-medium text-[var(--accent)]">Claude Code</span>
        </div>
        {parsed.session && (
          <div>
            <span className="text-[var(--text-secondary)]">Session: </span>
            <span className="font-mono text-[10px]">{parsed.session}</span>
          </div>
        )}
        {parsed.turns && (
          <div>
            <span className="text-[var(--text-secondary)]">Turns: </span>
            <span className="font-medium">{parsed.turns}</span>
          </div>
        )}
        {parsed.duration && (
          <div>
            <span className="text-[var(--text-secondary)]">Duration: </span>
            <span className="font-medium">{parsed.duration}</span>
          </div>
        )}
        {cost_usd > 0 && (
          <div>
            <span className="text-[var(--text-secondary)]">Cost: </span>
            <span className="font-medium text-amber-400">${cost_usd.toFixed(4)}</span>
          </div>
        )}
      </div>

      {/* Token breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
          <div className="text-[10px] text-[var(--text-secondary)]">Input (non-cached)</div>
          <div className="text-sm font-medium text-cyan-400">{formatTokens(Math.max(0, nonCachedInput))}</div>
        </div>
        <div className="px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
          <div className="text-[10px] text-[var(--text-secondary)]">Cache Read 🎯</div>
          <div className="text-sm font-medium text-emerald-400">{formatTokens(cached_tokens || 0)}</div>
        </div>
        <div className="px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
          <div className="text-[10px] text-[var(--text-secondary)]">Cache Write ✍️</div>
          <div className="text-sm font-medium text-amber-400">{formatTokens(cache_creation_tokens || 0)}</div>
        </div>
        <div className="px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
          <div className="text-[10px] text-[var(--text-secondary)]">Output</div>
          <div className="text-sm font-medium text-purple-400">{formatTokens(completion_tokens)}</div>
        </div>
      </div>

      {/* Prompt */}
      {promptText && (
        <div>
          <p className="text-[var(--text-secondary)] mb-1">Prompt:</p>
          <CopyablePre className="bg-[var(--bg-primary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
            {promptText}
          </CopyablePre>
        </div>
      )}
    </div>
  );
}

function RecordRow({
  record: r,
  expanded,
  onToggle,
  onViewTrace,
}: {
  record: TokenRecord;
  expanded: boolean;
  onToggle: () => void;
  onViewTrace: (traceId: string) => void;
}) {
  const callLabel = getCallLabel(r.tool_names, r.finish_reason);
  const callToneClass = getCallLabelTone(r.tool_names, r.finish_reason);

  return (
    <>
      <tr
        className="border-b border-[var(--border)]/50 hover:bg-[var(--bg-tertiary)]/30 cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-4 py-2.5 text-xs text-[var(--text-secondary)] whitespace-nowrap">
          {formatTime(r.timestamp)}
        </td>
        <td className="px-4 py-2.5 font-mono text-xs truncate" title={r.model}>
          {shortModel(r.model)}
        </td>
        <td className="px-4 py-2.5 text-center">
          <ModelRoleIcon role={r.model_role || 'default'} />
        </td>
        <td className="px-4 py-2.5 text-xs">{r.provider}</td>
        <td className="px-4 py-2.5 text-right text-cyan-400 text-xs">
          {r.model_role === 'pending' ? '—' : formatTokens(r.prompt_tokens)}
        </td>
        <td className="px-4 py-2.5 text-right text-emerald-400 text-xs">
          {r.model_role === 'pending' ? '—' : formatTokens(r.completion_tokens)}
        </td>
        <td className="px-4 py-2.5 text-center">
          {formatCacheStatus(r.cached_tokens || 0, r.cache_creation_tokens || 0)}
        </td>
        <td className="px-4 py-2.5">
          <div className="flex justify-center">
            <CallLabelBadge label={callLabel} toneClass={callToneClass} widthClass="w-[132px]" />
          </div>
          {/*
            <span
              className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
                r.finish_reason === 'end_turn' || r.finish_reason === 'stop'
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : 'bg-gray-500/15 text-gray-400'
              }`}
            >
              {r.finish_reason === 'end_turn' || r.finish_reason === 'stop' ? 'end' : r.finish_reason || '—'}
            </span>
          */}
        </td>
        <td className="px-4 py-2.5 text-right font-medium text-xs">{formatTokens(r.total_tokens)}</td>
        <td className="px-4 py-2.5 text-right text-xs">
          {r.cost_usd > 0 ? (
            <span className="text-amber-400 font-medium">${r.cost_usd.toFixed(4)}</span>
          ) : (
            <span className="text-[var(--text-secondary)]">—</span>
          )}
        </td>
        <td className="px-4 py-2.5 text-center">
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-[var(--text-secondary)]" />
          )}
        </td>
      </tr>
      {expanded && (
	        <tr className="bg-[var(--bg-tertiary)]/20 border-b border-[var(--border)]/50">
	          <td colSpan={11} className="px-4 py-3 overflow-hidden">
	            <div className="space-y-2 text-xs min-w-0">
	              {(r.conversation_id || r.trace_id || r.span_id || r.parent_span_id) && (
	                <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] p-3">
	                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
	                    <div className="space-y-1 min-w-0">
	                      <IdentityField value={r.conversation_id} label="Conversation ID" />
	                      <IdentityField value={r.trace_id} label="Trace ID" />
	                      <IdentityField value={r.span_id} label="Span ID" />
	                      <IdentityField value={r.parent_span_id} label="Parent Span ID" />
	                    </div>
	                    {r.trace_id && (
	                      <button
	                        type="button"
	                        onClick={e => {
	                          e.stopPropagation();
	                          onViewTrace(r.trace_id);
	                        }}
	                        className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white hover:opacity-90"
	                      >
	                        <BarChart3 className="h-3.5 w-3.5" />
	                        View Trace
	                      </button>
	                    )}
	                  </div>
	                </div>
	              )}
              <div>
                <span className="text-[var(--text-secondary)]">Session:</span>{' '}
                <span className="font-mono">{r.session_key || '—'}</span>
              </div>
              {r.model_role === 'claude_code' && <ClaudeCodeMeta record={r} />}
              {r.user_message && r.model_role !== 'claude_code' && (
                <div>
                  <p className="text-[var(--text-secondary)] mb-1">用户输入:</p>
                  <CopyablePre className="bg-[var(--bg-primary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                    {r.user_message}
                  </CopyablePre>
                </div>
              )}
              {r.output_content && (
                <div>
                  <p className="text-[var(--text-secondary)] mb-1">
                    {r.model_role === 'tool_call' ? '工具调用:' : '模型输出:'}
                  </p>
                  <CopyablePre className="bg-[var(--bg-primary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                    {r.output_content}
                  </CopyablePre>
                </div>
              )}
              <div>
                {r.system_prompt_preview && (
                  <>
                    <p className="text-[var(--text-secondary)] mb-1">系统提示词:</p>
                    <CopyablePre className="bg-[var(--bg-primary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-32 overflow-y-auto text-[var(--text-secondary)]">
                      {r.system_prompt_preview}
                    </CopyablePre>
                  </>
                )}
              </div>
              {r.conversation_history && (
                <div>
                  <p className="text-[var(--text-secondary)] mb-1">请求上下文（发送给模型前的快照）:</p>
                  <div className="bg-[var(--bg-primary)] rounded-lg p-3">
                    <ConversationHistoryView historyJson={r.conversation_history} />
                  </div>
                </div>
              )}
              {r.full_request_payload && r.full_request_payload.length > 0 && (
                <div>
                  <p className="text-[var(--text-secondary)] mb-1">完整 API 请求:</p>
                  <CopyablePre className="bg-[var(--bg-primary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-64 overflow-y-auto text-[var(--text-secondary)]">
                    {(() => {
                      try {
                        return JSON.stringify(JSON.parse(r.full_request_payload), null, 2);
                      } catch {
                        return r.full_request_payload;
                      }
                    })()}
                  </CopyablePre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function TurnClusterList({
  loading,
  sessionKey,
  activeTurnKey,
  activeTurnSeq,
  expandedTurnKey,
  onToggleTurn,
  turnSummaries,
  turnIterationsByKey,
  turnKey,
  chatTurnsByKey,
	  turnRecordsByKey,
	  loadingTurnRecords,
	  onViewTrace,
	}: {
	  loading: boolean;
	  sessionKey: string;
  activeTurnKey: string | null;
  activeTurnSeq: number | null;
  expandedTurnKey: string | null;
  onToggleTurn: (turnKey: string) => void;
  turnSummaries: TurnSummaryRecord[];
  turnIterationsByKey: Map<string, TurnIterationRecord[]>;
  turnKey: (convId: string, turnSeq: number) => string;
	  chatTurnsByKey: ChatTurnMap;
	  turnRecordsByKey: Record<string, TokenRecord[]>;
	  loadingTurnRecords: Record<string, boolean>;
	  onViewTrace: (traceId: string) => void;
	}) {
  if (loading) {
    return (
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-8 text-center text-[var(--text-secondary)]">
        加载 Turn 数据中...
      </div>
    );
  }

  if (turnSummaries.length === 0) {
    return (
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-8 text-center text-[var(--text-secondary)]">
        当前 Session 暂无可展示的 Turn 统计
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {turnSummaries.map(summary => {
        if (summary.turn_seq == null) return null;

        const turnSeq = summary.turn_seq;
        const currentTurnKey = turnKey(summary.conversation_id || '', turnSeq);
        const iterations = turnIterationsByKey.get(currentTurnKey) || [];
        const detailRecords = turnRecordsByKey[currentTurnKey] || [];
        const chatTurn = chatTurnsByKey[currentTurnKey];
        const expanded = expandedTurnKey === currentTurnKey;
        const highlighted = activeTurnKey ? activeTurnKey === currentTurnKey : activeTurnSeq === turnSeq;
        const status = getTurnStatus(detailRecords, iterations);
        const finalAssistantText = getTurnFinalAssistantText(chatTurn);
        const userMessage = getTurnUserMessage(chatTurn);

        return (
          <div
            key={currentTurnKey}
            id={turnDomId(currentTurnKey)}
            className={cn(
              'bg-[var(--bg-secondary)] border rounded-xl overflow-hidden transition-colors',
              highlighted ? 'border-[var(--accent)] shadow-[0_0_0_1px_var(--accent)]' : 'border-[var(--border)]',
            )}
          >
            <button
              onClick={() => onToggleTurn(currentTurnKey)}
              className="w-full px-4 py-4 text-left hover:bg-[var(--bg-tertiary)]/20 transition-colors"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">Turn #{turnSeq}</span>
                    {highlighted && (
                      <span className="inline-flex items-center rounded-full bg-[var(--accent)]/15 px-2 py-0.5 text-[10px] font-medium text-[var(--accent)]">
                        当前定位
                      </span>
                    )}
                    <span
                      className={cn(
                        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium',
                        status.className,
                      )}
                    >
                      {status.label}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-[var(--text-primary)] break-words">{getTurnUserPreview(chatTurn)}</p>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
                    {chatTurn?.startTime && (
                      <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5">
                        {formatTime(chatTurn.startTime)}
                      </span>
                    )}
                    <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5">
                      {summary.llm_calls} 次 LLM 调用
                    </span>
                    <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5">
                      {iterations.length || detailRecords.length} 条调用条目
                    </span>
                    {chatTurn && chatTurn.toolCalls.length > 0 && (
                      <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5">
                        {chatTurn.toolCalls.length} 个工具调用
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 lg:min-w-[250px]">
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2">
                    <div className="text-[10px] text-[var(--text-secondary)]">Total</div>
                    <div className="text-sm font-semibold text-[var(--accent)]">
                      {formatTokens(summary.total_tokens)}
                    </div>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2">
                    <div className="text-[10px] text-[var(--text-secondary)]">Models</div>
                    <div className="text-sm font-semibold text-[var(--text-primary)] truncate" title={summary.models}>
                      {summary.models || '—'}
                    </div>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2">
                    <div className="text-[10px] text-[var(--text-secondary)]">Prompt</div>
                    <div className="text-sm font-semibold text-cyan-400">{formatTokens(summary.prompt_tokens)}</div>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2">
                    <div className="text-[10px] text-[var(--text-secondary)]">Completion</div>
                    <div className="text-sm font-semibold text-emerald-400">
                      {formatTokens(summary.completion_tokens)}
                    </div>
                  </div>
                </div>
              </div>
	            </button>
	
	            {summary.trace_id && (
	              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border)] bg-[var(--bg-primary)]/40 px-4 py-2">
	                <IdentityField value={summary.trace_id} label="Trace ID" className="min-w-0" />
	                <button
	                  type="button"
	                  onClick={event => {
	                    event.stopPropagation();
	                    onViewTrace(summary.trace_id || '');
	                  }}
	                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-tertiary)] px-2.5 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--accent)]"
	                >
	                  <BarChart3 className="h-3.5 w-3.5" />
	                  View Trace
	                </button>
	              </div>
	            )}
	
	            {expanded && (
              <div className="border-t border-[var(--border)] bg-[var(--bg-tertiary)]/15 px-4 py-4 space-y-4">
	                {summary.conversation_id && <IdentityField value={summary.conversation_id} label="Conversation ID" />}
                <div className="text-[11px] text-[var(--text-secondary)]">
                  Session: <span className="font-mono text-[var(--text-primary)] break-all">{sessionKey}</span>
                </div>

                {userMessage && (
                  <div>
                    <p className="text-[var(--text-secondary)] mb-1 text-xs">用户输入</p>
                    <CopyablePre className="bg-[var(--bg-primary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                      {userMessage}
                    </CopyablePre>
                  </div>
                )}

                {finalAssistantText && (
                  <div>
                    <p className="text-[var(--text-secondary)] mb-1 text-xs">最终回复</p>
                    <CopyablePre className="bg-[var(--bg-primary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
                      {finalAssistantText}
                    </CopyablePre>
                  </div>
                )}

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-[var(--text-secondary)] text-xs">调用条目</p>
                    <span className="text-[10px] text-[var(--text-secondary)]">
                      {detailRecords.length || iterations.length} 条
                    </span>
                  </div>
                  {loadingTurnRecords[currentTurnKey] ? (
                    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-4 text-xs text-[var(--text-secondary)]">
                      加载调用详情中...
                    </div>
                  ) : detailRecords.length > 0 ? (
                    <div className="space-y-3">
                      {detailRecords.map((record, index) => (
                        <TurnCallEntry key={`${turnSeq}-${record.iteration}-${index}`} record={record} />
                      ))}
                    </div>
                  ) : iterations.length > 0 ? (
                    <div className="space-y-2">
                      {iterations.map(iteration => (
                        <TurnIterationFallback key={`${turnSeq}-${iteration.iteration}`} iteration={iteration} />
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-4 text-xs text-[var(--text-secondary)]">
                      暂无调用详情
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function TurnCallEntry({ record }: { record: TokenRecord }) {
  const [expanded, setExpanded] = useState(record.iteration === 0);
  const label =
    record.tool_names ||
    (record.finish_reason === 'end_turn' || record.finish_reason === 'stop' ? 'end' : record.finish_reason || '—');

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] overflow-hidden">
      <button
        onClick={() => setExpanded(prev => !prev)}
        className="w-full px-3 py-3 text-left hover:bg-[var(--bg-tertiary)]/20 transition-colors"
      >
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
              iteration {record.iteration}
            </span>
            <ModelRoleIcon role={record.model_role || 'default'} />
            <span className="font-mono text-xs text-[var(--text-primary)] truncate" title={record.model}>
              {shortModel(record.model)}
            </span>
            <CallLabelBadge
              label={record.tool_names ? getCallLabel(record.tool_names, record.finish_reason) : label}
              className="rounded-full px-2"
              toneClass={getCallLabelTone(record.tool_names, record.finish_reason)}
              widthClass="max-w-[200px]"
            />
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-[var(--text-secondary)] md:flex md:items-center md:gap-4">
            <span>Prompt {formatTokens(record.prompt_tokens)}</span>
            <span>Completion {formatTokens(record.completion_tokens)}</span>
            <span>Total {formatTokens(record.total_tokens)}</span>
            <span>{formatTime(record.timestamp)}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border)] px-3 py-3 space-y-3">
          <div className="flex flex-wrap gap-3 text-[11px] text-[var(--text-secondary)]">
            <span>{formatCacheStatus(record.cached_tokens || 0, record.cache_creation_tokens || 0)}</span>
            {record.cost_usd > 0 && <span className="text-amber-400">${record.cost_usd.toFixed(4)}</span>}
          </div>

          {record.output_content && (
            <div>
              <p className="text-[var(--text-secondary)] mb-1 text-xs">模型输出</p>
              <CopyablePre className="bg-[var(--bg-secondary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                {record.output_content}
              </CopyablePre>
            </div>
          )}

          <div>
            <p className="text-[var(--text-secondary)] mb-1 text-xs">系统提示词</p>
            {record.system_prompt_preview ? (
              <CopyablePre className="bg-[var(--bg-secondary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-32 overflow-y-auto text-[var(--text-secondary)]">
                {record.system_prompt_preview}
              </CopyablePre>
            ) : (
              <p className="text-xs text-[var(--text-tertiary)] italic">（与上一条相同，已省略）</p>
            )}
          </div>

          {record.conversation_history && (
            <div>
              <p className="text-[var(--text-secondary)] mb-1 text-xs">请求上下文（发送给模型前的快照）</p>
              <div className="bg-[var(--bg-secondary)] rounded-lg p-3">
                <ConversationHistoryView historyJson={record.conversation_history} />
              </div>
            </div>
          )}

          {record.full_request_payload && (
            <div>
              <p className="text-[var(--text-secondary)] mb-1 text-xs">完整 API 请求</p>
              <CopyablePre className="bg-[var(--bg-secondary)] rounded-lg p-3 text-xs whitespace-pre-wrap break-all max-h-64 overflow-y-auto text-[var(--text-secondary)]">
                {(() => {
                  try {
                    return JSON.stringify(JSON.parse(record.full_request_payload), null, 2);
                  } catch {
                    return record.full_request_payload;
                  }
                })()}
              </CopyablePre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TurnIterationFallback({ iteration }: { iteration: TurnIterationRecord }) {
  const label =
    iteration.tool_names ||
    (iteration.finish_reason === 'end_turn' || iteration.finish_reason === 'stop'
      ? 'end'
      : iteration.finish_reason || '—');

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
            iteration {iteration.iteration}
          </span>
          <ModelRoleIcon role={iteration.model_role || 'default'} />
          <span className="font-mono text-xs text-[var(--text-primary)]">{shortModel(iteration.model)}</span>
          <CallLabelBadge
            label={iteration.tool_names ? getCallLabel(iteration.tool_names, iteration.finish_reason) : label}
            className="rounded-full px-2"
            toneClass={getCallLabelTone(iteration.tool_names, iteration.finish_reason)}
            widthClass="max-w-[160px]"
          />
        </div>
        <div className="flex flex-wrap gap-3 text-[11px] text-[var(--text-secondary)]">
          <span>P {formatTokens(iteration.prompt_tokens)}</span>
          <span>C {formatTokens(iteration.completion_tokens)}</span>
          <span>Total {formatTokens(iteration.total_tokens)}</span>
        </div>
      </div>
    </div>
  );
}

function PageNumbers({ current, total, onPage }: { current: number; total: number; onPage: (p: number) => void }) {
  const pages: (number | '...')[] = [];
  const maxVisible = 7;

  if (total <= maxVisible) {
    for (let i = 0; i < total; i++) pages.push(i);
  } else {
    pages.push(0);
    if (current > 3) pages.push('...');
    const lo = Math.max(1, current - 1);
    const hi = Math.min(total - 2, current + 1);
    for (let i = lo; i <= hi; i++) pages.push(i);
    if (current < total - 4) pages.push('...');
    pages.push(total - 1);
  }

  return (
    <>
      {pages.map((p, i) =>
        p === '...' ? (
          <span key={`e${i}`} className="px-1 text-xs text-[var(--text-secondary)]">
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onPage(p)}
            className={cn(
              'min-w-[28px] px-1.5 py-1 rounded text-xs font-medium transition-colors',
              p === current
                ? 'bg-[var(--accent)] text-white'
                : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
            )}
          >
            {p + 1}
          </button>
        ),
      )}
    </>
  );
}
