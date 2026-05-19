import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './stores/auth'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import AgentDashboardPage from './pages/AgentDashboardPage'
import DashboardPage from './pages/DashboardPage'
import ConfigPage from './pages/ConfigPage'
import MemoryPage from './pages/MemoryPage'
import PersonaPage from './pages/PersonaPage'
import SkillsPage from './pages/SkillsPage'
import SettingsToolsWorkflowsPage from './pages/SettingsToolsWorkflowsPage'
import SettingsToolsWorkflowsDetailPage from './pages/SettingsToolsWorkflowsDetailPage'
import ChatPage from './pages/ChatPage'
import TokenStatsPage from './pages/TokenStatsPage'
import BrowserPage from './pages/BrowserPage'
import LanAccessPage from './pages/LanAccessPage'
import SettingsPage, { DesktopSettingsPage, SettingsVersionPage } from './pages/SettingsPage'
import WorkflowDetailPage from './pages/WorkflowDetailPage'
import { legacyRedirectMatrix, resolveLegacyRedirect } from './router/redirect-matrix'
import { useDeepLink } from './hooks/useDeepLink'

const MobilePairPage = lazy(() => import('./pages/MobilePairPage'))

function LegacyRedirect() {
  const location = useLocation()
  const rule = legacyRedirectMatrix.find((item) => item.from === location.pathname)
  const target = resolveLegacyRedirect(location.pathname, location.search) || { pathname: '/', search: '' }

  useEffect(() => {
    if (!import.meta.env.DEV || !rule) return
    console.warn(
      `[Ava] Legacy route "${rule.from}" is deprecated and will be removed after ${rule.deprecatedAfter}; use "${rule.to}" instead.`,
    )
  }, [rule])

  return <Navigate to={target} replace />
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center text-[var(--text-secondary)]">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function DeepLinkBridge() {
  useDeepLink()
  return null
}

function applyPlatformAttr() {
  const desktop = (window as unknown as { avaDesktop?: { platform?: string } }).avaDesktop
  document.documentElement.dataset.platform = desktop?.platform ?? 'web'
}

export default function App() {
  const { checkAuth, user, loading } = useAuth()

  useEffect(() => {
    applyPlatformAttr()
    checkAuth()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <BrowserRouter>
      <DeepLinkBridge />
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
          <Route index element={<ChatPage />} />
          <Route path="workflows/:chainId" element={<WorkflowDetailPage />} />
          <Route path="settings" element={<SettingsPage />}>
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
            <Route path="tools/workflows" element={<SettingsToolsWorkflowsPage />} />
            <Route path="tools/workflows/:workflowId" element={<SettingsToolsWorkflowsDetailPage />} />
            <Route path="system" element={<Navigate to="gateway" replace />} />
            <Route path="system/desktop" element={<DesktopSettingsPage />} />
            <Route path="system/lan-access" element={<LanAccessPage />} />
            <Route path="system/gateway" element={<DashboardPage />} />
            <Route path="system/browser" element={<BrowserPage />} />
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
