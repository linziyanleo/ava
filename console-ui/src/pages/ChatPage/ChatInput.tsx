import { useState, useRef, useCallback, useEffect } from 'react'
import { Send } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled: boolean
  isMobile?: boolean
}

const MAX_HEIGHT = 200

export function ChatInput({ onSend, disabled, isMobile }: ChatInputProps) {
  const [input, setInput] = useState('')
  const isComposingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [input, adjustHeight])

  const handleSend = () => {
    const msg = input.trim()
    if (!msg || disabled) return
    try {
      setInput('')
      onSend(msg)
    } catch (err) {
      console.error('Failed to send message:', err)
    }
    // Reset height after clearing
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (isComposingRef.current) return

    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSend()
      return
    }

    // Shift+Enter: allow default newline behavior
    if (e.key === 'Enter' && e.shiftKey) {
      return
    }

    // Plain Enter: insert newline (do nothing, textarea default)
  }

  return (
    <div className={`p-4 border-t border-[var(--border)] ${isMobile ? 'pb-3' : 'pb-[calc(1rem+env(safe-area-inset-bottom,0px))]'}`}>
      <div className="flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={input}
          rows={1}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => { isComposingRef.current = true }}
          onCompositionEnd={() => { isComposingRef.current = false }}
          placeholder="Type a message... (⌘+Enter to send)"
          disabled={disabled}
          className="flex-1 px-4 py-2.5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] disabled:opacity-50 resize-none overflow-y-auto leading-normal"
          style={{ maxHeight: `${MAX_HEIGHT}px` }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          className="px-4 py-2.5 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white disabled:opacity-40 transition-colors shrink-0"
          title="Send (⌘+Enter)"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
