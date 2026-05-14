import { create } from 'zustand'
import { api, setOnUnauthorized } from '../api/client'

export interface User {
  username: string
  created_at: string
}

interface AuthState {
  user: User | null
  loading: boolean
  login: (passphrase: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
}

export const useAuth = create<AuthState>((set) => {
  // 当非 auth 请求收到 401 时，清除用户状态，让 ProtectedRoute 自动重定向到登录页
  setOnUnauthorized(() => set({ user: null, loading: false }))

  return {
  user: null,
  loading: true,

  login: async (passphrase) => {
    const res = await api<{ user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: 'owner', password: passphrase }),
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
}})
