import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './stores/auth'
import type { UserRole } from './stores/auth'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import AgentDashboardPage from './pages/AgentDashboardPage'
import DashboardPage from './pages/DashboardPage'
import ConfigPage from './pages/ConfigPage'
import MemoryPage from './pages/MemoryPage'
import PersonaPage from './pages/PersonaPage'
import SkillsPage from './pages/SkillsPage'
import ChatPage from './pages/ChatPage'
import TokenStatsPage from './pages/TokenStatsPage'
import UsersPage from './pages/UsersPage'
import BrowserPage from './pages/BrowserPage'
import LanAccessPage from './pages/LanAccessPage'
import SettingsPage, { SettingsVersionPage } from './pages/SettingsPage'
import { legacyRedirectMatrix, resolveLegacyRedirect } from './router/redirect-matrix'

const READ_ONLY_ROLES: UserRole[] = ['admin', 'editor', 'viewer', 'read_only', 'mock_tester']
const MobilePairPage = lazy(() => import('./pages/MobilePairPage'))

function LegacyRedirect() {
  const location = useLocation()
  const target = resolveLegacyRedirect(location.pathname, location.search) || { pathname: '/', search: '' }
  return <Navigate to={target} replace />
}

function ProtectedRoute({
  children,
  allowedRoles,
}: {
  children: React.ReactNode
  allowedRoles?: UserRole[]
}) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center text-[var(--text-secondary)]">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  if (allowedRoles && !allowedRoles.includes(user.role)) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  const { checkAuth, user, loading } = useAuth()

  useEffect(() => {
    checkAuth()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={user && !loading ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route
          path="/lan/pair"
          element={
            <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-[var(--text-secondary)]">Loading...</div>}>
              <MobilePairPage />
            </Suspense>
          }
        />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ProtectedRoute allowedRoles={READ_ONLY_ROLES}><ChatPage /></ProtectedRoute>} />
          <Route path="settings" element={<ProtectedRoute allowedRoles={READ_ONLY_ROLES}><SettingsPage /></ProtectedRoute>}>
            <Route index element={<Navigate to="agents-config" replace />} />
            <Route path="agents-config" element={<AgentDashboardPage />} />
            <Route path="agents-config/:agentKind" element={<AgentDashboardPage />} />
            <Route path="agents-config/nanobot/config" element={<ConfigPage mode="nanobot" />} />
            <Route path="agents-config/codex/config" element={<ConfigPage mode="codex" />} />
            <Route path="agents-config/claude-code/config" element={<ConfigPage mode="claude_code" />} />
            <Route path="agents-config/nanobot/memory" element={<MemoryPage />} />
            <Route path="agents-config/nanobot/persona" element={<PersonaPage />} />
            <Route path="agents-config/image-gen/config" element={<ConfigPage mode="image_gen" />} />
            <Route path="statistics" element={<TokenStatsPage />} />
            <Route path="tools" element={<Navigate to="skills" replace />} />
            <Route path="tools/skills" element={<SkillsPage />} />
            <Route path="users" element={<ProtectedRoute allowedRoles={['admin']}><UsersPage /></ProtectedRoute>} />
            <Route path="system" element={<Navigate to="gateway" replace />} />
            <Route path="system/lan-access" element={<ProtectedRoute allowedRoles={['admin']}><LanAccessPage /></ProtectedRoute>} />
            <Route path="system/gateway" element={<DashboardPage />} />
            <Route path="system/browser" element={<ProtectedRoute allowedRoles={['admin', 'editor', 'viewer']}><BrowserPage /></ProtectedRoute>} />
            <Route path="system/console" element={<ConfigPage mode="console" />} />
            <Route path="system/version" element={<SettingsVersionPage />} />
          </Route>
          {legacyRedirectMatrix.map((rule) => (
            <Route key={rule.from} path={rule.from.slice(1)} element={<LegacyRedirect />} />
          ))}
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
