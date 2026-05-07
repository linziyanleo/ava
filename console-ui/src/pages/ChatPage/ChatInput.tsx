import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { FileText, Plus, Send, X } from 'lucide-react'
import { InputActionMenu } from './InputActionMenu'
import type { ChatCommand } from './commands'
import { findCommandsByPrefix } from './commands'
import { ImageGenPanel } from './ImageGenPanel'
import type { ChatComposePayload, DirectTaskSubmitParams, DirectTaskType } from './types'

interface ChatInputProps {
  onSend: (payload: ChatComposePayload) => Promise<void> | void
  onStopCurrentTurn: () => Promise<void> | void
  onSubmitDirectTask: (params: DirectTaskSubmitParams) => Promise<void> | void
  sendDisabled: boolean
  isMobile?: boolean
}

interface PendingAttachment {
  id: string
  file: File
  previewUrl: string | null
  isImage: boolean
}

const MAX_HEIGHT = 200
const MAX_ATTACHMENTS = 4

function parseDirectTaskCommand(text: string): { taskType: DirectTaskType; prompt: string } | null {
  const match = text.match(/^\/(codex|claude-code)(?:\s+([\s\S]*))?$/)
  if (!match) return null
  return {
    taskType: match[1] === 'claude-code' ? 'claude_code' : 'codex',
    prompt: (match[2] || '').trim(),
  }
}

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
    case 'application/pdf':
      return 'pdf'
    case 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
      return 'docx'
    case 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
      return 'xlsx'
    case 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
      return 'pptx'
    case 'text/plain':
      return 'txt'
    case 'text/markdown':
      return 'md'
    case 'text/csv':
      return 'csv'
    case 'application/json':
      return 'json'
    default:
      return 'bin'
  }
}

function normalizeAttachmentFile(file: File, index: number, fallbackNamePrefix: string): File {
  if (file.name) return file
  const extension = extensionForMime(file.type)
  return new File([file], `${fallbackNamePrefix}-${Date.now()}-${index}.${extension}`, { type: file.type })
}

function formatFileSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

