import { useState, useRef, useCallback, useEffect, useMemo, type CSSProperties } from 'react'
import { Bot, FileText, Plus, Puzzle, Send, X } from 'lucide-react'
import { InputActionMenu } from './InputActionMenu'
import type { ChatCommand } from './commands'
import { findCommandsByPrefix } from './commands'
import type { ChatComposePayload, ChatFileUpload, DirectTaskSubmitParams, DirectTaskType } from './types'
import { api } from '../../api/client'

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

interface SkillSummary {
  name: string
  source?: string
  enabled?: boolean
  description?: string
}

const MAX_HEIGHT = 200
const MAX_ATTACHMENTS = 4
const SKILL_TRIGGER_TEMPLATE = '@skill_name'
const IMAGE_FILE_EXTENSION_RE = /\.(png|jpe?g|webp|gif|avif)$/i
const AGENT_MENTIONS = [
  { id: 'nanobot', label: 'Nanobot' },
  { id: 'codex', label: 'Codex' },
  { id: 'claude_code', label: 'Claude Code' },
]

function filterSkillSuggestions(skills: SkillSummary[], query: string): SkillSummary[] {
  return skills
    .filter((skill) => skill.enabled !== false && skill.name.toLowerCase().startsWith(query.toLowerCase()))
    .slice(0, 8)
}

