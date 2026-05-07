import { useState } from 'react'
import { Image as ImageIcon, Send, X } from 'lucide-react'

interface ImageGenPanelProps {
  open: boolean
  submitting?: boolean
  onClose: () => void
  onSubmit: (prompt: string, params: { reference_image?: string }) => Promise<void> | void
}

export function ImageGenPanel({ open, submitting = false, onClose, onSubmit }: ImageGenPanelProps) {
  const [promptValue, setPromptValue] = useState('')
  const [referenceImageValue, setReferenceImageValue] = useState('')

  if (!open) return null

  return (
    <div className="absolute bottom-full left-0 right-0 z-50 mb-2 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] p-3 shadow-xl">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-fuchsia-500/10 text-fuchsia-500">
          <ImageIcon className="h-4 w-4" />
        </span>
        <span className="text-sm font-medium text-[var(--text-primary)]">Image Gen</span>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto rounded-md p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          title="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault()
          const prompt = promptValue.trim()
          if (!prompt || submitting) return
          const reference_image = referenceImageValue.trim()
          void onSubmit(prompt, reference_image ? { reference_image } : {})
        }}
      >
        <textarea
          rows={3}
          value={promptValue}
          onChange={(event) => setPromptValue(event.currentTarget.value)}
          placeholder="Prompt"
          className="block w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
        />
        <input
          type="text"
          value={referenceImageValue}
          onChange={(event) => setReferenceImageValue(event.currentTarget.value)}
          placeholder="Reference image path"
          className="block h-10 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
        />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded-lg border border-[var(--border)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-[var(--accent)] px-3 text-sm text-white hover:bg-[var(--accent-hover)] disabled:opacity-40"
          >
            <Send className="h-3.5 w-3.5" />
            Submit
          </button>
        </div>
      </form>
    </div>
  )
}