export function ChatInput({ onSend, onStopCurrentTurn, onSubmitDirectTask, sendDisabled, isMobile }: ChatInputProps) {
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [pasteError, setPasteError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [slashOpen, setSlashOpen] = useState(false)
  const [imageGenOpen, setImageGenOpen] = useState(false)
  const [activeCommandIndex, setActiveCommandIndex] = useState(0)
  const isComposingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const attachmentsRef = useRef<PendingAttachment[]>([])
  attachmentsRef.current = attachments

  const slashCommands = useMemo(
    () => (slashOpen ? findCommandsByPrefix(input) : []),
    [input, slashOpen],
  )
  const slashSuggestOpen = slashOpen && slashCommands.length > 0

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
        if (attachment.previewUrl) {
          URL.revokeObjectURL(attachment.previewUrl)
        }
      }
    }
  }, [])

  const focusTextarea = useCallback(() => {
    requestAnimationFrame(() => {
      textareaRef.current?.focus()
    })
  }, [])

  const closeActionMenus = useCallback(() => {
    setMenuOpen(false)
    setSlashOpen(false)
    setImageGenOpen(false)
    focusTextarea()
  }, [focusTextarea])

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const target = prev.find((item) => item.id === id)
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl)
      }
      return prev.filter((item) => item.id !== id)
    })
  }

  const updateSlashSuggest = useCallback((value: string) => {
    const matches = !isComposingRef.current && value.startsWith('/') ? findCommandsByPrefix(value) : []
    setSlashOpen(matches.length > 0)
    setActiveCommandIndex(0)
  }, [])

  const addAttachmentsFromFiles = useCallback((files: File[], fallbackNamePrefix: string) => {
    if (files.length === 0) return

    setPasteError('')
    setAttachments((prev) => {
      const remainingSlots = Math.max(MAX_ATTACHMENTS - prev.length, 0)
      if (remainingSlots === 0) {
        setPasteError(`最多支持 ${MAX_ATTACHMENTS} 个文件`)
        return prev
      }

      const next = files.slice(0, remainingSlots).map((file, index) => {
        const normalized = normalizeAttachmentFile(file, index, fallbackNamePrefix)
        const isImage = normalized.type.startsWith('image/')
        return {
          id: `${Date.now()}-${index}-${normalized.name}`,
          file: normalized,
          previewUrl: isImage ? URL.createObjectURL(normalized) : null,
          isImage,
        }
      })

      if (files.length > remainingSlots) {
        setPasteError(`最多支持 ${MAX_ATTACHMENTS} 个文件`)
      }

      return [...prev, ...next]
    })
  }, [])

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    let pastedFiles = Array.from(e.clipboardData?.files || [])
    if (pastedFiles.length === 0) {
      pastedFiles = Array.from(e.clipboardData?.items || [])
        .filter((item) => item.kind === 'file')
        .map((item) => item.getAsFile())
        .filter((file): file is File => file instanceof File)
    }
    if (pastedFiles.length === 0) return

    e.preventDefault()
    addAttachmentsFromFiles(pastedFiles, 'pasted-file')
  }

  const handleSend = async () => {
    const text = input.trim()
    if ((!text && attachments.length === 0) || sendDisabled) return
    const directTask = parseDirectTaskCommand(text)
    if (directTask) {
      if (!directTask.prompt) {
        setPasteError('请输入 direct task prompt')
        return
      }
      if (attachments.length > 0) {
        setPasteError('Direct task commands do not support attachments')
        return
      }
      try {
        await onSubmitDirectTask({
          task_type: directTask.taskType,
          prompt: directTask.prompt,
          params: { mode: 'standard' },
        })
        setInput('')
        setPasteError('')
        setMenuOpen(false)
        setSlashOpen(false)
      } catch (err) {
        console.error('Failed to submit direct task:', err)
        return
      }
      return
    }
    try {
      await onSend({
        text,
        attachments: attachments.map((item) => item.file),
      })
      for (const attachment of attachments) {
        if (attachment.previewUrl) {
          URL.revokeObjectURL(attachment.previewUrl)
        }
      }
      setAttachments([])
      setInput('')
      setPasteError('')
      setMenuOpen(false)
      setSlashOpen(false)
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

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const nextInput = e.target.value
    setInput(nextInput)
    updateSlashSuggest(nextInput)
  }

  const handleRunCommand = useCallback(async (command: ChatCommand) => {
    if (sendDisabled && !command.runWhenBusy) {
      focusTextarea()
      return
    }

    try {
      if (command.run) {
        await command.run({
          send: onSend,
          stopCurrentTurn: onStopCurrentTurn,
          submitDirectTask: onSubmitDirectTask,
          openImageGenPanel: () => setImageGenOpen(true),
          setInput,
          closeMenu: closeActionMenus,
        })
      } else if (command.populateOnly) {
        setInput(`${command.id} `)
      } else {
        await onSend({ text: command.id, attachments: [] })
        if (input.startsWith('/')) {
          setInput('')
        }
      }
      setPasteError('')
      setMenuOpen(false)
      setSlashOpen(false)
    } catch (err) {
      console.error('Failed to run chat command:', err)
    } finally {
      focusTextarea()
    }
  }, [closeActionMenus, focusTextarea, input, onSend, onStopCurrentTurn, onSubmitDirectTask, sendDisabled])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (isComposingRef.current) return

    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      void handleSend()
      return
    }

    if (slashSuggestOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveCommandIndex((index) => (index + 1) % slashCommands.length)
        return
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveCommandIndex((index) => (index - 1 + slashCommands.length) % slashCommands.length)
        return
      }

      if (e.key === 'Tab' || e.key === 'Enter') {
        e.preventDefault()
        const command = slashCommands[activeCommandIndex]
        if (command) {
          void handleRunCommand(command)
        }
        return
      }

      if (e.key === 'Escape') {
        e.preventDefault()
        setSlashOpen(false)
        focusTextarea()
        return
      }
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
                {attachment.isImage && attachment.previewUrl ? (
                  <img
                    src={attachment.previewUrl}
                    alt={attachment.file.name || 'Attachment'}
                    className="block h-[120px] w-[120px] object-cover"
                  />
                ) : (
                  <div className="flex h-[120px] w-[220px] items-center gap-3 p-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
                      <FileText className="h-5 w-5" />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-[var(--text-primary)]">{attachment.file.name}</span>
                      <span className="block text-xs text-[var(--text-secondary)]">{formatFileSize(attachment.file.size)}</span>
                    </span>
                  </div>
                )}
                <button
                  onClick={() => removeAttachment(attachment.id)}
                  className="absolute right-2 top-2 rounded-full bg-black/65 p-1 text-white hover:bg-[var(--danger)]"
                  title="移除文件"
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
        <div className="relative shrink-0">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="flex h-12 w-12 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] transition-colors hover:border-[var(--accent)] hover:text-[var(--text-primary)]"
            title="添加文件或命令"
          >
            <Plus className="h-4 w-4" />
          </button>
          <InputActionMenu
            open={menuOpen}
            onClose={closeActionMenus}
            onPickFiles={(files) => addAttachmentsFromFiles(files, 'picked-file')}
            onRunCommand={(command) => { void handleRunCommand(command) }}
            isMobile={isMobile}
            anchorRef={menuButtonRef}
            variant="menu"
            sendDisabled={sendDisabled}
          />
        </div>
        <div className="relative flex-1">
          <ImageGenPanel
            open={imageGenOpen}
            submitting={sendDisabled}
            onClose={() => {
              setImageGenOpen(false)
              focusTextarea()
            }}
            onSubmit={async (prompt, params) => {
              try {
                await onSubmitDirectTask({
                  task_type: 'image_gen',
                  prompt,
                  params,
                })
                setImageGenOpen(false)
                setPasteError('')
                focusTextarea()
              } catch (err) {
                console.error('Failed to submit image generation task:', err)
              }
            }}
          />
          <textarea
            ref={textareaRef}
            value={input}
            rows={1}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            onCompositionStart={() => { isComposingRef.current = true }}
            onCompositionEnd={() => {
              isComposingRef.current = false
              updateSlashSuggest(input)
            }}
            placeholder="Type a message or attach files... (⌘+Enter to send)"
            className="block min-h-12 w-full px-4 py-3 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border)] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] resize-none leading-6"
            style={{ maxHeight: `${MAX_HEIGHT}px` }}
          />
          <InputActionMenu
            open={slashSuggestOpen}
            onClose={closeActionMenus}
            onPickFiles={(files) => addAttachmentsFromFiles(files, 'picked-file')}
            onRunCommand={(command) => { void handleRunCommand(command) }}
            isMobile={isMobile}
            anchorRef={textareaRef}
            filterPrefix={input}
            variant="slash-suggest"
            sendDisabled={sendDisabled}
            activeIndex={activeCommandIndex}
          />
        </div>
        <button
          onClick={() => { void handleSend() }}
          disabled={(!input.trim() && attachments.length === 0) || sendDisabled}
          className="flex h-12 w-16 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-40"
          title="Send (⌘+Enter)"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
