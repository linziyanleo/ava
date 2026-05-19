/**
 * AVA-26 §F4-F6: schema-driven Agent config form.
 *
 * Renders a JSON Schema (draft-2020-12) form via primitive widgets:
 *   - object  → recursive section
 *   - array   → ArrayField (string array shorthand) or generic JSON
 *   - string  → text input (with `enum` → select, `format: password` → masked)
 *   - integer / number → number input with min/max bounds
 *   - boolean → ToggleSwitch
 *
 * Client-side validation goes through AJV with field-path error rows;
 * server-side 422 errors can be merged in via `serverErrors` prop so PUT
 * conflicts (e.g. `/codex/api_base`) light up the same fields.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import Ajv, { type ErrorObject } from 'ajv'
import addFormats from 'ajv-formats'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { ArrayField, ToggleSwitch } from '../../pages/ConfigPage/FormWidgets'

type JSONSchema = {
  $schema?: string
  type?: string | string[]
  title?: string
  description?: string
  enum?: unknown[]
  default?: unknown
  pattern?: string
  format?: string
  minimum?: number
  maximum?: number
  minLength?: number
  maxLength?: number
  required?: string[]
  properties?: Record<string, JSONSchema>
  items?: JSONSchema | JSONSchema[]
  additionalProperties?: boolean | JSONSchema
}

type ServerError = { path: string; message: string }

export interface AgentConfigFormProps {
  schema: JSONSchema
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  serverErrors?: ServerError[]
  readOnly?: boolean
}

const ajv = new Ajv({ allErrors: true, strict: false, useDefaults: false })
addFormats(ajv)

function formatErrorPath(error: ErrorObject): string {
  const path = error.instancePath || ''
  if (error.keyword === 'required') {
    const missing = (error.params as { missingProperty?: string }).missingProperty
    return missing ? `${path}/${missing}` : path
  }
  return path || '/'
}

function toErrorMessage(error: ErrorObject): string {
  return error.message ?? String(error.keyword)
}

function pickType(schema: JSONSchema): string {
  if (Array.isArray(schema.type)) {
    return schema.type.find((t) => t !== 'null') ?? 'string'
  }
  return schema.type ?? 'string'
}

function isStringArray(schema: JSONSchema): boolean {
  if (pickType(schema) !== 'array') return false
  const items = schema.items
  if (!items || Array.isArray(items)) return false
  return pickType(items) === 'string'
}

function getValueAt(value: Record<string, unknown>, path: string): unknown {
  if (!path || path === '/') return value
  const parts = path.split('/').filter(Boolean)
  let cursor: unknown = value
  for (const part of parts) {
    if (cursor && typeof cursor === 'object') {
      cursor = (cursor as Record<string, unknown>)[part]
    } else {
      return undefined
    }
  }
  return cursor
}

function setValueAt(
  value: Record<string, unknown>,
  path: string,
  next: unknown,
): Record<string, unknown> {
  if (!path || path === '/') {
    if (next && typeof next === 'object' && !Array.isArray(next)) {
      return next as Record<string, unknown>
    }
    return value
  }
  const parts = path.split('/').filter(Boolean)
  const out = { ...value }
  let cursor: Record<string, unknown> = out
  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = parts[i]
    const child = cursor[key]
    if (child && typeof child === 'object' && !Array.isArray(child)) {
      cursor[key] = { ...(child as Record<string, unknown>) }
    } else {
      cursor[key] = {}
    }
    cursor = cursor[key] as Record<string, unknown>
  }
  cursor[parts[parts.length - 1]] = next
  return out
}

interface FieldRendererProps {
  schema: JSONSchema
  fieldKey: string
  path: string
  value: unknown
  errors: Map<string, string[]>
  readOnly: boolean
  onChange: (path: string, next: unknown) => void
  required?: boolean
}

function FieldRenderer({
  schema,
  fieldKey,
  path,
  value,
  errors,
  readOnly,
  onChange,
  required,
}: FieldRendererProps) {
  const fieldType = pickType(schema)
  const fieldLabel = schema.title || fieldKey
  const fieldHint = schema.description
  const placeholder = schema.default !== undefined ? String(schema.default) : ''
  const localErrors = errors.get(path) || []
  const errorClass = localErrors.length > 0
    ? 'border-red-500 ring-1 ring-red-300'
    : 'border-zinc-300 dark:border-zinc-700'

  if (Array.isArray(schema.enum) && schema.enum.length > 0 && fieldType === 'string') {
    return (
      <FieldShell label={fieldLabel} hint={fieldHint} errors={localErrors} required={required}>
        <select
          className={`w-full rounded border bg-white px-2 py-1 text-sm dark:bg-zinc-900 ${errorClass}`}
          value={typeof value === 'string' ? value : ''}
          disabled={readOnly}
          onChange={(event) => onChange(path, event.target.value)}
        >
          {!required && <option value="">{`<empty>`}</option>}
          {schema.enum.map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
      </FieldShell>
    )
  }

  if (fieldType === 'boolean') {
    return (
      <FieldShell label={fieldLabel} hint={fieldHint} errors={localErrors} required={required}>
        <ToggleSwitch
          value={Boolean(value)}
          readOnly={readOnly}
          onChange={(next) => onChange(path, next)}
        />
      </FieldShell>
    )
  }

  if (fieldType === 'integer' || fieldType === 'number') {
    return (
      <FieldShell label={fieldLabel} hint={fieldHint} errors={localErrors} required={required}>
        <input
          type="number"
          className={`w-full rounded border bg-white px-2 py-1 text-sm dark:bg-zinc-900 ${errorClass}`}
          value={typeof value === 'number' ? value : value === undefined || value === null ? '' : Number(value as number)}
          placeholder={placeholder}
          disabled={readOnly}
          step={fieldType === 'integer' ? 1 : 'any'}
          min={schema.minimum}
          max={schema.maximum}
          onChange={(event) => {
            const raw = event.target.value
            if (raw === '') {
              onChange(path, undefined)
              return
            }
            const parsed = fieldType === 'integer' ? Number.parseInt(raw, 10) : Number.parseFloat(raw)
            onChange(path, Number.isNaN(parsed) ? raw : parsed)
          }}
        />
      </FieldShell>
    )
  }

  if (fieldType === 'array' && isStringArray(schema)) {
    return (
      <FieldShell label={fieldLabel} hint={fieldHint} errors={localErrors} required={required}>
        <ArrayField
          value={Array.isArray(value) ? (value as string[]) : []}
          readOnly={readOnly}
          onChange={(next) => onChange(path, next)}
        />
      </FieldShell>
    )
  }

  if (fieldType === 'array' || fieldType === 'object') {
    let serialised = ''
    try {
      serialised = JSON.stringify(value ?? (fieldType === 'array' ? [] : {}), null, 2)
    } catch {
      serialised = String(value ?? '')
    }
    return (
      <FieldShell
        label={fieldLabel}
        hint={fieldHint || `复杂 ${fieldType}：用 JSON 编辑`}
        errors={localErrors}
        required={required}
      >
        <textarea
          className={`h-32 w-full rounded border bg-white p-2 font-mono text-xs dark:bg-zinc-900 ${errorClass}`}
          disabled={readOnly}
          value={serialised}
          onChange={(event) => {
            const raw = event.target.value
            try {
              onChange(path, JSON.parse(raw))
            } catch {
              onChange(path, raw)
            }
          }}
        />
      </FieldShell>
    )
  }

  // string fallback
  const isPassword = schema.format === 'password' || /key|token|secret/i.test(fieldKey)
  return (
    <FieldShell label={fieldLabel} hint={fieldHint} errors={localErrors} required={required}>
      <input
        type={isPassword ? 'password' : 'text'}
        className={`w-full rounded border bg-white px-2 py-1 text-sm dark:bg-zinc-900 ${errorClass}`}
        value={typeof value === 'string' ? value : value === undefined || value === null ? '' : String(value)}
        placeholder={placeholder}
        disabled={readOnly}
        pattern={schema.pattern}
        minLength={schema.minLength}
        maxLength={schema.maxLength}
        onChange={(event) => onChange(path, event.target.value)}
      />
    </FieldShell>
  )
}

function FieldShell({
  label,
  hint,
  errors,
  required,
  children,
}: {
  label: string
  hint?: string
  errors: string[]
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="font-medium text-zinc-700 dark:text-zinc-200">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </span>
      {children}
      {hint && <span className="text-[11px] text-zinc-500">{hint}</span>}
      {errors.length > 0 && (
        <span className="text-[11px] text-red-600">{errors.join('; ')}</span>
      )}
    </label>
  )
}

function ObjectSection({
  schema,
  path,
  value,
  errors,
  readOnly,
  onChange,
  collapsible = false,
}: {
  schema: JSONSchema
  path: string
  value: Record<string, unknown>
  errors: Map<string, string[]>
  readOnly: boolean
  onChange: (path: string, next: unknown) => void
  collapsible?: boolean
}) {
  const [open, setOpen] = useState(true)
  const required = new Set(schema.required ?? [])
  const properties = schema.properties || {}

  const body = (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {Object.entries(properties).map(([key, sub]) => {
        const subPath = path === '/' || path === '' ? `/${key}` : `${path}/${key}`
        const subType = pickType(sub)
        if (subType === 'object' && sub.properties) {
          return (
            <div key={key} className="md:col-span-2">
              <ObjectSection
                schema={sub}
                path={subPath}
                value={(value?.[key] as Record<string, unknown>) || {}}
                errors={errors}
                readOnly={readOnly}
                onChange={onChange}
                collapsible
              />
            </div>
          )
        }
        return (
          <FieldRenderer
            key={key}
            schema={sub}
            fieldKey={key}
            path={subPath}
            value={value?.[key]}
            errors={errors}
            readOnly={readOnly}
            onChange={onChange}
            required={required.has(key)}
          />
        )
      })}
    </div>
  )

  if (!collapsible) return body

  return (
    <section className="rounded border border-zinc-200 dark:border-zinc-700">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium hover:bg-zinc-50 dark:hover:bg-zinc-800"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {schema.title || path.split('/').pop() || 'object'}
      </button>
      {open && <div className="px-3 pb-3">{body}</div>}
    </section>
  )
}

export function AgentConfigForm({
  schema,
  value,
  onChange,
  serverErrors,
  readOnly = false,
}: AgentConfigFormProps) {
  const [clientErrors, setClientErrors] = useState<Map<string, string[]>>(new Map())

  const validator = useMemo(() => {
    try {
      return ajv.compile(schema)
    } catch {
      return null
    }
  }, [schema])

  const validateNow = useCallback(
    (snapshot: Record<string, unknown>) => {
      if (!validator) return new Map<string, string[]>()
      const ok = validator(snapshot)
      if (ok) return new Map<string, string[]>()
      const map = new Map<string, string[]>()
      for (const error of validator.errors || []) {
        const key = formatErrorPath(error)
        const list = map.get(key) || []
        list.push(toErrorMessage(error))
        map.set(key, list)
      }
      return map
    },
    [validator],
  )

  useEffect(() => {
    setClientErrors(validateNow(value))
  }, [validateNow, value])

  const merged = useMemo(() => {
    const map = new Map<string, string[]>(clientErrors)
    for (const err of serverErrors || []) {
      const list = map.get(err.path) || []
      list.push(`server: ${err.message}`)
      map.set(err.path, list)
    }
    return map
  }, [clientErrors, serverErrors])

  const handleChange = useCallback(
    (path: string, nextValue: unknown) => {
      const updated = setValueAt(value, path, nextValue)
      onChange(updated)
    },
    [onChange, value],
  )

  return (
    <div className="space-y-4">
      <ObjectSection
        schema={schema}
        path="/"
        value={value}
        errors={merged}
        readOnly={readOnly}
        onChange={handleChange}
      />
      <details className="text-xs text-zinc-500">
        <summary className="cursor-pointer">校验状态</summary>
        {merged.size === 0 ? (
          <div className="mt-2 text-emerald-600">无错误</div>
        ) : (
          <ul className="mt-2 space-y-0.5">
            {[...merged.entries()].map(([path, msgs]) => (
              <li key={path} className="font-mono">
                <span className="text-zinc-700 dark:text-zinc-300">{path || '/'}</span>
                <span className="ml-1 text-red-600">{msgs.join('; ')}</span>
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  )
}

export default AgentConfigForm

export const __test__ = {
  setValueAt,
  getValueAt,
  formatErrorPath,
  pickType,
  isStringArray,
}
