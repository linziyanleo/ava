export interface LegacyRedirectRule {
  from: string
  to: string
  deprecatedAfter: string
  defaults?: Record<string, string>
  renameParams?: Record<string, string>
}

export interface RedirectLocation {
  pathname: string
  search: string
}

export const legacyRedirectMatrix: LegacyRedirectRule[] = [
  { from: '/agents', to: '/settings/agents-config', deprecatedAfter: '0.3.0' },
  { from: '/config', to: '/settings/system/console', deprecatedAfter: '0.3.0' },
  { from: '/memory', to: '/settings/agents-config/nanobot/memory', deprecatedAfter: '0.3.0' },
  { from: '/persona', to: '/settings/agents-config/nanobot/persona', deprecatedAfter: '0.3.0' },
  { from: '/skills', to: '/settings/tools/skills', deprecatedAfter: '0.3.0' },
  { from: '/media', to: '/', deprecatedAfter: '0.3.0', defaults: { view: 'tasks', task_view: 'artifacts' } },
  { from: '/chat', to: '/', deprecatedAfter: '0.3.0', renameParams: { session_key: 'session_id' } },
  { from: '/tasks', to: '/', deprecatedAfter: '0.3.0', defaults: { view: 'tasks', task_view: 'scheduled' } },
  { from: '/bg-tasks', to: '/', deprecatedAfter: '0.3.0', defaults: { view: 'tasks', task_view: 'history' } },
  { from: '/tokens', to: '/settings/statistics', deprecatedAfter: '0.3.0' },
  { from: '/users', to: '/settings/users', deprecatedAfter: '0.3.0' },
  { from: '/browser', to: '/settings/system/browser', deprecatedAfter: '0.3.0' },
  { from: '/gateway', to: '/settings/system/gateway', deprecatedAfter: '0.3.0' },
  { from: '/files', to: '/settings/agents-config/nanobot/memory', deprecatedAfter: '0.3.0' },
  { from: '/audit', to: '/settings/users', deprecatedAfter: '0.3.0' },
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
