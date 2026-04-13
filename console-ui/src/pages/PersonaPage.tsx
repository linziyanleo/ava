import { useEffect, useState, useCallback } from 'react'
import Editor from '@monaco-editor/react'
import { UserCog, Save, RefreshCw, Users, Heart, Wrench, User } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { cn } from '../lib/utils'

interface FileData {
  path: string
  content: string
  mtime: number
}

const PERSONA_FILES = [
  { key: 'agents', name: 'AGENTS.md', description: 'Agent 指令配置', icon: Users },
  { key: 'soul', name: 'SOUL.md', description: '人格设定', icon: Heart },
  { key: 'tools', name: 'TOOLS.md', description: '工具说明', icon: Wrench },
  { key: 'user', name: 'USER.md', description: '用户信息', icon: User },
] as const

type FileKey = typeof PERSONA_FILES[number]['key']

export default function PersonaPage() {
  const [activeFile, setActiveFile] = useState<FileKey>('agents')
  const [files, setFiles] = useState<Record<FileKey, FileData | null>>({
    agents: null,
    soul: null,
    tools: null,
    user: null,
  })
  const [edits, setEdits] = useState<Record<FileKey, string>>({
    agents: '',
    soul: '',
    tools: '',
    user: '',
  })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const { canEdit } = useAuth()

  const loadFiles = useCallback(async () => {
    try {
      const results = await Promise.all(
        PERSONA_FILES.map(f =>
          api<FileData>(`/files/read?path=workspace/${f.name}`)
            .then(data => ({ key: f.key, data }))
            .catch(() => ({ key: f.key, data: null }))
        )
      )
      const newFiles: Record<string, FileData | null> = {}
      const newEdits: Record<string, string> = {}
      for (const { key, data } of results) {
        newFiles[key] = data
        newEdits[key] = data?.content || ''
      }
      setFiles(newFiles as Record<FileKey, FileData | null>)
      setEdits(newEdits as Record<FileKey, string>)
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '加载失败' })
    }
  }, [])

  useEffect(() => { loadFiles() }, [loadFiles])

  const saveFile = async () => {
    const file = files[activeFile]
    const content = edits[activeFile]
    if (!file) return

    setSaving(true)
    setMessage(null)
    try {
      const result = await api<FileData>('/files/write', {
        method: 'PUT',
        body: JSON.stringify({ path: file.path, content, expected_mtime: file.mtime }),
      })
      setFiles(prev => ({ ...prev, [activeFile]: { ...file, content, mtime: result.mtime } }))
      setMessage({ type: 'success', text: `${PERSONA_FILES.find(f => f.key === activeFile)?.name} 保存成功` })
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  const hasChanges = edits[activeFile] !== files[activeFile]?.content
  const currentFileInfo = PERSONA_FILES.find(f => f.key === activeFile)!

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <UserCog className="w-6 h-6 text-[var(--accent)]" />
            人物设定
          </h1>
          <p className="text-[var(--text-secondary)] text-sm mt-1">管理 Agent 的核心配置文件</p>
        </div>
        <button
          onClick={loadFiles}
          title="刷新所有文件"
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm"
        >
          <RefreshCw className="w-4 h-4" /> 刷新
        </button>
      </div>

      {/* File Tabs */}
      <div className="flex items-center gap-1 mb-3 overflow-x-auto scrollbar-none" style={{ WebkitOverflowScrolling: 'touch' }}>
        {PERSONA_FILES.map(file => {
          const Icon = file.icon
          const isActive = activeFile === file.key
          const fileHasChanges = edits[file.key] !== files[file.key]?.content
          return (
            <button
              key={file.key}
              onClick={() => setActiveFile(file.key)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors shrink-0',
                isActive
                  ? 'bg-[var(--accent)] text-white'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {file.name}
              {fileHasChanges && (
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full shrink-0',
                  isActive ? 'bg-white' : 'bg-[var(--warning)]'
                )} />
              )}
            </button>
          )
        })}
      </div>

      {message && (
        <div className={`mb-4 p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}>
          {message.text}
        </div>
      )}

      {/* Editor */}
      <div className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden flex flex-col min-h-0">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)] shrink-0">
          <div className="flex items-center gap-3">
            <currentFileInfo.icon className="w-5 h-5 text-[var(--accent)]" />
            <div>
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{currentFileInfo.name}</h3>
              <p className="text-xs text-[var(--text-secondary)]">{currentFileInfo.description}</p>
            </div>
          </div>
          {canEdit() && files[activeFile] && (
            <button
              onClick={saveFile}
              disabled={!hasChanges || saving}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                hasChanges
                  ? 'bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
                'disabled:opacity-40'
              )}
            >
              <Save className="w-4 h-4" />
              {saving ? '保存中...' : hasChanges ? '保存' : '已保存'}
            </button>
          )}
        </div>
        <div className="flex-1 min-h-0">
          {files[activeFile] ? (
            <Editor
              height="100%"
              language="markdown"
              theme="vs-dark"
              value={edits[activeFile]}
              onChange={(v) => setEdits(prev => ({ ...prev, [activeFile]: v || '' }))}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                readOnly: !canEdit(),
                wordWrap: 'on',
                scrollBeyondLastLine: false,
                lineNumbers: 'on',
                padding: { top: 16 },
              }}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-[var(--text-secondary)] text-sm">
              文件不存在
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
