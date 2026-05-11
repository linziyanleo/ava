import { useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, Smartphone } from 'lucide-react'
import { pairLanDevice } from '../api/lan-access'

export default function MobilePairPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const initialPin = params.get('pin') || ''
  const [pin, setPin] = useState(initialPin)
  const [deviceName, setDeviceName] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const lanUrl = useMemo(() => `${window.location.protocol}//${window.location.host}`, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setMessage('')
    setSubmitting(true)
    try {
      await pairLanDevice(pin, deviceName || navigator.userAgent.split(' ')[0] || 'Mobile device')
      navigate('/', { replace: true })
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Pairing failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen bg-[var(--bg-primary)] px-4 py-8 text-[var(--text-primary)]">
      <section className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-md flex-col justify-center">
        <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)]">
          <Smartphone className="h-6 w-6 text-[var(--accent)]" />
        </div>
        <h1 className="text-2xl font-semibold">Pair Ava Console</h1>
        <p className="mt-2 break-all font-mono text-sm text-[var(--text-secondary)]">{lanUrl}</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm text-[var(--text-secondary)]">PIN</span>
            <input
              value={pin}
              onChange={(event) => setPin(event.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-3 font-mono text-2xl outline-none focus:border-[var(--accent)]"
              required
              minLength={6}
              maxLength={6}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm text-[var(--text-secondary)]">Device name</span>
            <input
              value={deviceName}
              onChange={(event) => setDeviceName(event.target.value)}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-3 outline-none focus:border-[var(--accent)]"
              placeholder="Phone"
            />
          </label>
          <button
            type="submit"
            disabled={submitting || pin.length !== 6}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-[var(--accent)] px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Pair
          </button>
        </form>
        {message && <div className="mt-4 text-sm text-red-400">{message}</div>}
      </section>
    </main>
  )
}
