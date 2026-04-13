import { useEffect, useState, useCallback } from 'react'
import { Save, RefreshCw, Timer, Heart } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import type { ConfigData, NanobotConfig, CronStore } from './ConfigPage/types'
import { CronJobsEditor } from './ConfigPage/CronJobsEditor'
import { HeartbeatEditor } from './ConfigPage/HeartbeatEditor'

type Tab = 'cron' | 'heartbeat'

export default function ScheduledTasksPage() {
  const [tab, setTab] = useState<Tab>('cron')
  const [cronStore, setCronStore] = useState<CronStore | null>(null)
  const [parsed, setParsed] = useState<NanobotConfig | null>(null)
  const [cronData, setCronData] = useState<ConfigData | null>(null)
  const [configData, setConfigData] = useState<ConfigData | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [dirty, setDirty] = useState(false)
  const { canEdit } = useAuth()
  const readOnly = !canEdit()

  const loadCron = useCallback(async () => {
    try {
      const d = await api<ConfigData>('/config/cron/jobs.json')
      setCronData(d)
      setCronStore(JSON.parse(d.content))
      setDirty(false)
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载定时任务失败' })
    }
  }, [])

  const loadConfig = useCallback(async () => {
    try {
      const d = await api<ConfigData>('/config/config.json')
      setConfigData(d)
      setParsed(JSON.parse(d.content))
      setDirty(false)
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载配置失败' })
    }
  }, [])

  useEffect(() => {
    loadCron()
    loadConfig()
  }, [loadCron, loadConfig])

  const handleReload = () => {
    if (tab === 'cron') loadCron()
    else loadConfig()
  }

  const updateCronStore = useCallback((store: CronStore) => {
    setCronStore(store)
    setDirty(true)
  }, [])

  const updateParsed = useCallback((updater: (prev: NanobotConfig) => NanobotConfig) => {
    setParsed(prev => {
      if (!prev) return prev
      const next = updater(prev)
      setDirty(true)
      return next
    })
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      if (tab === 'cron' && cronStore && cronData) {
        const content = JSON.stringify(cronStore, null, 2)
        const result = await api<{ mtime: number }>('/config/cron/jobs.json', {
          method: 'PUT',
          body: JSON.stringify({ content, mtime: cronData.mtime }),
        })
        setCronData({ ...cronData, content, mtime: result.mtime })
      } else if (tab === 'heartbeat' && parsed && configData) {
        const content = JSON.stringify(parsed, null, 2)
        const result = await api<{ mtime: number }>('/config/config.json', {
          method: 'PUT',
          body: JSON.stringify({ content, mtime: configData.mtime }),
        })
        setConfigData({ ...configData, content, mtime: result.mtime })
      }
      setDirty(false)
      setMessage({ type: 'success', text: '保存成功' })
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  const hasContent = tab === 'cron' ? !!cronStore : !!parsed

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">定时任务</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReload}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> 重载
          </button>
          {canEdit() && (
            <button
              onClick={handleSave}
              disabled={!dirty || saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors disabled:opacity-40"
            >
              <Save className="w-4 h-4" />
              {saving ? '保存中...' : '保存'}
            </button>
          )}
        </div>
      </div>

      {message && (
        <div
          className={`mb-3 p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}
        >
          {message.text}
        </div>
      )}

      <div className="flex gap-1 mb-3">
        <button
          onClick={() => setTab('cron')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
            tab === 'cron'
              ? 'bg-[var(--accent)] text-white'
              : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
        >
          <Timer className="w-3.5 h-3.5" /> 定时任务
        </button>
        <button
          onClick={() => setTab('heartbeat')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
            tab === 'heartbeat'
              ? 'bg-[var(--accent)] text-white'
              : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
        >
          <Heart className="w-3.5 h-3.5" /> 心跳任务
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pb-8">
        {!hasContent ? (
          <div className="text-center py-20 text-[var(--text-secondary)]">加载中...</div>
        ) : tab === 'cron' && cronStore ? (
          <CronJobsEditor store={cronStore} readOnly={readOnly} onChange={updateCronStore} />
        ) : tab === 'heartbeat' && parsed ? (
          <HeartbeatEditor
            heartbeatConfig={parsed.agents?.defaults?.heartbeat}
            readOnly={readOnly}
            onConfigChange={heartbeat => updateParsed(p => ({
              ...p,
              agents: { ...p.agents, defaults: { ...p.agents.defaults, heartbeat } },
            }))}
          />
        ) : null}
      </div>
    </div>
  )
}
