import { useEffect, useState, useCallback } from 'react'
import { Pencil, Trash2, UserPlus, LogOut, ChevronDown, ChevronRight, ChevronLeft, ClipboardList } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { cn } from '../lib/utils'

interface User {
  username: string
  role: string
  created_at: string
}

interface AuditEntry {
  ts: string
  user: string
  role: string
  action: string
  target: string
  detail: Record<string, unknown> | null
  ip: string
}

interface AuditResponse {
  entries: AuditEntry[]
  total: number
  page: number
  size: number
}

const ACTION_COLORS: Record<string, string> = {
  'auth.login': 'text-[var(--success)]',
  'auth.login_failed': 'text-[var(--danger)]',
  'config.update': 'text-[var(--accent)]',
  'file.update': 'text-[var(--accent)]',
  'gateway.restart': 'text-[var(--warning)]',
  'secret.reveal': 'text-[var(--danger)]',
  'user.create': 'text-purple-400',
  'user.update': 'text-purple-400',
  'user.delete': 'text-[var(--danger)]',
  'chat.send': 'text-[var(--text-secondary)]',
  'media.delete': 'text-[var(--danger)]',
}

function UserAuditLog({ username }: { username: string }) {
  const [data, setData] = useState<AuditResponse | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  const loadAuditLogs = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({ page: String(page), size: '10', user: username })
    try {
      const res = await api<AuditResponse>(`/audit/logs?${params}`)
      setData(res)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [username, page])

  useEffect(() => { loadAuditLogs() }, [loadAuditLogs])

  const totalPages = data ? Math.ceil(data.total / data.size) : 0

  if (loading) {
    return <div className="p-4 text-sm text-[var(--text-secondary)]">加载中...</div>
  }

  if (!data || data.entries.length === 0) {
    return (
      <div className="p-4 text-center text-[var(--text-secondary)]">
        <ClipboardList className="w-6 h-6 mx-auto mb-2 opacity-30" />
        <p className="text-sm">暂无行为日志</p>
      </div>
    )
  }

  return (
    <div className="p-4 pt-2">
      <table className="w-full">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="text-left px-3 py-2 text-xs font-medium text-[var(--text-secondary)] uppercase">时间</th>
            <th className="text-left px-3 py-2 text-xs font-medium text-[var(--text-secondary)] uppercase">操作</th>
            <th className="text-left px-3 py-2 text-xs font-medium text-[var(--text-secondary)] uppercase">目标</th>
            <th className="text-left px-3 py-2 text-xs font-medium text-[var(--text-secondary)] uppercase">IP</th>
          </tr>
        </thead>
        <tbody>
          {data.entries.map((entry, i) => (
            <tr key={i} className="border-b border-[var(--border)] last:border-0">
              <td className="px-3 py-2 text-xs text-[var(--text-secondary)] whitespace-nowrap">
                {new Date(entry.ts).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-sm">
                <span className={`font-mono text-xs ${ACTION_COLORS[entry.action] || 'text-[var(--text-secondary)]'}`}>
                  {entry.action}
                </span>
              </td>
              <td className="px-3 py-2 text-xs text-[var(--text-secondary)] max-w-[150px] truncate">{entry.target || '-'}</td>
              <td className="px-3 py-2 text-xs text-[var(--text-secondary)] font-mono">{entry.ip || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--border)]">
          <p className="text-xs text-[var(--text-secondary)]">{data.total} 条记录</p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              title="上一页"
              className="p-1.5 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="text-xs">{page} / {totalPages}</span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              title="下一页"
              className="p-1.5 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function UsersPage() {
  const { logout, isAdmin } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [showForm, setShowForm] = useState(false)
  const [editingUser, setEditingUser] = useState<string | null>(null)
  const [expandedUser, setExpandedUser] = useState<string | null>(null)
  const [form, setForm] = useState({ username: '', password: '', role: 'viewer' })
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadUsers = useCallback(async () => {
    const list = await api<User[]>('/users')
    setUsers(list)
  }, [])

  useEffect(() => { loadUsers() }, [loadUsers])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setMessage(null)
    try {
      if (editingUser) {
        await api(`/users/${editingUser}`, {
          method: 'PUT',
          body: JSON.stringify({
            password: form.password || null,
            role: form.role,
          }),
        })
        setMessage({ type: 'success', text: '用户已更新' })
      } else {
        await api('/users', {
          method: 'POST',
          body: JSON.stringify(form),
        })
        setMessage({ type: 'success', text: '用户已创建' })
      }
      setShowForm(false)
      setEditingUser(null)
      setForm({ username: '', password: '', role: 'viewer' })
      loadUsers()
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '操作失败' })
    }
  }

  const deleteUser = async (username: string) => {
    if (!confirm(`确定删除用户 "${username}" 吗？`)) return
    try {
      await api(`/users/${username}`, { method: 'DELETE' })
      loadUsers()
      setMessage({ type: 'success', text: '用户已删除' })
      if (expandedUser === username) setExpandedUser(null)
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '删除失败' })
    }
  }

  const startEdit = (user: User) => {
    setEditingUser(user.username)
    setForm({ username: user.username, password: '', role: user.role })
    setShowForm(true)
  }

  const toggleExpand = (username: string) => {
    setExpandedUser(prev => prev === username ? null : username)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">用户管理</h1>
        <div className="flex gap-2">
          {isAdmin() && (
            <button
              onClick={() => {
                setShowForm(true);
                setEditingUser(null);
                setForm({ username: '', password: '', role: 'viewer' });
              }}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium"
            >
              <UserPlus className="w-4 h-4" /> 添加用户
            </button>
          )}
          <button
            onClick={logout}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--danger)]/10 text-[var(--danger)] hover:bg-[var(--danger)]/20 text-sm font-medium"
          >
            <LogOut className="w-4 h-4" /> 退出登录
          </button>
        </div>
      </div>

      {message && (
        <div
          className={`mb-4 p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}
        >
          {message.text}
        </div>
      )}

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="mb-6 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 space-y-4"
        >
          <h2 className="text-lg font-semibold">{editingUser ? '编辑用户' : '新用户'}</h2>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">用户名</label>
              <input
                type="text"
                value={form.username}
                onChange={e => setForm({ ...form, username: e.target.value })}
                disabled={!!editingUser}
                className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-primary)] disabled:opacity-50"
                required={!editingUser}
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">
                密码 {editingUser && '(留空则不修改)'}
              </label>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-primary)]"
                required={!editingUser}
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">角色</label>
              <select
                value={form.role}
                onChange={e => setForm({ ...form, role: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] text-[var(--text-primary)]"
              >
                <option value="admin">管理员</option>
                <option value="editor">可编辑</option>
                <option value="viewer">可查看</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-medium">
              {editingUser ? '更新' : '创建'}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="px-4 py-2 rounded-lg bg-[var(--bg-tertiary)] text-[var(--text-secondary)] text-sm"
            >
              取消
            </button>
          </div>
        </form>
      )}

      <div className="space-y-3">
        {users.map(u => (
          <div
            key={u.username}
            className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden"
          >
            {/* User Row */}
            <div
              className={cn(
                'flex items-center justify-between px-5 py-3 cursor-pointer transition-colors',
                expandedUser === u.username ? 'bg-[var(--bg-tertiary)]/50' : 'hover:bg-[var(--bg-tertiary)]/30'
              )}
              onClick={() => isAdmin() && toggleExpand(u.username)}
            >
              <div className="flex items-center gap-4">
                {isAdmin() && (
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleExpand(u.username) }}
                    className="p-1 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    title="展开/收起行为日志"
                  >
                    {expandedUser === u.username ? (
                      <ChevronDown className="w-4 h-4" />
                    ) : (
                      <ChevronRight className="w-4 h-4" />
                    )}
                  </button>
                )}
                <div>
                  <p className="text-sm font-medium">{u.username}</p>
                  <p className="text-xs text-[var(--text-secondary)]">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '未知时间'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    u.role === 'admin'
                      ? 'bg-[var(--danger)]/10 text-[var(--danger)]'
                      : u.role === 'editor'
                        ? 'bg-[var(--accent)]/10 text-[var(--accent)]'
                        : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
                  }`}
                >
                  {u.role === 'admin' ? '管理员' : u.role === 'editor' ? '可编辑' : '可查看'}
                </span>
                <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={() => startEdit(u)}
                    title="编辑"
                    className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--accent)] hover:bg-[var(--bg-tertiary)]"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => deleteUser(u.username)}
                    title="删除"
                    className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--danger)] hover:bg-[var(--bg-tertiary)]"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Audit Log (Expandable) */}
            {isAdmin() && expandedUser === u.username && (
              <div className="border-t border-[var(--border)] bg-[var(--bg-primary)]">
                <div className="px-5 py-2 border-b border-[var(--border)]">
                  <h4 className="text-xs font-medium text-[var(--text-secondary)] uppercase flex items-center gap-1.5">
                    <ClipboardList className="w-3.5 h-3.5" />
                    行为日志
                  </h4>
                </div>
                <UserAuditLog username={u.username} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
