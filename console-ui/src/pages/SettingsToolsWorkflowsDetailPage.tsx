import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, Code, FormInput, Play, RefreshCw, Save, Trash2, X } from 'lucide-react'
import {
  deleteDefinition,
  getDefinition,
  listRuns,
  listVersions,
  patchDefinition,
  triggerRun,
  type WorkflowConflict,
  type WorkflowDefinitionDoc,
  type WorkflowRun,
  type WorkflowSummary,
  type WorkflowVersion,
} from '../api/workflow-definitions'
import {
  WorkflowGraph,
  type StepRuntimeStatus,
} from '../components/workflow/WorkflowGraph'

type EditorMode = 'form' | 'json'
type Tab = 'definition' | 'history' | 'runs'

interface ConflictModalState {
  conflict: WorkflowConflict
}

export default function SettingsToolsWorkflowsDetailPage() {
  const { workflowId = '' } = useParams<{ workflowId: string }>()
  const [tab, setTab] = useState<Tab>('definition')
  const [mode, setMode] = useState<EditorMode>('form')
  const [summary, setSummary] = useState<WorkflowSummary | null>(null)
  const [draft, setDraft] = useState<WorkflowDefinitionDoc | null>(null)
  const [jsonText, setJsonText] = useState<string>('')
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [conflict, setConflict] = useState<ConflictModalState | null>(null)
  const [versions, setVersions] = useState<WorkflowVersion[]>([])
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [running, setRunning] = useState(false)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)

  const runStatuses = useMemo<Record<string, StepRuntimeStatus>>(() => {
    const latest = runs[0]
    if (!latest) return {}
    if (latest.status === 'succeeded') {
      const out: Record<string, StepRuntimeStatus> = {}
      for (const step of draft?.steps || []) out[step.id] = 'succeeded'
      return out
    }
    if (latest.status === 'failed' || latest.status === 'cancelled') {
      const out: Record<string, StepRuntimeStatus> = {}
      for (const step of draft?.steps || []) out[step.id] = latest.status as StepRuntimeStatus
      return out
    }
    if (latest.status === 'running' || latest.status === 'pending') {
      const out: Record<string, StepRuntimeStatus> = {}
      for (const step of draft?.steps || []) out[step.id] = latest.status === 'running' ? 'running' : 'queued'
      return out
    }
    return {}
  }, [runs, draft])

  const loadAll = useCallback(async () => {
    setError(null)
    try {
      const [s, v, r] = await Promise.all([
        getDefinition(workflowId),
        listVersions(workflowId),
        listRuns(workflowId),
      ])
      setSummary(s)
      const def = s.current?.definition ?? null
      setDraft(def ?? { name: s.name, steps: [] })
      setJsonText(JSON.stringify(def, null, 2))
      setVersions(v.versions)
      setRuns(r.runs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'load failed')
    }
  }, [workflowId])

  useEffect(() => {
    if (!workflowId) return
    void loadAll()
  }, [workflowId, loadAll])

  const dirty = useMemo(() => {
    if (!summary?.current?.definition || !draft) return false
    return JSON.stringify(summary.current.definition) !== JSON.stringify(draft)
  }, [summary, draft])

  const switchToJson = useCallback(() => {
    setJsonText(JSON.stringify(draft, null, 2))
    setJsonError(null)
    setMode('json')
  }, [draft])

  const switchToForm = useCallback(() => {
    try {
      const parsed = JSON.parse(jsonText) as WorkflowDefinitionDoc
      setDraft(parsed)
      setJsonError(null)
      setMode('form')
    } catch (err) {
      setJsonError(err instanceof Error ? err.message : 'invalid JSON')
    }
  }, [jsonText])

  const onSave = useCallback(async () => {
    if (!summary || !draft) return
    setSaving(true)
    setError(null)
    let payloadDef = draft
    if (mode === 'json') {
      try {
        payloadDef = JSON.parse(jsonText) as WorkflowDefinitionDoc
      } catch (err) {
        setJsonError(err instanceof Error ? err.message : 'invalid JSON')
        setSaving(false)
        return
      }
    }
    const outcome = await patchDefinition(workflowId, {
      base_version: summary.current_version,
      definition: payloadDef,
      change_summary: 'manual edit',
    })
    setSaving(false)
    if (outcome.kind === 'ok') {
      setSummary(outcome.summary)
      const def = outcome.summary.current?.definition ?? null
      setDraft(def ?? draft)
      setJsonText(JSON.stringify(def, null, 2))
      setConflict(null)
      void loadAll()
      return
    }
    if (outcome.kind === 'conflict') {
      setConflict({ conflict: outcome.conflict })
      return
    }
    setError(outcome.message)
  }, [summary, draft, mode, jsonText, workflowId, loadAll])

  const onDelete = useCallback(async () => {
    if (!confirm('确认删除此 workflow？现有 runs 不会被删除。')) return
    try {
      await deleteDefinition(workflowId)
      window.location.href = '/settings/tools/workflows'
    } catch (err) {
      setError(err instanceof Error ? err.message : 'delete failed')
    }
  }, [workflowId])

  const onRun = useCallback(async () => {
    setRunning(true)
    setError(null)
    try {
      await triggerRun(workflowId, {})
      void loadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'run failed')
    } finally {
      setRunning(false)
    }
  }, [workflowId, loadAll])

  const stepsBlock = useMemo(() => draft?.steps ?? [], [draft])

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link
            to=".."
            className="inline-flex items-center text-sm text-zinc-500 hover:underline"
          >
            <ChevronLeft className="h-4 w-4" />
            Workflows
          </Link>
          <span className="text-zinc-400">/</span>
          <h1 className="text-xl font-semibold">{summary?.name ?? workflowId}</h1>
          {summary && (
            <span className="text-xs text-zinc-500">v{summary.current_version}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadAll()}
            className="inline-flex items-center gap-1 rounded border px-2 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <RefreshCw className="h-4 w-4" /> 刷新
          </button>
          <button
            type="button"
            onClick={() => void onRun()}
            disabled={running || !summary}
            className="inline-flex items-center gap-1 rounded bg-emerald-600 px-3 py-1 text-sm text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4" /> {running ? 'Running…' : 'Run'}
          </button>
          <button
            type="button"
            onClick={() => void onDelete()}
            className="inline-flex items-center gap-1 rounded border border-red-200 bg-white px-2 py-1 text-sm text-red-600 hover:bg-red-50 dark:border-red-900 dark:bg-zinc-900 dark:hover:bg-red-950"
          >
            <Trash2 className="h-4 w-4" /> 删除
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
      {conflict && (
        <ConflictModal
          state={conflict}
          onClose={() => setConflict(null)}
          onReload={() => {
            setConflict(null)
            void loadAll()
          }}
        />
      )}

      <nav className="flex gap-1 border-b">
        {(['definition', 'history', 'runs'] as Tab[]).map((value) => (
          <button
            type="button"
            key={value}
            className={`px-3 py-1 text-sm ${
              tab === value
                ? 'border-b-2 border-blue-500 font-medium'
                : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
            }`}
            onClick={() => setTab(value)}
          >
            {value === 'definition' ? 'Definition' : value === 'history' ? 'History' : 'Runs'}
          </button>
        ))}
      </nav>

      {tab === 'definition' && (
        <section className="flex flex-col gap-3">
          {draft && (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_280px]">
              <WorkflowGraph
                definition={draft}
                runStatuses={runStatuses}
                selectedStepId={selectedStepId}
                onStepClick={(id) => setSelectedStepId(id)}
              />
              {selectedStepId && (
                <StepDetailDrawer
                  stepId={selectedStepId}
                  definition={draft}
                  status={runStatuses[selectedStepId]}
                  onClose={() => setSelectedStepId(null)}
                />
              )}
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={switchToForm}
              className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-sm ${
                mode === 'form' ? 'bg-zinc-100 dark:bg-zinc-800' : ''
              }`}
            >
              <FormInput className="h-4 w-4" /> Form
            </button>
            <button
              type="button"
              onClick={switchToJson}
              className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-sm ${
                mode === 'json' ? 'bg-zinc-100 dark:bg-zinc-800' : ''
              }`}
            >
              <Code className="h-4 w-4" /> JSON
            </button>
            <span className="ml-auto text-xs text-zinc-500">
              {dirty ? '未保存改动' : '已同步'}
            </span>
            <button
              type="button"
              disabled={!dirty || saving}
              onClick={() => void onSave()}
              className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Save className="h-4 w-4" /> {saving ? '保存中…' : '保存 (PATCH)'}
            </button>
          </div>

          {mode === 'form' && draft && (
            <div className="flex flex-col gap-2">
              <FormField
                label="名称"
                value={draft.name}
                onChange={(v) => setDraft({ ...draft, name: v })}
              />
              <FormField
                label="描述"
                value={draft.description || ''}
                onChange={(v) => setDraft({ ...draft, description: v })}
              />
              <h3 className="mt-2 text-sm font-medium">Steps（v1 闭集 = agent_task）</h3>
              <ul className="flex flex-col gap-2">
                {stepsBlock.map((step, idx) => (
                  <li
                    key={`${step.id}-${idx}`}
                    className="rounded border p-2 text-xs dark:border-zinc-700"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono">{step.id}</span>
                      <span className="text-zinc-500">{step.kind} · {step.agent}</span>
                    </div>
                    <div className="mt-1 truncate text-zinc-600 dark:text-zinc-400">
                      {step.task.prompt_template}
                    </div>
                  </li>
                ))}
                {stepsBlock.length === 0 && (
                  <li className="rounded border p-2 text-xs text-zinc-500 dark:border-zinc-700">
                    没有 step。切到 JSON 模式手动添加；form 编辑器（KeyValue / multiselect）将在后续迭代中补齐。
                  </li>
                )}
              </ul>
            </div>
          )}

          {mode === 'json' && (
            <div className="flex flex-col gap-1">
              <textarea
                className="h-96 w-full rounded border p-2 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-950"
                value={jsonText}
                onChange={(event) => {
                  setJsonText(event.target.value)
                  setJsonError(null)
                }}
              />
              {jsonError && (
                <div className="rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
                  JSON 解析失败：{jsonError}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {tab === 'history' && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">版本历史</h2>
          <ul className="flex flex-col gap-1 text-xs">
            {versions.map((version) => (
              <li
                key={version.version}
                className="flex items-center justify-between rounded border px-3 py-2 dark:border-zinc-700"
              >
                <div>
                  <span className="font-mono">v{version.version}</span>
                  {version.is_current && (
                    <span className="ml-2 rounded bg-blue-100 px-1 text-[10px] text-blue-700">
                      current
                    </span>
                  )}
                  <span className="ml-3 text-zinc-500">{version.change_summary || '—'}</span>
                </div>
                <span className="text-zinc-500">{new Date(version.created_at * 1000).toLocaleString()}</span>
              </li>
            ))}
            {versions.length === 0 && (
              <li className="rounded border p-2 text-xs text-zinc-500 dark:border-zinc-700">
                没有 version 记录。
              </li>
            )}
          </ul>
        </section>
      )}

      {tab === 'runs' && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">运行记录</h2>
          <ul className="flex flex-col gap-1 text-xs">
            {runs.map((run) => (
              <li
                key={run.run_id}
                className="flex items-center justify-between rounded border px-3 py-2 dark:border-zinc-700"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono">{run.run_id.slice(0, 12)}</span>
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-[10px] dark:bg-zinc-800">
                    v{run.version}
                  </span>
                  <span className="text-zinc-500">{run.status}</span>
                </div>
                <span className="text-zinc-500">
                  {run.started_at ? new Date(run.started_at * 1000).toLocaleString() : 'pending'}
                </span>
              </li>
            ))}
            {runs.length === 0 && (
              <li className="rounded border p-2 text-xs text-zinc-500 dark:border-zinc-700">
                还没有运行记录。
              </li>
            )}
          </ul>
        </section>
      )}
    </div>
  )
}

function StepDetailDrawer({
  stepId,
  definition,
  status,
  onClose,
}: {
  stepId: string
  definition: WorkflowDefinitionDoc
  status?: StepRuntimeStatus
  onClose: () => void
}) {
  const step = definition.steps.find((s) => s.id === stepId)
  if (!step) return null
  return (
    <aside className="rounded border bg-white p-3 text-xs dark:border-zinc-700 dark:bg-zinc-900">
      <header className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold">{step.id}</h3>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          aria-label="关闭 step 详情"
        >
          <X className="h-4 w-4" />
        </button>
      </header>
      <dl className="space-y-1">
        <div className="flex justify-between">
          <dt className="text-zinc-500">agent</dt>
          <dd className="font-mono">{step.agent}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-zinc-500">kind</dt>
          <dd>{step.kind}</dd>
        </div>
        {status && (
          <div className="flex justify-between">
            <dt className="text-zinc-500">status</dt>
            <dd>{status}</dd>
          </div>
        )}
      </dl>
      <div className="mt-3">
        <div className="text-zinc-500">prompt_template</div>
        <pre className="mt-1 max-h-32 overflow-auto rounded bg-zinc-50 p-1 text-[10px] dark:bg-zinc-950">
          {step.task.prompt_template}
        </pre>
      </div>
      {step.inputs && Object.keys(step.inputs).length > 0 && (
        <div className="mt-3">
          <div className="text-zinc-500">inputs</div>
          <ul className="mt-1 space-y-0.5">
            {Object.entries(step.inputs).map(([key, expr]) => (
              <li key={key} className="font-mono">
                <span className="text-zinc-700 dark:text-zinc-300">{key}</span>
                <span className="mx-1 text-zinc-400">=</span>
                <span className="text-zinc-500">{expr}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {step.outputs && step.outputs.length > 0 && (
        <div className="mt-3">
          <div className="text-zinc-500">outputs</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {step.outputs.map((output) => (
              <span
                key={output}
                className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] dark:bg-zinc-800"
              >
                {output}
              </span>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}

function FormField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (next: string) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-zinc-500">{label}</span>
      <input
        className="rounded border px-2 py-1 dark:border-zinc-700 dark:bg-zinc-950"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

function ConflictModal({
  state,
  onClose,
  onReload,
}: {
  state: ConflictModalState
  onClose: () => void
  onReload: () => void
}) {
  const { conflict } = state
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded bg-white p-4 shadow-xl dark:bg-zinc-900">
        <h2 className="mb-1 text-base font-semibold text-amber-700">版本冲突</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          该 workflow 已被更新到 v{conflict.current_version}（你的 base_version 是 v{conflict.your_base_version}）。
        </p>
        <div className="mt-3 rounded bg-zinc-50 p-2 text-xs dark:bg-zinc-950">
          <div className="font-medium">改动概览</div>
          <div className="text-zinc-600 dark:text-zinc-400">
            顶层字段差异：{conflict.current_definition_diff.changed_top_level_keys.join(', ') || '无'}
          </div>
          <div className="text-zinc-600 dark:text-zinc-400">
            steps 数量：你的 {conflict.current_definition_diff.step_count_yours ?? '—'} / 服务端 {conflict.current_definition_diff.step_count_current ?? '—'}
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border px-3 py-1 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onReload}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
          >
            查看最新版本
          </button>
        </div>
      </div>
    </div>
  )
}
