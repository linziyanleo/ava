import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FilePlus, FileUp, RefreshCw, Workflow } from 'lucide-react'
import {
  createDefinition,
  importDefinition,
  listDefinitions,
  listTemplates,
  subscribeDefinitionEvents,
  type WorkflowSummary,
  type WorkflowTemplateRow,
} from '../api/workflow-definitions'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

export default function SettingsToolsWorkflowsPage() {
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [templates, setTemplates] = useState<WorkflowTemplateRow[]>([])
  const [showTemplates, setShowTemplates] = useState(false)
  const [importJson, setImportJson] = useState<string>('')
  const [importing, setImporting] = useState(false)

  const refresh = useCallback(async () => {
    setLoadState('loading')
    setError(null)
    try {
      const [defs, tpls] = await Promise.all([listDefinitions(), listTemplates()])
      setWorkflows(defs.workflows)
      setTemplates(tpls.templates)
      setLoadState('ready')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'load failed')
      setLoadState('error')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const unsub = subscribeDefinitionEvents((msg) => {
      if (
        msg.type === 'workflow.updated' ||
        msg.type === 'workflow.deleted' ||
        msg.type === 'workflow.run.created'
      ) {
        void refresh()
      }
    })
    return unsub
  }, [refresh])

  const onCreateFromTemplate = useCallback(
    async (tpl: WorkflowTemplateRow) => {
      try {
        await createDefinition({
          name: `${tpl.name} (copy)`,
          description: tpl.description,
          definition: tpl.definition,
          change_summary: `from template ${tpl.id}`,
        })
        setShowTemplates(false)
        void refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'create failed')
      }
    },
    [refresh],
  )

  const onImport = useCallback(async () => {
    setImporting(true)
    setError(null)
    try {
      const parsed = JSON.parse(importJson) as {
        name?: string
        description?: string
        definition?: unknown
      }
      if (!parsed.definition || typeof parsed.definition !== 'object') {
        throw new Error('JSON 缺少 `definition` 字段')
      }
      await importDefinition({
        name: parsed.name || 'imported workflow',
        description: parsed.description || '',
        definition: parsed.definition as Parameters<typeof importDefinition>[0]['definition'],
      })
      setImportJson('')
      void refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'import failed')
    } finally {
      setImporting(false)
    }
  }, [importJson, refresh])

  const sorted = useMemo(
    () =>
      [...workflows].sort((a, b) => b.updated_at - a.updated_at),
    [workflows],
  )

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Workflow className="h-5 w-5 text-zinc-500" />
          <h1 className="text-xl font-semibold">Workflows</h1>
          <span className="text-xs text-zinc-500">
            {loadState === 'ready' ? `${workflows.length} 项` : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex items-center gap-1 rounded border px-2 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="刷新"
          >
            <RefreshCw className="h-4 w-4" />
            刷新
          </button>
          <button
            type="button"
            onClick={() => setShowTemplates((v) => !v)}
            className="inline-flex items-center gap-1 rounded border px-2 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <FilePlus className="h-4 w-4" />
            New from template
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {showTemplates && (
        <section className="rounded border bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-2 text-sm font-medium">内置模板</h2>
          <ul className="flex flex-col gap-2">
            {templates.map((tpl) => (
              <li
                key={tpl.id}
                className="flex items-center justify-between rounded border px-3 py-2 text-sm dark:border-zinc-700"
              >
                <div>
                  <div className="font-medium">{tpl.name}</div>
                  <div className="text-xs text-zinc-500">{tpl.description}</div>
                </div>
                <button
                  type="button"
                  onClick={() => void onCreateFromTemplate(tpl)}
                  className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700"
                >
                  + New
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <details className="rounded border bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
        <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
          <FileUp className="h-4 w-4" />
          Import JSON
        </summary>
        <div className="mt-2 flex flex-col gap-2">
          <textarea
            className="h-40 w-full rounded border p-2 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-950"
            placeholder='{"format":"ava-workflow-definition","format_version":1,"name":"...","definition":{...}}'
            value={importJson}
            onChange={(event) => setImportJson(event.target.value)}
          />
          <button
            type="button"
            onClick={() => void onImport()}
            disabled={importing || !importJson.trim()}
            className="self-start rounded bg-zinc-700 px-3 py-1 text-sm text-white hover:bg-zinc-800 disabled:opacity-50"
          >
            导入
          </button>
        </div>
      </details>

      {loadState === 'loading' && (
        <div className="rounded border p-3 text-sm text-zinc-500">加载中…</div>
      )}

      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sorted.map((wf) => (
          <li
            key={wf.workflow_id}
            className="rounded border bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900"
          >
            <Link
              to={wf.workflow_id}
              className="block hover:underline"
            >
              <div className="font-medium">{wf.name}</div>
              <div className="text-xs text-zinc-500">v{wf.current_version}</div>
              {wf.description && (
                <div className="mt-1 line-clamp-2 text-xs text-zinc-600">
                  {wf.description}
                </div>
              )}
              <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
                <span>updated {new Date(wf.updated_at * 1000).toLocaleString()}</span>
              </div>
            </Link>
          </li>
        ))}
        {loadState === 'ready' && sorted.length === 0 && (
          <li className="col-span-full rounded border p-3 text-sm text-zinc-500">
            还没有 workflow。试试 [+ New from template] 或 [Import JSON]。
          </li>
        )}
      </ul>
    </div>
  )
}
