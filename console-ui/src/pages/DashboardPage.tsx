import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowUpCircle,
  BarChart3,
  Brain,
  ChevronRight,
  Clock,
  Cpu,
  Hammer,
  Image,
  Loader2,
  MessageSquare,
  Power,
  RefreshCw,
  Server,
  Settings,
  Shield,
  Timer,
  UserCog,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useResponsiveMode } from '../hooks/useResponsiveMode'
import { useVersionCheck } from '../hooks/useVersionCheck'
import { useAuth } from '../stores/auth'

interface GatewayStatusData {
  running: boolean
  pid: number | null
  uptime_seconds: number | null
  gateway_port: number | null
  console_port: number | null
  supervised: boolean
  supervisor: string | null
  restart_pending: boolean
  boot_generation: number
  last_exit_reason: string | null
}

interface ActiveTask {
  task_id: string
  task_type: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  prompt_preview: string
  started_at: number | null
  elapsed_ms: number
}

interface ActiveTasksResponse {
  running: number
  total: number
  tasks: ActiveTask[]
}

interface QuickCard {
  icon: typeof Settings
  label: string
  value: string
  sub: string
  color: string
  onClick: () => void
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return 'N/A'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const parts: string[] = []
  if (days > 0) parts.push(`${days}d`)
  if (hours > 0) parts.push(`${hours}h`)
  parts.push(`${minutes}m`)
  return parts.join(' ')
}

