import { useEffect, useState, useCallback, useRef } from 'react'
import Editor from '@monaco-editor/react'
import {
  Wrench, Puzzle, Plus, RefreshCw, Save, GitBranch, FolderOpen, Trash2, X,
  Package, Pencil, Upload, Bot, ExternalLink, Server, ShieldCheck, AlertTriangle,
} from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { cn } from '../lib/utils'

// ── Types ──────────────────────────────────────────────────────────────────

interface ToolInfo {
  name: string
  class: string
  description: string
  file: string
}

interface SkillInfo {
  name: string
  source: 'ava' | 'agents' | 'builtin'
  path: string
  enabled: boolean
  description: string
  always: boolean
  install_method?: string | null
  git_url?: string | null
}

interface FileData {
  path: string
  content: string
  mtime: number
}

interface MCPConfigSummary {
  type?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
  toolTimeout?: number
  enabledTools?: string[]
}

interface MCPServerStatus {
  name: string
  status: 'connected' | 'connecting' | 'configured' | 'failed' | 'unloaded' | string
  config_redacted: MCPConfigSummary
  redacted: string[]
  registered_tools: string[]
  last_error: string | null
  last_connected_at: string | null
}

interface MCPStatusResponse {
  servers: MCPServerStatus[]
  runtime: {
    loaded: boolean
    mcp_connected: boolean
    mcp_connecting: boolean
    connected_servers: string[]
  }
}

interface MCPProbeResult {
  ok: boolean
  name: string
  status: string
  raw_tools: string[]
  wrapped_tools: string[]
  error: string | null
}

// ── Toggle Switch ─────────────────────────────────────────────────────────

function ToggleSwitch({ enabled, onToggle, disabled }: { enabled: boolean; onToggle: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      title={enabled ? '点击禁用' : '点击启用'}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
        enabled ? 'bg-[var(--success)]' : 'bg-[var(--bg-tertiary)]',
        disabled && 'opacity-40 cursor-not-allowed',
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform',
          enabled ? 'translate-x-[18px]' : 'translate-x-[3px]',
        )}
      />
    </button>
  )
}

// ── Tools Section ──────────────────────────────────────────────────────────

