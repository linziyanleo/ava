export interface LegacyRedirectRule {
  from: string
  to: string
  defaults?: Record<string, string>
  renameParams?: Record<string, string>
}

export interface RedirectLocation {
  pathname: string
  search: string
}

export const legacyRedirectMatrix: LegacyRedirectRule[] = [
  { from: '/agents', to: '/settings/agents-config' },
  { from: '/config', to: '/settings/system/console' },
  { from: '/memory', to: '/settings/agents-config/nanobot/memory' },
  { from: '/persona', to: '/settings/agents-config/nanobot/persona' },
  { from: '/skills', to: '/settings/tools/skills' },
  { from: '/media', to: '/', defaults: { view: 'tasks', task_view: 'artifacts' } },
  { from: '/chat', to: '/', renameParams: { session_key: 'session_id' } },
  { from: '/tasks', to: '/', defaults: { view: 'tasks', task_view: 'scheduled' } },
  { from: '/bg-tasks', to: '/', defaults: { view: 'tasks', task_view: 'history' } },
  { from: '/tokens', to: '/settings/statistics' },
  { from: '/users', to: '/settings/users' },
  { from: '/browser', to: '/settings/system/browser' },
  { from: '/gateway', to: '/settings/system/gateway' },
  { from: '/files', to: '/settings/agents-config/nanobot/memory' },
  { from: '/audit', to: '/settings/users' },
]

export function resolveLegacyRedirect(pathname: string, search: string): RedirectLocation | null {
  const rule = legacyRedirectMatrix.find((item) => item.from === pathname)
  if (!rule) return null

  const params = new URLSearchParams(search)
  const targetPathname = rule.from === '/tokens' && params.has('trace_id')
    ? '/'
    : rule.to

  Object.entries(rule.renameParams ?? {}).forEach(([from, to]) => {
    const value = params.get(from)
    if (value !== null && !params.has(to)) {
      params.set(to, value)
      params.delete(from)
    }
  })

  Object.entries(rule.defaults ?? {}).forEach(([key, value]) => {
    if (!params.has(key)) params.set(key, value)
  })

  const query = params.toString()
  return {
    pathname: targetPathname,
    search: query ? `?${query}` : '',
  }
}
