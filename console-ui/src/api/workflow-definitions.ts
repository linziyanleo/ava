/**
 * AVA-48 P2c: typed client for /api/workflow-definitions + /api/workflow-runs.
 *
 * The base `api()` helper throws on non-ok with a stringified detail, which is
 * not enough for 409 base-version-conflict where the server returns a structured
 * body (`current_version` / `current_definition_diff` / `your_base_version`). The
 * `patchDefinition` wrapper here uses `fetch` directly so callers can branch on
 * 409 vs other failures.
 */
import { api, wsUrl } from './client'

export interface WorkflowDefinitionDoc {
  workflow_id?: string
  version?: number
  name: string
  description?: string
  inputs?: Array<{ name: string; type?: string; description?: string; default?: unknown }>
  outputs?: Array<{ name: string; type?: string; description?: string }>
  steps: Array<{
    id: string
    kind: 'agent_task'
    agent: string
    task: { prompt_template: string; tools?: string[]; skill?: string | null }
    inputs?: Record<string, string>
    outputs?: string[]
    next?: string | null
  }>
}

export interface WorkflowSummary {
  workflow_id: string
  name: string
  description: string
  current_version: number
  created_by_agent: string
  created_at: number
  updated_at: number
  deleted_at: number | null
  current?: {
    version: number
    change_summary: string
    created_at: number
    definition: WorkflowDefinitionDoc | null
  }
}

export interface WorkflowVersion {
  workflow_id: string
  version: number
  definition_json: string
  change_summary: string
  base_version: number | null
  created_by_agent: string
  created_at: number
  is_current: boolean
}

export interface WorkflowRun {
  run_id: string
  workflow_id: string
  version: number
  triggered_by: string
  status: string
  started_at: number | null
  completed_at: number | null
  final_outputs_json: string
}

export interface WorkflowConflict {
  code: 'version_conflict'
  message: string
  current_version: number
  your_base_version: number
  current_definition_diff: {
    changed_top_level_keys: string[]
    step_count_yours: number | null
    step_count_current: number | null
  }
}

export interface WorkflowTemplateRow {
  id: string
  name: string
  description: string
  definition: WorkflowDefinitionDoc
}

export function listDefinitions(): Promise<{ workflows: WorkflowSummary[] }> {
  return api<{ workflows: WorkflowSummary[] }>('/workflow-definitions')
}

export function getDefinition(workflowId: string): Promise<WorkflowSummary> {
  return api<WorkflowSummary>(`/workflow-definitions/${encodeURIComponent(workflowId)}`)
}

export function listTemplates(): Promise<{ templates: WorkflowTemplateRow[] }> {
  return api<{ templates: WorkflowTemplateRow[] }>('/workflow-definitions/templates')
}

export function createDefinition(payload: {
  name: string
  description?: string
  definition: WorkflowDefinitionDoc
  change_summary?: string
}): Promise<WorkflowSummary> {
  return api<WorkflowSummary>('/workflow-definitions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export type PatchOutcome =
  | { kind: 'ok'; summary: WorkflowSummary }
  | { kind: 'conflict'; conflict: WorkflowConflict }
  | { kind: 'error'; status: number; message: string }

export async function patchDefinition(
  workflowId: string,
  payload: {
    base_version: number
    definition: WorkflowDefinitionDoc
    change_summary?: string
  },
): Promise<PatchOutcome> {
  const res = await fetch(`/api/workflow-definitions/${encodeURIComponent(workflowId)}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (res.status === 409) {
    return { kind: 'conflict', conflict: (await res.json()) as WorkflowConflict }
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (body?.detail) message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // ignore
    }
    return { kind: 'error', status: res.status, message }
  }
  return { kind: 'ok', summary: (await res.json()) as WorkflowSummary }
}

export function deleteDefinition(workflowId: string): Promise<{ workflow_id: string; deleted: true }> {
  return api(`/workflow-definitions/${encodeURIComponent(workflowId)}`, { method: 'DELETE' })
}

export function listVersions(workflowId: string): Promise<{ versions: WorkflowVersion[] }> {
  return api<{ versions: WorkflowVersion[] }>(
    `/workflow-definitions/${encodeURIComponent(workflowId)}/versions`,
  )
}

export function listRuns(workflowId: string, limit = 50): Promise<{ runs: WorkflowRun[] }> {
  return api<{ runs: WorkflowRun[] }>(
    `/workflow-definitions/${encodeURIComponent(workflowId)}/runs?limit=${limit}`,
  )
}

export function triggerRun(
  workflowId: string,
  payload: { inputs?: Record<string, unknown>; triggered_by?: string } = {},
): Promise<WorkflowRun> {
  return api<WorkflowRun>(`/workflow-definitions/${encodeURIComponent(workflowId)}/runs`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function exportDefinition(workflowId: string) {
  return api<{ format: string; format_version: number; name: string; definition: WorkflowDefinitionDoc; exported_at: number }>(
    `/workflow-definitions/${encodeURIComponent(workflowId)}/export`,
  )
}

export function importDefinition(payload: {
  name: string
  description?: string
  definition: WorkflowDefinitionDoc
}): Promise<WorkflowSummary> {
  return api<WorkflowSummary>('/workflow-definitions/import', {
    method: 'POST',
    body: JSON.stringify({
      format: 'ava-workflow-definition',
      format_version: 1,
      ...payload,
    }),
  })
}

/** Subscribe to the 5 WS event types. Returns a close handle. */
export function subscribeDefinitionEvents(
  onEvent: (msg: { type: string; ts: number; payload: Record<string, unknown> }) => void,
): () => void {
  const ws = new WebSocket(wsUrl('/workflow-definitions/ws'))
  ws.addEventListener('message', (event) => {
    try {
      const parsed = JSON.parse(event.data)
      onEvent(parsed)
    } catch {
      // ignore unparseable frames
    }
  })
  return () => {
    try {
      ws.close()
    } catch {
      // already closing
    }
  }
}