function shortUptime(seconds: number | null): string {
  if (seconds == null) return 'N/A'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`
}

export default function DashboardPage() {
  const [status, setStatus] = useState<GatewayStatusData | null>(null)
  const [restarting, setRestarting] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [gwMessage, setGwMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [activeTasks, setActiveTasks] = useState<ActiveTasksResponse | null>(null)
  const navigate = useNavigate()
  const { isMobile } = useResponsiveMode()
  const { currentVersion, updateAvailable, dismiss, refresh } = useVersionCheck()
  const { user, isAdmin, isMockTester } = useAuth()
  const mockMode = isMockTester()

  const loadStatus = useCallback(() => {
    api<GatewayStatusData>('/gateway/status').then(setStatus).catch(() => {})
  }, [])

  const loadActiveTasks = useCallback(() => {
    if (mockMode) {
      setActiveTasks(null)
      return
    }
    api<ActiveTasksResponse>('/bg-tasks?include_finished=false')
      .then(setActiveTasks)
      .catch(() => {})
  }, [mockMode])

  useEffect(() => {
    loadStatus()
    loadActiveTasks()
    const statusTimer = window.setInterval(loadStatus, 10000)
    const taskTimer = mockMode ? null : window.setInterval(loadActiveTasks, 3000)
    return () => {
      window.clearInterval(statusTimer)
      if (taskTimer != null) window.clearInterval(taskTimer)
    }
  }, [loadActiveTasks, loadStatus, mockMode])

  useEffect(() => {
    if (!activeTasks || activeTasks.running <= 0) return
    const timer = window.setInterval(() => setActiveTasks(data => (data ? { ...data } : data)), 1000)
    return () => window.clearInterval(timer)
  }, [activeTasks])

  useEffect(() => {
    if (countdown <= 0) return
    const timer = window.setTimeout(() => setCountdown(countdown - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [countdown])

  const handleRestart = async (force = false) => {
    if (!window.confirm(`重启网关${force ? '（强制）' : ''}？`)) return
    setRestarting(true)
    setGwMessage(null)
    try {
      const delayMs = 5000
      await api('/gateway/restart', {
        method: 'POST',
        body: JSON.stringify({ delay_ms: delayMs, force }),
      })
      setCountdown(Math.ceil(delayMs / 1000) + 5)
      setGwMessage({ type: 'success', text: `网关重启已调度，${delayMs / 1000}s 后执行。` })
    } catch (err: unknown) {
      setGwMessage({ type: 'error', text: err instanceof Error ? err.message : '重启失败' })
    } finally {
      setRestarting(false)
    }
  }

  const handleRebuild = async () => {
    if (!window.confirm('立即重新构建控制台界面？')) return
    setRebuilding(true)
    setGwMessage(null)
    try {
      const res = await api<{ success: boolean; duration_ms: number; error: string }>('/gateway/console/rebuild', {
        method: 'POST',
      })
      if (res.success) {
        setGwMessage({ type: 'success', text: `界面重新构建完成，耗时 ${res.duration_ms}ms。` })
      } else {
        setGwMessage({ type: 'error', text: `重新构建失败：${res.error}` })
      }
    } catch (err: unknown) {
      setGwMessage({ type: 'error', text: err instanceof Error ? err.message : '重新构建失败' })
    } finally {
      setRebuilding(false)
    }
  }

  const cards: QuickCard[] = mockMode
    ? [
        {
          icon: Settings,
          label: '配置',
          value: 'Mock Config',
          sub: '仅编辑模拟配置文件',
          color: 'text-[var(--accent)]',
          onClick: () => navigate('/config'),
        },
        {
          icon: Timer,
          label: '定时任务',
          value: 'Mock Cron',
          sub: '定时任务在模拟数据目录下',
          color: 'text-cyan-400',
          onClick: () => navigate('/tasks'),
        },
        {
          icon: Cpu,
          label: '后台任务',
          value: 'Mock Tasks',
          sub: '查看空/模拟安全的任务状态',
          color: 'text-blue-400',
          onClick: () => navigate('/bg-tasks'),
        },
        {
          icon: Brain,
          label: '记忆',
          value: 'Mock Memory',
          sub: '预览人设和记忆文档',
          color: 'text-amber-400',
          onClick: () => navigate('/memory'),
        },
        {
          icon: Image,
          label: '生成图片',
          value: 'Mock Media',
          sub: '图片库限定在模拟数据目录内',
          color: 'text-emerald-400',
          onClick: () => navigate('/media'),
        },
        {
          icon: UserCog,
          label: '人设',
          value: 'Mock Persona',
          sub: '在沙盒中编辑工作区身份文件',
          color: 'text-violet-400',
          onClick: () => navigate('/persona'),
        },
        {
          icon: Hammer,
          label: '技能和工具',
          value: 'Mock Skills',
          sub: '查看工具注册表和模拟 TOOLS.md',
          color: 'text-fuchsia-400',
          onClick: () => navigate('/skills'),
        },
        {
          icon: MessageSquare,
          label: '聊天',
          value: 'Mock Chat',
          sub: '安全浏览预置的模拟对话',
          color: 'text-pink-400',
          onClick: () => navigate('/chat'),
        },
        {
          icon: BarChart3,
          label: 'Token 统计',
          value: 'Mock Stats',
          sub: 'Token 图表来自模拟数据库',
          color: 'text-sky-400',
          onClick: () => navigate('/tokens'),
        },
      ]
    : [
        {
          icon: Settings,
          label: '配置',
          value: '配置',
          sub: '编辑网关和控制台配置',
          color: 'text-[var(--accent)]',
          onClick: () => navigate('/config'),
        },
        {
          icon: Brain,
          label: '记忆',
          value: '记忆',
          sub: '浏览全局和个人记忆文件',
          color: 'text-amber-400',
          onClick: () => navigate('/memory'),
        },
        {
          icon: UserCog,
          label: '人设',
          value: '人设',
          sub: '查看核心 Agent 身份文件',
          color: 'text-emerald-400',
          onClick: () => navigate('/persona'),
        },
        {
          icon: MessageSquare,
          label: '聊天',
          value: '聊天',
          sub: '打开实时 Agent 会话和调试流程',
          color: 'text-fuchsia-400',
          onClick: () => navigate('/chat'),
        },
      ]

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">控制台</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">当前登录用户：{user?.username}</p>
      </div>

      {mockMode && (
        <div className="mb-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4">
          <div className="flex items-start gap-3">
            <Shield className="mt-0.5 h-5 w-5 text-amber-400" />
            <div>
              <p className="text-sm font-semibold text-amber-300">模拟沙盒</p>
              <p className="mt-1 text-sm text-amber-100/80">
                当前账号只能读取和编辑 `~/.nanobot/console/mock_data/`。真实 workspace、真实 `~/.nanobot`、live agent
                执行与 gateway 控制都不会暴露给这个账号；聊天与后台任务页面也只展示 mock-safe 数据或空态。
              </p>
            </div>
          </div>
        </div>
      )}

      {updateAvailable && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/10 p-3">
          <div className="flex items-center gap-2">
            <ArrowUpCircle className="h-4 w-4 text-[var(--accent)]" />
            <span className="text-sm font-medium text-[var(--accent)]">检测到新的 console-ui 构建版本</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="rounded-lg bg-[var(--accent)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--accent)]/80"
            >
              刷新加载
            </button>
            <button
              onClick={dismiss}
              className="rounded-lg px-2 py-1 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              忽略
            </button>
          </div>
        </div>
      )}

      {gwMessage && (
        <div
          className={`mb-4 rounded-lg p-3 text-sm ${
            gwMessage.type === 'success'
              ? 'bg-[var(--success)]/10 text-[var(--success)]'
              : 'bg-[var(--danger)]/10 text-[var(--danger)]'
          }`}
        >
          {gwMessage.text}
        </div>
      )}

      {countdown > 0 && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-[var(--warning)]/20 bg-[var(--warning)]/10 p-4">
          <AlertTriangle className="h-5 w-5 text-[var(--warning)]" />
          <div>
            <p className="text-sm font-medium text-[var(--warning)]">网关重启等待中</p>
            <p className="text-xs text-[var(--text-secondary)]">预计约 {countdown}s 后重新连接。</p>
          </div>
        </div>
      )}

      {isMobile ? (
        <div className="mb-4 grid grid-cols-2 gap-3">
          {cards.map(card => (
            <button
              key={card.label}
              onClick={card.onClick}
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-4 text-left transition-all hover:border-[var(--accent)]/50"
            >
              <div className={`mb-3 inline-flex rounded-lg bg-[var(--bg-tertiary)] p-2 ${card.color}`}>
                <card.icon className="h-4 w-4" />
              </div>
              <p className="text-sm font-semibold">{card.value}</p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">{card.sub}</p>
            </button>
          ))}
        </div>
      ) : (
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {cards.map(card => (
            <button
              key={card.label}
              onClick={card.onClick}
              className="group rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-5 text-left transition-all hover:border-[var(--accent)]/50"
            >
              <div className="mb-3 flex items-center gap-3">
                <div className={`rounded-lg bg-[var(--bg-tertiary)] p-2 ${card.color}`}>
                  <card.icon className="h-5 w-5" />
                </div>
                <span className="text-sm text-[var(--text-secondary)]">{card.label}</span>
              </div>
              <p className={`text-xl font-semibold ${card.color}`}>{card.value}</p>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">{card.sub}</p>
            </button>
          ))}
        </div>
      )}

      <div
        className={`mb-6 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] ${isMobile ? 'p-4' : 'p-5'}`}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className={`rounded-lg p-2 ${status?.running ? 'bg-[var(--success)]/10' : 'bg-[var(--danger)]/10'}`}>
              <Server className={`h-5 w-5 ${status?.running ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`} />
            </div>
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                {status?.running ? '网关在线' : '网关离线'}
                <button
                  onClick={loadStatus}
                  className="rounded p-1 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                  title="刷新状态"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              </h2>
              <p className="text-[10px] text-[var(--text-secondary)]">
                {status?.running
                  ? `PID ${status.pid ?? '-'} · 运行 ${shortUptime(status.uptime_seconds)} · 端口 ${status.gateway_port ?? '-'}`
                  : '未检测到运行中的网关'}
              </p>
            </div>
          </div>

          {isAdmin() && !mockMode && (
            <div className="flex gap-1.5">
              <button
                onClick={handleRebuild}
                disabled={rebuilding}
                className="flex items-center gap-1 rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-[11px] font-medium text-white disabled:opacity-50 hover:bg-[var(--accent)]/80"
              >
                {rebuilding ? <Loader2 className="h-3 w-3 animate-spin" /> : <Hammer className="h-3 w-3" />}
                {isMobile ? '' : rebuilding ? '构建中...' : '重新构建'}
              </button>
              <button
                onClick={() => handleRestart(false)}
                disabled={restarting}
                className="flex items-center gap-1 rounded-lg bg-[var(--warning)] px-2.5 py-1.5 text-[11px] font-medium text-black disabled:opacity-50 hover:bg-[var(--warning)]/80"
              >
                <RefreshCw className="h-3 w-3" />
                {isMobile ? '' : restarting ? '调度中...' : '重启'}
              </button>
              <button
                onClick={() => handleRestart(true)}
                disabled={restarting}
                className="flex items-center gap-1 rounded-lg bg-[var(--danger)] px-2.5 py-1.5 text-[11px] font-medium text-white disabled:opacity-50 hover:bg-[var(--danger)]/80"
              >
                <Power className="h-3 w-3" />
                {isMobile ? '' : '强制'}
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-lg bg-[var(--bg-primary)] p-3">
            <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">状态</p>
            <p
              className={`text-sm font-semibold ${status?.running ? 'text-[var(--success)]' : 'text-[var(--danger)]'}`}
            >
              {status?.running ? '在线' : '离线'}
            </p>
          </div>
          <div className="rounded-lg bg-[var(--bg-primary)] p-3">
            <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">网关端口</p>
            <p className="text-sm font-semibold">{status?.gateway_port ?? '-'}</p>
          </div>
          <div className="rounded-lg bg-[var(--bg-primary)] p-3">
            <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">控制台端口</p>
            <p className="text-sm font-semibold">{status?.console_port ?? '-'}</p>
          </div>
          <div className="rounded-lg bg-[var(--bg-primary)] p-3">
            <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">运行时长</p>
            <p className="text-sm font-semibold">{formatUptime(status?.uptime_seconds ?? null)}</p>
          </div>
        </div>

        {status && (
          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-lg bg-[var(--bg-primary)] p-3">
              <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">监管进程</p>
              <p className="flex items-center gap-1 text-sm font-semibold">
                <Shield
                  className={`h-3 w-3 ${status.supervised ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}`}
                />
                {status.supervised ? (status.supervisor ?? '已启用') : '无'}
              </p>
            </div>
            <div className="rounded-lg bg-[var(--bg-primary)] p-3">
              <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">启动代数</p>
              <p className="text-sm font-semibold">#{status.boot_generation}</p>
            </div>
            <div className="rounded-lg bg-[var(--bg-primary)] p-3">
              <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">界面版本</p>
              <p className="font-mono text-sm font-semibold">{currentVersion?.hash?.slice(0, 8) ?? '-'}</p>
            </div>
            <div className="rounded-lg bg-[var(--bg-primary)] p-3">
              <p className="mb-0.5 text-[10px] text-[var(--text-secondary)]">重启状态</p>
              <p
                className={`text-sm font-semibold ${status.restart_pending ? 'text-[var(--warning)]' : 'text-[var(--text-secondary)]'}`}
              >
                {status.restart_pending ? '等待重启' : '稳定'}
              </p>
            </div>
          </div>
        )}
      </div>

      {!mockMode && activeTasks && activeTasks.running > 0 && (
        <div className="mb-6 rounded-xl border border-blue-500/30 bg-[var(--bg-secondary)] p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="rounded-lg bg-blue-500/10 p-2">
                <Cpu className="h-4 w-4 text-blue-400" />
              </div>
              <h2 className="text-sm font-semibold">后台任务</h2>
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-400">
                <Loader2 className="h-3 w-3 animate-spin" />
                {activeTasks.running} 运行中
              </span>
            </div>
            <button
              onClick={() => navigate('/bg-tasks')}
              className="flex items-center gap-1 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              查看全部 <ChevronRight className="h-3 w-3" />
            </button>
          </div>

          <div className="space-y-2">
            {activeTasks.tasks
              .filter(task => task.status === 'queued' || task.status === 'running')
              .slice(0, 3)
              .map(task => {
                const elapsed = task.started_at ? Math.floor(Date.now() / 1000 - task.started_at) : 0;
                const elapsedText = elapsed >= 60 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` : `${elapsed}s`;
                const StatusIcon = task.status === 'running' ? Loader2 : Clock;
                return (
                  <button
                    key={task.task_id}
                    onClick={() => navigate('/bg-tasks')}
                    className="flex w-full items-center gap-3 rounded-lg bg-[var(--bg-primary)] p-3 text-left transition-colors hover:bg-[var(--bg-tertiary)]"
                  >
                    <StatusIcon
                      className={`h-4 w-4 ${task.status === 'running' ? 'animate-spin text-blue-400' : 'text-yellow-500'}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{task.prompt_preview || '(no prompt)'}</p>
                      <p className="text-xs text-[var(--text-secondary)]">
                        {task.task_type} · {task.task_id} · {elapsedText}
                      </p>
                    </div>
                  </button>
                );
              })}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-5">
        <div className="mb-3 flex items-center gap-2">
          <Activity className="h-4 w-4 text-[var(--accent)]" />
          <h2 className="text-sm font-semibold">快捷信息</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
          <div>
            <p className="text-[var(--text-secondary)]">角色</p>
            <p className="font-medium capitalize">{user?.role}</p>
          </div>
          <div>
            <p className="text-[var(--text-secondary)]">模式</p>
            <p className="font-medium">{mockMode ? '模拟沙盒' : '实时运行'}</p>
          </div>
          <div>
            <p className="text-[var(--text-secondary)]">网关</p>
            <p className="font-medium">{status?.gateway_port ?? 'N/A'}</p>
          </div>
          <div>
            <p className="text-[var(--text-secondary)]">控制台</p>
            <p className="font-medium">{status?.console_port ?? 'N/A'}</p>
          </div>
        </div>
      </div>

      <p className="mt-4 text-right font-mono text-[10px] text-[var(--text-secondary)] opacity-60">
        {new Date(__BUILD_TIME__).toLocaleString('zh-CN', {
          timeZone: 'Asia/Shanghai',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })}
      </p>
    </div>
  );
}