function ToolsSection() {
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [toolsDoc, setToolsDoc] = useState<FileData | null>(null)
  const [docEdit, setDocEdit] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const { canEdit } = useAuth()

  const loadTools = useCallback(async () => {
    try {
      const [toolsRes, docRes] = await Promise.all([
        api<{ tools: ToolInfo[] }>('/skills/tools'),
        api<FileData>('/files/read?path=workspace/TOOLS.md').catch(() => null),
      ])
      setTools(toolsRes.tools)
      setToolsDoc(docRes)
      setDocEdit(docRes?.content || '')
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载失败' })
    }
  }, [])

  useEffect(() => { loadTools() }, [loadTools])

  const saveDoc = async () => {
    if (!toolsDoc) return
    setSaving(true)
    setMessage(null)
    try {
      const result = await api<FileData>('/files/write', {
        method: 'PUT',
        body: JSON.stringify({ path: toolsDoc.path, content: docEdit, expected_mtime: toolsDoc.mtime }),
      })
      setToolsDoc({ ...toolsDoc, content: docEdit, mtime: result.mtime })
      setMessage({ type: 'success', text: 'TOOLS.md 保存成功' })
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  const docChanged = docEdit !== toolsDoc?.content

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Wrench className="w-5 h-5 text-[var(--accent)]" />
          内置工具
          <span className="text-sm text-[var(--text-secondary)] font-normal">({tools.length} 个)</span>
        </h2>
        <button
          onClick={loadTools}
          title="刷新"
          className="p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {message && (
        <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}>
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {tools.map(tool => (
          <div
            key={tool.name}
            className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 hover:border-[var(--accent)]/50 transition-all"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
                  <Wrench className="w-4 h-4" />
                </div>
                <span className="font-mono text-sm font-medium">{tool.name}</span>
              </div>
            </div>
            <p className="text-xs text-[var(--text-secondary)] mt-2 line-clamp-2">{tool.description}</p>
            <p className="text-[10px] text-[var(--text-secondary)]/60 mt-2 font-mono">{tool.file}</p>
          </div>
        ))}
      </div>

      {/* TOOLS.md Editor */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <Pencil className="w-4 h-4 text-[var(--warning)]" />
            <span className="text-sm font-semibold">TOOLS.md</span>
            <span className="text-xs text-[var(--text-secondary)]">工具文档</span>
          </div>
          {canEdit() && toolsDoc && (
            <button
              onClick={saveDoc}
              disabled={!docChanged || saving}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-xs font-medium disabled:opacity-40"
            >
              <Save className="w-3.5 h-3.5" /> {saving ? '保存中...' : '保存'}
            </button>
          )}
        </div>
        <div className="h-64">
          {toolsDoc ? (
            <Editor
              height="100%"
              language="markdown"
              theme="vs-dark"
              value={docEdit}
              onChange={(v) => setDocEdit(v || '')}
              options={{ minimap: { enabled: false }, fontSize: 13, readOnly: !canEdit(), wordWrap: 'on', scrollBeyondLastLine: false }}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-[var(--text-secondary)]">
              TOOLS.md 文件不存在
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── MCP Section ────────────────────────────────────────────────────────────

function statusClass(status: string): string {
  if (status === 'connected') return 'bg-[var(--success)]/10 text-[var(--success)]'
  if (status === 'connecting' || status === 'configured') return 'bg-[var(--warning)]/10 text-[var(--warning)]'
  return 'bg-[var(--danger)]/10 text-[var(--danger)]'
}

function recordKeys(record?: Record<string, string>): string[] {
  return Object.keys(record || {})
}

function MCPSection() {
  const [status, setStatus] = useState<MCPStatusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [reconnecting, setReconnecting] = useState(false)
  const [probeResults, setProbeResults] = useState<Record<string, MCPProbeResult>>({})
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const { canEdit, isAdmin, isMockTester } = useAuth()
  const canProbe = canEdit() && !isMockTester()

  const loadStatus = useCallback(async () => {
    setLoading(true)
    setMessage(null)
    try {
      const res = await api<MCPStatusResponse>('/skills/mcp/status')
      setStatus(res)
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载失败' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadStatus() }, [loadStatus])

  const testConnection = async (name: string) => {
    setTesting(name)
    setMessage(null)
    try {
      const result = await api<MCPProbeResult>('/skills/mcp/test', {
        method: 'POST',
        body: JSON.stringify({ name }),
      })
      setProbeResults(prev => ({ ...prev, [name]: result }))
      setMessage({
        type: result.ok ? 'success' : 'error',
        text: result.ok ? `${name} probe connected` : result.error || `${name} probe failed`,
      })
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '测试失败' })
    } finally {
      setTesting(null)
    }
  }

  const reconnectAll = async () => {
    setReconnecting(true)
    setMessage(null)
    try {
      await api('/skills/mcp/reconnect', {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setMessage({ type: 'success', text: 'MCP 已触发全量重连' })
      loadStatus()
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '重连不可用，请重启 gateway' })
    } finally {
      setReconnecting(false)
    }
  }

  const servers = status?.servers ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Server className="w-5 h-5 text-cyan-400" />
          MCP servers
          <span className="text-sm text-[var(--text-secondary)] font-normal">({servers.length} 个)</span>
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={loadStatus}
            disabled={loading}
            title="刷新状态"
            className="p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-40"
          >
            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
          </button>
          {isAdmin() && (
            <button
              onClick={reconnectAll}
              disabled={reconnecting}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] hover:bg-[var(--bg-tertiary)]/80 text-sm font-medium disabled:opacity-40"
            >
              <RefreshCw className={cn('w-4 h-4', reconnecting && 'animate-spin')} /> 全量重连
            </button>
          )}
        </div>
      </div>

      {message && (
        <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}>
          {message.text}
        </div>
      )}

      {servers.length === 0 ? (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 text-sm text-[var(--text-secondary)]">
          未配置 MCP server
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {servers.map(server => {
            const cfg = server.config_redacted || {}
            const envKeys = recordKeys(cfg.env)
            const headerKeys = recordKeys(cfg.headers)
            const probe = probeResults[server.name]

            return (
              <div key={server.name} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium truncate">{server.name}</span>
                      <span className={cn('text-[10px] px-1.5 py-0.5 rounded', statusClass(server.status))}>
                        {server.status}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-secondary)]">
                      {server.registered_tools.length} registered / {cfg.enabledTools?.length ?? 0} enabled
                    </p>
                  </div>
                  {canProbe && (
                    <button
                      onClick={() => testConnection(server.name)}
                      disabled={testing === server.name}
                      className="shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[var(--accent)]/10 text-[var(--accent)] hover:bg-[var(--accent)]/15 text-xs font-medium disabled:opacity-40"
                    >
                      <ShieldCheck className="w-3.5 h-3.5" /> {testing === server.name ? '测试中...' : 'Test'}
                    </button>
                  )}
                </div>

                <div className="mt-3 space-y-2 text-xs">
                  {cfg.command && (
                    <div>
                      <span className="text-[var(--text-secondary)]">command</span>
                      <p className="font-mono break-all mt-0.5">{[cfg.command, ...(cfg.args || [])].join(' ')}</p>
                    </div>
                  )}
                  {cfg.url && (
                    <div>
                      <span className="text-[var(--text-secondary)]">url</span>
                      <p className="font-mono break-all mt-0.5">{cfg.url}</p>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2 text-[var(--text-secondary)]">
                    <span>timeout={cfg.toolTimeout ?? 30}s</span>
                    {server.redacted.length > 0 && <span>redacted={server.redacted.join(',')}</span>}
                    {status?.runtime.loaded ? null : <span>runtime=unloaded</span>}
                  </div>
                  {(cfg.enabledTools || []).length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {cfg.enabledTools!.map(tool => (
                        <span key={tool} className="px-1.5 py-0.5 rounded bg-[var(--bg-primary)] border border-[var(--border)] font-mono">
                          {tool}
                        </span>
                      ))}
                    </div>
                  )}
                  {(envKeys.length > 0 || headerKeys.length > 0) && (
                    <div className="flex flex-wrap gap-1.5 text-[var(--text-secondary)]">
                      {envKeys.map(key => <span key={`env:${key}`} className="px-1.5 py-0.5 rounded bg-[var(--bg-primary)] border border-[var(--border)]">env.{key}=****</span>)}
                      {headerKeys.map(key => <span key={`header:${key}`} className="px-1.5 py-0.5 rounded bg-[var(--bg-primary)] border border-[var(--border)]">headers.{key}=****</span>)}
                    </div>
                  )}
                  {server.registered_tools.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {server.registered_tools.map(tool => (
                        <span key={tool} className="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 font-mono">
                          {tool}
                        </span>
                      ))}
                    </div>
                  )}
                  {server.last_error && (
                    <div className="flex items-start gap-1.5 text-[var(--danger)]">
                      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                      <span>{server.last_error}</span>
                    </div>
                  )}
                  {probe && (
                    <div className={cn('rounded-lg px-2.5 py-2', probe.ok ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]')}>
                      {probe.ok ? `probe tools: ${probe.wrapped_tools.join(', ') || '(none)'}` : probe.error}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Skills Section ─────────────────────────────────────────────────────────

function SkillsSection() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [showInstall, setShowInstall] = useState<'git' | 'path' | 'upload' | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [skillName, setSkillName] = useState('')
  const [installing, setInstalling] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [toggling, setToggling] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const { canEdit, isAdmin, isMockTester } = useAuth()
  const mockMode = isMockTester()
  const canMutateRegistry = canEdit() && !mockMode
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null)

  const loadSkills = useCallback(async () => {
    try {
      const res = await api<{ skills: SkillInfo[] }>('/skills/list')
      setSkills(res.skills)
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载失败' })
    }
  }, [])

  useEffect(() => { loadSkills() }, [loadSkills])

  const toggleSkill = async (name: string, enabled: boolean) => {
    setToggling(name)
    setMessage(null)
    try {
      await api('/skills/toggle', {
        method: 'PUT',
        body: JSON.stringify({ name, enabled }),
      })
      setSkills(prev => prev.map(s => s.name === name ? { ...s, enabled } : s))
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '切换失败' })
    } finally {
      setToggling(null)
    }
  }

  const installFromGit = async () => {
    if (!gitUrl.trim()) return
    setInstalling(true)
    setMessage(null)
    try {
      await api('/skills/install/git', {
        method: 'POST',
        body: JSON.stringify({ git_url: gitUrl, name: skillName || null }),
      })
      setMessage({ type: 'success', text: '技能安装成功' })
      setShowInstall(null)
      setGitUrl('')
      setSkillName('')
      loadSkills()
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '安装失败' })
    } finally {
      setInstalling(false)
    }
  }

  const installFromPath = async () => {
    if (!localPath.trim()) return
    setInstalling(true)
    setMessage(null)
    try {
      await api('/skills/install/path', {
        method: 'POST',
        body: JSON.stringify({ source_path: localPath, name: skillName || null }),
      })
      setMessage({ type: 'success', text: '技能导入成功' })
      setShowInstall(null)
      setLocalPath('')
      setSkillName('')
      loadSkills()
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '导入失败' })
    } finally {
      setInstalling(false)
    }
  }

  const installFromUpload = async () => {
    if (!selectedFiles || selectedFiles.length === 0) return
    if (!skillName.trim()) {
      setMessage({ type: 'error', text: '请输入技能名称' })
      return
    }
    setInstalling(true)
    setMessage(null)
    try {
      const formData = new FormData()
      formData.append('name', skillName)
      for (const file of Array.from(selectedFiles)) {
        // webkitRelativePath preserves directory structure
        const relativePath = (file as any).webkitRelativePath || file.name
        formData.append('files', file, relativePath)
      }
      await api('/skills/install/upload', {
        method: 'POST',
        body: formData,
        // Let browser set Content-Type with boundary for multipart
        headers: {},
      })
      setMessage({ type: 'success', text: '技能上传安装成功' })
      setShowInstall(null)
      setSkillName('')
      setSelectedFiles(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      loadSkills()
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '上传失败' })
    } finally {
      setInstalling(false)
    }
  }

  const deleteSkill = async (name: string) => {
    if (!confirm(`确定要删除技能 "${name}" 吗？`)) return
    setDeleting(name)
    setMessage(null)
    try {
      await api('/skills/delete', {
        method: 'DELETE',
        body: JSON.stringify({ name }),
      })
      setMessage({ type: 'success', text: '技能删除成功' })
      loadSkills()
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '删除失败' })
    } finally {
      setDeleting(null)
    }
  }

  const avaSkills = skills.filter(s => s.source === 'ava')
  const agentsSkills = skills.filter(s => s.source === 'agents')
  const builtinSkills = skills.filter(s => s.source === 'builtin')

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Puzzle className="w-5 h-5 text-purple-400" />
          技能
          <span className="text-sm text-[var(--text-secondary)] font-normal">({skills.length} 个)</span>
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={loadSkills}
            title="刷新"
            className="p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          {canMutateRegistry && (
            <button
              onClick={() => setShowInstall(showInstall ? null : 'git')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium"
            >
              <Plus className="w-4 h-4" /> 添加技能
            </button>
          )}
        </div>
      </div>

      {message && (
        <div className={`p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}>
          {message.text}
        </div>
      )}

      {mockMode && (
        <div className="rounded-xl border border-amber-500/25 bg-amber-500/8 p-3 text-sm text-amber-200">
          `mock_tester` 可以查看工具/技能状态，并编辑 mock `TOOLS.md`；启用、安装、删除技能仍保持禁用，避免影响真实 runtime。
        </div>
      )}

      {/* Install Panel */}
      {showInstall && canMutateRegistry && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">添加新技能</h3>
            <button onClick={() => setShowInstall(null)} title="关闭" className="p-1 rounded-lg hover:bg-[var(--bg-tertiary)]">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Method Tabs */}
          <div className="flex gap-2 mb-4">
            {([
              { key: 'git' as const, icon: GitBranch, label: 'Git 仓库' },
              { key: 'path' as const, icon: FolderOpen, label: '本地路径' },
              { key: 'upload' as const, icon: Upload, label: '文件夹选择' },
            ]).map(({ key, icon: Icon, label }) => (
              <button
                key={key}
                onClick={() => setShowInstall(key)}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  showInstall === key
                    ? 'bg-[var(--accent)] text-white'
                    : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
                )}
              >
                <Icon className="w-4 h-4" /> {label}
              </button>
            ))}
          </div>

          {showInstall === 'git' && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-[var(--text-secondary)] mb-1 block">Git 仓库 URL</label>
                <input
                  type="text"
                  value={gitUrl}
                  onChange={(e) => setGitUrl(e.target.value)}
                  placeholder="https://github.com/user/skill-name.git"
                  className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-[var(--text-secondary)] mb-1 block">技能名称（可选）</label>
                <input
                  type="text"
                  value={skillName}
                  onChange={(e) => setSkillName(e.target.value)}
                  placeholder="留空则使用仓库名"
                  className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm"
                />
              </div>
              <button
                onClick={installFromGit}
                disabled={!gitUrl.trim() || installing}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium disabled:opacity-40"
              >
                {installing ? '安装中...' : '从 Git 安装'}
              </button>
            </div>
          )}

          {showInstall === 'path' && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-[var(--text-secondary)] mb-1 block">本地路径</label>
                <input
                  type="text"
                  value={localPath}
                  onChange={(e) => setLocalPath(e.target.value)}
                  placeholder="/path/to/skill-directory"
                  className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-[var(--text-secondary)] mb-1 block">技能名称（可选）</label>
                <input
                  type="text"
                  value={skillName}
                  onChange={(e) => setSkillName(e.target.value)}
                  placeholder="留空则使用文件夹名"
                  className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm"
                />
              </div>
              <button
                onClick={installFromPath}
                disabled={!localPath.trim() || installing}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium disabled:opacity-40"
              >
                {installing ? '导入中...' : '从本地导入'}
              </button>
            </div>
          )}

          {showInstall === 'upload' && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-[var(--text-secondary)] mb-1 block">技能名称</label>
                <input
                  type="text"
                  value={skillName}
                  onChange={(e) => setSkillName(e.target.value)}
                  placeholder="my-skill"
                  className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-[var(--text-secondary)] mb-1 block">选择技能文件夹</label>
                <input
                  ref={fileInputRef}
                  type="file"
                  /* @ts-expect-error webkitdirectory is non-standard */
                  webkitdirectory=""
                  directory=""
                  multiple
                  onChange={(e) => setSelectedFiles(e.target.files)}
                  className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-sm file:mr-3 file:px-3 file:py-1 file:rounded file:border-0 file:bg-[var(--accent)]/10 file:text-[var(--accent)] file:text-xs file:font-medium"
                />
                {selectedFiles && selectedFiles.length > 0 && (
                  <p className="text-xs text-[var(--text-secondary)] mt-1">
                    已选择 {selectedFiles.length} 个文件
                  </p>
                )}
              </div>
              <button
                onClick={installFromUpload}
                disabled={!selectedFiles || selectedFiles.length === 0 || !skillName.trim() || installing}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium disabled:opacity-40"
              >
                {installing ? '上传中...' : '上传安装'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Ava Skills (custom) */}
      {avaSkills.length > 0 && (
        <SkillGroup
          title="自定义技能"
          icon={<Package className="w-4 h-4" />}
          skills={avaSkills}
          onToggle={canMutateRegistry ? toggleSkill : undefined}
          onDelete={isAdmin() && !mockMode ? deleteSkill : undefined}
          toggling={toggling}
          deleting={deleting}
          colorClass="text-purple-400"
          badgeClass="bg-purple-500/10 text-purple-400"
        />
      )}

      {/* Agents Skills */}
      {agentsSkills.length > 0 && (
        <SkillGroup
          title=".agents 技能"
          icon={<Bot className="w-4 h-4" />}
          skills={agentsSkills}
          onToggle={canMutateRegistry ? toggleSkill : undefined}
          toggling={toggling}
          deleting={deleting}
          colorClass="text-amber-400"
          badgeClass="bg-amber-500/10 text-amber-400"
        />
      )}

      {/* Builtin Skills */}
      {builtinSkills.length > 0 && (
        <SkillGroup
          title="内置技能"
          icon={<Wrench className="w-4 h-4" />}
          skills={builtinSkills}
          onToggle={canMutateRegistry ? toggleSkill : undefined}
          toggling={toggling}
          deleting={deleting}
          colorClass="text-[var(--accent)]"
          badgeClass="bg-[var(--accent)]/10 text-[var(--accent)]"
        />
      )}

      {skills.length === 0 && (
        <div className="text-center py-8 text-[var(--text-secondary)]">
          暂无技能
        </div>
      )}
    </div>
  )
}

// ── Skill Group ───────────────────────────────────────────────────────────

function SkillGroup({
  title,
  icon,
  skills,
  onToggle,
  onDelete,
  toggling,
  deleting,
  colorClass,
  badgeClass,
}: {
  title: string
  icon: React.ReactNode
  skills: SkillInfo[]
  onToggle?: (name: string, enabled: boolean) => void
  onDelete?: (name: string) => void
  toggling: string | null
  deleting: string | null
  colorClass: string
  badgeClass: string
}) {
  return (
    <div>
      <h3 className={cn('text-sm font-medium text-[var(--text-secondary)] mb-3 flex items-center gap-2', colorClass)}>
        {icon} {title}
        <span className="text-xs font-normal">({skills.length})</span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {skills.map(skill => (
          <SkillCard
            key={skill.name}
            skill={skill}
            onToggle={onToggle ? () => onToggle(skill.name, !skill.enabled) : undefined}
            onDelete={onDelete ? () => onDelete(skill.name) : undefined}
            toggling={toggling === skill.name}
            deleting={deleting === skill.name}
            badgeClass={badgeClass}
          />
        ))}
      </div>
    </div>
  )
}

// ── Skill Card ────────────────────────────────────────────────────────────

function SkillCard({
  skill,
  onToggle,
  onDelete,
  toggling,
  deleting,
  badgeClass,
}: {
  skill: SkillInfo
  onToggle?: () => void
  onDelete?: () => void
  toggling?: boolean
  deleting?: boolean
  badgeClass: string
}) {
  const sourceLabels: Record<string, string> = {
    ava: 'custom',
    agents: '.agents',
    builtin: 'builtin',
  }

  return (
    <div className={cn(
      'bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 transition-all group',
      skill.enabled ? 'hover:border-[var(--accent)]/50' : 'opacity-60',
    )}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <div className={cn('p-1.5 rounded-lg shrink-0', badgeClass)}>
            <Puzzle className="w-4 h-4" />
          </div>
          <span className="font-medium text-sm truncate">{skill.name}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          {skill.always && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--success)]/10 text-[var(--success)]">always</span>
          )}
          <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badgeClass)}>
            {sourceLabels[skill.source]}
          </span>
        </div>
      </div>

      <p className="text-xs text-[var(--text-secondary)] mt-2 line-clamp-2">{skill.description || '暂无描述'}</p>

      <div className="flex items-center justify-between mt-3 pt-2 border-t border-[var(--border)]">
        <div className="flex items-center gap-2">
          {onToggle && (
            <ToggleSwitch
              enabled={skill.enabled}
              onToggle={onToggle}
              disabled={toggling}
            />
          )}
          {skill.install_method && (
            <span className="text-[10px] text-[var(--text-secondary)]/60">
              via {skill.install_method}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {skill.install_method === 'git' && skill.git_url && (
            <button
              onClick={() => window.open(skill.git_url!, '_blank')}
              title="打开来源仓库"
              className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--accent)] hover:bg-[var(--accent)]/10 opacity-0 group-hover:opacity-100 transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              disabled={deleting}
              title="删除"
              className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[var(--danger)]/10 opacity-0 group-hover:opacity-100 transition-all"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function SkillsPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Puzzle className="w-6 h-6 text-[var(--accent)]" />
          技能 & 工具
        </h1>
        <p className="text-[var(--text-secondary)] text-sm mt-1">管理内置工具和外置技能</p>
      </div>

      <div className="space-y-8">
        <ToolsSection />
        <MCPSection />
        <SkillsSection />
      </div>
    </div>
  )
}
