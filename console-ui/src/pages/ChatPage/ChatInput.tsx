import { useState, useRef, useCallback, useEffect } from 'react'
import { Send, X } from 'lucide-react'
import type { ChatComposePayload } from './types'

interface ChatInputProps {
  onSend: (payload: ChatComposePayload) => Promise<void> | void
  disabled: boolean
  isMobile?: boolean
}

interface PendingAttachment {
  id: string
  file: File
  previewUrl: string
}

const MAX_HEIGHT = 200
const MAX_ATTACHMENTS = 4

function extensionForMime(mime: string): string {
  switch (mime) {
    case 'image/png':
      return 'png'
    case 'image/jpeg':
      return 'jpg'
    case 'image/webp':
      return 'webp'
    case 'image/gif':
      return 'gif'
    default:
      return 'png'
  }
}

function normalizePastedFile(file: File, index: number): File {
  if (file.name) return file
  const extension = extensionForMime(file.type)
  return new File([file], `pasted-image-${Date.now()}-${index}.${extension}`, { type: file.type })
}

export function ChatInput({ onSend, disabled, isMobile }: ChatInputProps) {
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [pasteError, setPasteError] = useState('')
  const isComposingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const attachmentsRef = useRef<PendingAttachment[]>([])
  attachmentsRef.current = attachments

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden'
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [input, adjustHeight])

  useEffect(() => {
    return () => {
      for (const attachment of attachmentsRef.current) {
        URL.revokeObjectURL(attachment.previewUrl)
      }
    }
  }, [])

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const target = prev.find((item) => item.id === id)
      if (target) {
        URL.revokeObjectURL(target.previewUrl)
      }
      return prev.filter((item) => item.id !== id)
    })
  }

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(e.clipboardData?.items || [])
    const imageItems = items.filter((item) => item.type.startsWith('image/'))
    if (imageItems.length === 0) return

    e.preventDefault()
    setPasteError('')

    setAttachments((prev) => {
      const remainingSlots = Math.max(MAX_ATTACHMENTS - prev.length, 0)
      if (remainingSlots === 0) {
        setPasteError(`最多支持 ${MAX_ATTACHMENTS} 张图片`)
        return prev
      }

      const next = imageItems
        .slice(0, remainingSlots)
        .map((item) => item.getAsFile())
        .filter((file): file is File => file instanceof File)
        .map((file, index) => {
          const normalized = normalizePastedFile(file, index)
          return {
            id: `${Date.now()}-${index}-${normalized.name}`,
            file: normalized,
            previewUrl: URL.createObjectURL(normalized),
          }
        })

      if (imageItems.length > remainingSlots) {
        setPasteError(`最多支持 ${MAX_ATTACHMENTS} 张图片`)
      }

      return [...prev, ...next]
    })
  }

  const handleSend = async () => {
    const text = input.trim()
    if ((!text && attachments.length === 0) || disabled) return
    try {
      await onSend({
        text,
        attachments: attachments.map((item) => item.file),
      })
      for (const attachment of attachments) {
        URL.revokeObjectURL(attachment.previewUrl)
      }
      setAttachments([])
      setInput('')
      setPasteError('')
    } catch (err) {
      console.error('Failed to send message:', err)
      return
    }

    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
        textareaRef.current.style.overflowY = 'hidden'
      }
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (isComposingRef.current) return

    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      void handleSend()
      return
    }

    if (e.key === 'Enter' && e.shiftKey) {
      return
    }
  }

  return (
    <div className={`p-4 border-t border-[var(--border)] ${isMobile ? 'pb-3' : 'pb-[calc(1rem+env(safe-area-inset-bottom,0px))]'}`}>
      {attachments.length > 0 && (
        <div className="mb-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] p-3">
          <div className="flex gap-2 overflow-x-auto pb-1">
            {attachments.map((attachment) => (
              <div
                key={attachment.id}
                className="relative shrink-0 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-tertiary)]"
              >
                <img
                  src={attachment.previewUrl}
                  alt="Pasted attachment"
                  className="block h-[120px] w-[120px] object-cover"
                />
                <button
                  onClick={() => removeAttachment(attachment.id)}
                  disabled={disabled}
                  className="absolute right-2 top-2 rounded-full bg-black/65 p-1 text-white hover:bg-[var(--danger)] disabled:opacity-40"
                  title="移除图片"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {pasteError && (
        <div className="mb-2 text-xs text-[var(--danger)]">{pasteError}</div>
      )}

      <div className="flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={input}
          rows={1}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onCompositionStart={() => { isComposingRef.current = true }}
          onCompositionEnd={() => { isComposingRef.current = false }}
          placeholder="Type a message or paste images... (⌘+Enter to send)"
          disabled={disabled}
          className="flex-1 px-4 py-2.5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] disabled:opacity-50 resize-none leading-normal"
          style={{ maxHeight: `${MAX_HEIGHT}px` }}
        />
        <button
          onClick={() => { void handleSend() }}
          disabled={(!input.trim() && attachments.length === 0) || disabled}
          className="px-4 py-2.5 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white disabled:opacity-40 transition-colors shrink-0"
          title="Send (⌘+Enter)"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
