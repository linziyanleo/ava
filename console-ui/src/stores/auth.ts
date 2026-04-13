import { create } from 'zustand'
import { api, setOnUnauthorized } from '../api/client'

export type UserRole = 'admin' | 'editor' | 'viewer' | 'mock_tester'

export interface User {
  username: string
  role: UserRole
  created_at: string
}

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
  isAdmin: () => boolean
  isMockTester: () => boolean
  canEdit: () => boolean
}

export const useAuth = create<AuthState>((set, get) => {
  // 当非 auth 请求收到 401 时，清除用户状态，让 ProtectedRoute 自动重定向到登录页
  setOnUnauthorized(() => set({ user: null, loading: false }))

  return {
  user: null,
  loading: true,

  login: async (username, password) => {
    const res = await api<{ user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    set({ user: res.user, loading: false })
  },

  logout: () => {
    void api('/auth/logout', { method: 'POST' }).catch(() => {})
    set({ user: null })
  },

  checkAuth: async () => {
    try {
      const user = await api<User>('/auth/me')
      set({ user, loading: false })
    } catch {
      set({ user: null, loading: false })
    }
  },

  isAdmin: () => get().user?.role === 'admin',
  isMockTester: () => get().user?.role === 'mock_tester',
  canEdit: () => {
    const role = get().user?.role
    return role === 'admin' || role === 'editor' || role === 'mock_tester'
  },
}})
