import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../stores/auth'

export default function LoginPage() {
  const [passphrase, setPassphrase] = useState('')
  const [revealed, setRevealed] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(passphrase)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: 'var(--ava-bg-canvas)' }}
    >
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center w-16 h-16 mb-4"
            style={{
              borderRadius: 'var(--ava-radius-xl)',
              background: 'var(--ava-primary-soft)',
              border: '1px solid var(--ava-primary-border)',
            }}
          >
            <Bot className="w-8 h-8" style={{ color: 'var(--ava-primary)' }} />
          </div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--ava-text)' }}>
            Ava
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--ava-text-muted)' }}>
            Enter your passphrase to continue
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="p-6 space-y-4"
          style={{
            background: 'var(--ava-bg-surface)',
            border: '1px solid var(--ava-border)',
            borderRadius: 'var(--ava-radius-lg)',
          }}
        >
          {error && (
            <div
              className="p-3 text-sm"
              style={{
                background: 'var(--ava-danger-soft)',
                border: '1px solid var(--ava-danger-border)',
                color: 'var(--ava-danger)',
                borderRadius: 'var(--ava-radius-md)',
              }}
              role="alert"
            >
              {error}
            </div>
          )}

          <div>
            <label
              htmlFor="passphrase"
              className="block text-sm font-medium mb-1.5"
              style={{ color: 'var(--ava-text-muted)' }}
            >
              Passphrase
            </label>
            <div className="relative">
              <input
                id="passphrase"
                type={revealed ? 'text' : 'password'}
                value={passphrase}
                onChange={e => setPassphrase(e.target.value)}
                className="w-full px-3 py-2.5 pr-10 focus:outline-none"
                style={{
                  background: 'var(--ava-bg-canvas)',
                  border: '1px solid var(--ava-border)',
                  borderRadius: 'var(--ava-radius-md)',
                  color: 'var(--ava-text)',
                }}
                onFocus={e => {
                  e.currentTarget.style.borderColor = 'var(--ava-primary-border)'
                }}
                onBlur={e => {
                  e.currentTarget.style.borderColor = 'var(--ava-border)'
                }}
                autoFocus
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                onClick={() => setRevealed(prev => !prev)}
                className="absolute right-3 top-1/2 -translate-y-1/2"
                aria-label={revealed ? 'Hide passphrase' : 'Show passphrase'}
                style={{ color: 'var(--ava-text-muted)' }}
              >
                {revealed ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || passphrase.length === 0}
            className="w-full py-2.5 font-medium transition-colors disabled:cursor-not-allowed"
            style={{
              background: 'var(--ava-primary)',
              color: 'var(--ava-bg-canvas)',
              borderRadius: 'var(--ava-radius-md)',
              opacity: loading || passphrase.length === 0 ? 0.55 : 1,
            }}
            onMouseEnter={e => {
              if (!loading && passphrase.length > 0) {
                e.currentTarget.style.background = 'var(--ava-primary-hover)'
              }
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'var(--ava-primary)'
            }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