function parseDirectTaskCommand(text: string): { taskType: DirectTaskType; prompt: string } | null {
  const match = text.match(/^\/(codex|claude-code|image-gen)(?:\s+([\s\S]*))?$/)
  if (!match) return null
  return {
    taskType: match[1] === 'claude-code' ? 'claude_code' : match[1] === 'image-gen' ? 'image_gen' : 'codex',
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

function isImageFile(file: File): boolean {
  return file.type.startsWith('image/') || IMAGE_FILE_EXTENSION_RE.test(file.name)
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
  const [skills, setSkills] = useState<SkillSummary[]>([])
  const [activeCommandIndex, setActiveCommandIndex] = useState(0)
  const [activeAgentIndex, setActiveAgentIndex] = useState(0)
  const [activeSkillIndex, setActiveSkillIndex] = useState(0)
  const [agentSuggestDismissedFor, setAgentSuggestDismissedFor] = useState('')
  const [skillSuggestDismissedFor, setSkillSuggestDismissedFor] = useState('')
  const [keyboardInset, setKeyboardInset] = useState(0)
  const [localSubmitting, setLocalSubmitting] = useState(false)
  const isComposingRef = useRef(false)
  const localSubmittingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const attachmentsRef = useRef<PendingAttachment[]>([])
  attachmentsRef.current = attachments

  const slashCommands = useMemo(
    () => (slashOpen ? findCommandsByPrefix(input) : []),
    [input, slashOpen],
  )
  const slashSuggestOpen = slashOpen && slashCommands.length > 0
  const skillTriggerQuery = useMemo(() => {
    const match = input.match(/^@([A-Za-z0-9_-]*)$/)
    return match ? match[1] : null
  }, [input])
  const skillSuggestions = useMemo(
    () => (skillTriggerQuery == null || slashSuggestOpen ? [] : filterSkillSuggestions(skills, skillTriggerQuery)),
    [skills, skillTriggerQuery, slashSuggestOpen],
  )
  const skillSuggestOpen = skillSuggestions.length > 0 && skillSuggestDismissedFor !== input
  const mentionQuery = useMemo(() => {
    if (input.startsWith('@')) return null
    const match = input.match(/(?:^|\s)@([A-Za-z0-9_-]*)$/)
    return match ? match[1].toLowerCase() : null
  }, [input])
  const agentSuggestions = useMemo(() => {
    if (mentionQuery == null || slashSuggestOpen) return []
    return AGENT_MENTIONS.filter((agent) => (
      agent.id.toLowerCase().startsWith(mentionQuery)
      || agent.label.toLowerCase().replace(/\s+/g, '_').startsWith(mentionQuery)
    ))
  }, [mentionQuery, slashSuggestOpen])
  const agentSuggestOpen = agentSuggestions.length > 0 && agentSuggestDismissedFor !== input
  const busy = sendDisabled || localSubmitting

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
    if (!isMobile || typeof window === 'undefined' || !window.visualViewport) {
      setKeyboardInset(0)
      return
    }
    const viewport = window.visualViewport
    const updateKeyboardInset = () => {
      const inset = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)
      setKeyboardInset(Math.round(inset))
    }
    updateKeyboardInset()
    viewport.addEventListener('resize', updateKeyboardInset)
    viewport.addEventListener('scroll', updateKeyboardInset)
    return () => {
      viewport.removeEventListener('resize', updateKeyboardInset)
      viewport.removeEventListener('scroll', updateKeyboardInset)
    }
  }, [isMobile])

  useEffect(() => {
    let disposed = false
    api<{ skills: SkillSummary[] }>('/skills/list')
      .then((response) => {
        if (!disposed) setSkills(response.skills || [])
      })
      .catch(() => {
        if (!disposed) setSkills([])
      })
    return () => {
      disposed = true
    }
  }, [])

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
    setSkillSuggestDismissedFor('')
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

  const insertAgentMention = useCallback((agentId: string) => {
    setInput((current) => current.replace(/(^|\s)@[A-Za-z0-9_-]*$/, `$1@${agentId} `))
    setActiveAgentIndex(0)
    requestAnimationFrame(() => {
      focusTextarea()
      adjustHeight()
    })
  }, [adjustHeight, focusTextarea])

  const insertSkillTrigger = useCallback((skillName: string) => {
    setInput(`@${skillName} `)
    setActiveSkillIndex(0)
    setSkillSuggestDismissedFor('')
    requestAnimationFrame(() => {
      focusTextarea()
      adjustHeight()
    })
  }, [adjustHeight, focusTextarea])

  const onSkillTriggerSelect = useCallback((skillName: string) => {
    insertSkillTrigger(skillName)
  }, [insertSkillTrigger])

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
        const isImage = isImageFile(normalized)
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

  const clearComposer = useCallback(() => {
    for (const attachment of attachmentsRef.current) {
      if (attachment.previewUrl) {
        URL.revokeObjectURL(attachment.previewUrl)
      }
    }
    setAttachments([])
    setInput('')
    setPasteError('')
    setMenuOpen(false)
    setSlashOpen(false)
    setSkillSuggestDismissedFor('')
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
        textareaRef.current.style.overflowY = 'hidden'
      }
    })
  }, [])

  const uploadImageGenReference = async (): Promise<string | null> => {
    if (attachments.length === 0) return null
    if (attachments.length > 1) {
      throw new Error('/image-gen 目前只支持 1 个 reference image')
    }
    const attachment = attachments[0]
    if (!attachment.isImage) {
      throw new Error('/image-gen reference 必须是图片文件')
    }
    const formData = new FormData()
    formData.append('files', attachment.file, attachment.file.name)
    const response = await api<{ uploads: ChatFileUpload[] }>('/chat/uploads', {
      method: 'POST',
      body: formData,
    })
    const upload = response.uploads?.[0]
    const referencePath = upload?.path || upload?.media_path
    if (!referencePath) {
      throw new Error('上传 reference image 后没有返回文件路径')
    }
    return referencePath
  }

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
    if ((!text && attachments.length === 0) || sendDisabled || localSubmittingRef.current) return
    const directTask = parseDirectTaskCommand(text)
    if (directTask) {
      if (!directTask.prompt) {
        setPasteError('请输入 direct task prompt')
        return
      }
      if (attachments.length > 0) {
        if (directTask.taskType !== 'image_gen') {
          setPasteError('Direct task commands do not support attachments')
          return
        }
      }
      localSubmittingRef.current = true
      setLocalSubmitting(true)
      try {
        const referenceImage = directTask.taskType === 'image_gen' ? await uploadImageGenReference() : null
        await onSubmitDirectTask({
          task_type: directTask.taskType,
          prompt: directTask.prompt,
          params: directTask.taskType === 'image_gen'
            ? (referenceImage ? { reference_image: referenceImage } : {})
            : { mode: 'standard' },
        })
        clearComposer()
      } catch (err) {
        console.error('Failed to submit direct task:', err)
        setPasteError(err instanceof Error ? err.message : 'Failed to submit direct task')
        return
      } finally {
        localSubmittingRef.current = false
        setLocalSubmitting(false)
      }
      return
    }
    localSubmittingRef.current = true
    setLocalSubmitting(true)
    try {
      await onSend({
        text,
        attachments: attachments.map((item) => item.file),
      })
      clearComposer()
    } catch (err) {
      console.error('Failed to send message:', err)
      return
    } finally {
      localSubmittingRef.current = false
      setLocalSubmitting(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const nextInput = e.target.value
    setInput(nextInput)
    setAgentSuggestDismissedFor('')
    setSkillSuggestDismissedFor('')
    setActiveSkillIndex(0)
    updateSlashSuggest(nextInput)
  }

  const handleRunCommand = useCallback(async (command: ChatCommand) => {
    if (busy && !command.runWhenBusy) {
      focusTextarea()
      return
    }

    try {
      if (command.run) {
        await command.run({
          send: onSend,
          stopCurrentTurn: onStopCurrentTurn,
          submitDirectTask: onSubmitDirectTask,
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
  }, [busy, closeActionMenus, focusTextarea, input, onSend, onStopCurrentTurn, onSubmitDirectTask])

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

    if (skillSuggestOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveSkillIndex((index) => (index + 1) % skillSuggestions.length)
        return
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveSkillIndex((index) => (index - 1 + skillSuggestions.length) % skillSuggestions.length)
        return
      }

      if (e.key === 'Tab' || e.key === 'Enter') {
        e.preventDefault()
        const skill = skillSuggestions[activeSkillIndex]
        if (skill) {
          onSkillTriggerSelect(skill.name)
        }
        return
      }

      if (e.key === 'Escape') {
        e.preventDefault()
        setSkillSuggestDismissedFor(input)
        setActiveSkillIndex(0)
        focusTextarea()
        return
      }
    }

    if (agentSuggestOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveAgentIndex((index) => (index + 1) % agentSuggestions.length)
        return
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveAgentIndex((index) => (index - 1 + agentSuggestions.length) % agentSuggestions.length)
        return
      }

      if (e.key === 'Tab' || e.key === 'Enter') {
        e.preventDefault()
        const agent = agentSuggestions[activeAgentIndex]
        if (agent) {
          insertAgentMention(agent.id)
        }
        return
      }

      if (e.key === 'Escape') {
        e.preventDefault()
        setAgentSuggestDismissedFor(input)
        setActiveAgentIndex(0)
        focusTextarea()
        return
      }
    }

    if (e.key === 'Enter' && e.shiftKey) {
      return
    }
  }

  const inputStyle = isMobile ? ({ '--keyboard-inset': `${keyboardInset}px` } as CSSProperties) : undefined

  return (
    <div
      style={inputStyle}
      className={`border-t border-[var(--border)] p-4 ${isMobile ? 'mobile-keyboard-safe' : 'pb-[calc(1rem+env(safe-area-inset-bottom,0px))]'}`}
    >
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
            sendDisabled={busy}
          />
        </div>
        <div className="relative flex-1">
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
            sendDisabled={busy}
            activeIndex={activeCommandIndex}
          />
          {skillSuggestOpen && (
            <div
              className="absolute bottom-full left-0 z-30 mb-2 w-full max-w-sm overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] shadow-xl"
              aria-label={`Insert ${SKILL_TRIGGER_TEMPLATE} trigger`}
            >
              {skillSuggestions.map((skill, index) => (
                <button
                  key={`${skill.source || 'skill'}:${skill.name}`}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    onSkillTriggerSelect(skill.name)
                  }}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
                    index === activeSkillIndex
                      ? 'bg-[var(--accent)]/10 text-[var(--accent)]'
                      : 'text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
                  }`}
                >
                  <Puzzle className="h-4 w-4" />
                  <span className="truncate">{skill.name}</span>
                  <span className="ml-auto shrink-0 font-mono text-xs text-[var(--text-secondary)]">@{skill.name}</span>
                </button>
              ))}
            </div>
          )}
          {agentSuggestOpen && (
            <div className="absolute bottom-full left-0 z-30 mb-2 w-full max-w-sm overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] shadow-xl">
              {agentSuggestions.map((agent, index) => (
                <button
                  key={agent.id}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    insertAgentMention(agent.id)
                  }}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
                    index === activeAgentIndex
                      ? 'bg-[var(--accent)]/10 text-[var(--accent)]'
                      : 'text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
                  }`}
                >
                  <Bot className="h-4 w-4" />
                  <span>{agent.label}</span>
                  <span className="ml-auto font-mono text-xs text-[var(--text-secondary)]">@{agent.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={() => { void handleSend() }}
          disabled={(!input.trim() && attachments.length === 0) || busy}
          className="flex h-12 w-16 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-40"
          title="Send (⌘+Enter)"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
