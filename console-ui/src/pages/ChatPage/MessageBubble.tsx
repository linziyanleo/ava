import { Copy, Check, Brain, ChevronDown, ChevronRight, Info, Eye, Mic } from 'lucide-react';
import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MarkdownRenderer } from '../../components/markdown/MarkdownRenderer';
import { cn } from '../../lib/utils';
import { useResponsiveMode } from '../../hooks/useResponsiveMode';
import type { RawMessage, TurnTokenStats } from './types';
import { extractMessageImages, getContentText, formatTimestamp, formatTokenCount } from './utils';
import { ImageCarousel } from './ImageCarousel';
import { TokenInfoPopover } from './TokenInfoPopover';

interface MediaBlock {
  type: 'vision' | 'voice'
  content: string
}

function parseMediaBlocks(text: string): { mainText: string; blocks: MediaBlock[] } {
  const blocks: MediaBlock[] = []
  let mainText = text

  const patterns: { regex: RegExp; type: 'vision' | 'voice' }[] = [
    { regex: /\[图片识别:\s*([\s\S]*?)\]/g, type: 'vision' },
    { regex: /\[语音转录:\s*([\s\S]*?)\]/g, type: 'voice' },
    { regex: /\[transcription:\s*([\s\S]*?)\]/g, type: 'voice' },
  ]

  for (const { regex, type } of patterns) {
    let match
    while ((match = regex.exec(text)) !== null) {
      blocks.push({ type, content: match[1].trim() })
    }
    mainText = mainText.replace(regex, '').trim()
  }

  return { mainText, blocks }
}

function MediaBlockIndicator({ block }: { block: MediaBlock }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = block.type === 'vision' ? Eye : Mic
  const label = block.type === 'vision' ? 'Image Recognition' : 'Voice Transcription'

  return (
    <div className="mt-1.5 rounded-lg border border-white/20 overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center gap-1.5 w-full px-2.5 py-1 text-[11px] text-white/80 hover:text-white transition-colors"
      >
        <Icon className="w-3 h-3" />
        <span className="font-medium">{label}</span>
        {expanded ? <ChevronDown className="w-3 h-3 ml-auto" /> : <ChevronRight className="w-3 h-3 ml-auto" />}
      </button>
      {expanded && (
        <div className="px-2.5 pb-1.5 border-t border-white/10">
          <pre
            className="whitespace-pre-wrap font-[inherit] text-[11px] text-white/70 leading-relaxed mt-1 break-words max-h-[200px] overflow-y-auto"
            style={{ lineHeight: 'var(--cjk-line-height)' }}
          >
            {block.content}
          </pre>
        </div>
      )}
    </div>
  )
}

function AttachmentPreview({ urls, paths, isUser }: { urls: string[]; paths: string[]; isUser: boolean }) {
  if (urls.length === 0) return null

  return (
    <div
      className={cn(
        'rounded-2xl overflow-hidden border',
        isUser
          ? 'border-[var(--accent)]/30 bg-[var(--accent)]/10'
          : 'border-[var(--border)] bg-[var(--bg-secondary)]',
      )}
    >
      <div className="p-2.5">
        <ImageCarousel urls={urls} alt="Chat attachment" maxHeight={180} />
      </div>
      <div className={cn(
        'border-t px-3 py-2 space-y-1',
        isUser ? 'border-[var(--accent)]/20 bg-black/10' : 'border-[var(--border)] bg-[var(--bg-tertiary)]/70',
      )}>
        {paths.map((path, index) => (
          <div
            key={`${path}-${index}`}
            className={cn(
              'font-mono text-[11px] break-all',
              isUser ? 'text-white/85' : 'text-[var(--text-secondary)]',
            )}
          >
            {path}
          </div>
        ))}
      </div>
    </div>
  )
}

interface MessageBubbleProps {
  message: RawMessage;
  isUser: boolean;
  tokenStats?: TurnTokenStats;
  sessionKey?: string;
}

export const MessageBubble = React.memo(function MessageBubble({ message, isUser, tokenStats, sessionKey }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const [reasoningExpanded, setReasoningExpanded] = useState(false);
  const [showTokenInfo, setShowTokenInfo] = useState(false);
  const [showMobileTokenInfo, setShowMobileTokenInfo] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const mobilePopoverRef = useRef<HTMLDivElement>(null);
  const { isMobile } = useResponsiveMode();
  const navigate = useNavigate();
  const { text: textWithoutImages, images } = extractMessageImages(message.content);
  const text = getContentText(message.content);
  const reasoning = message.reasoning_content;
  useEffect(() => {
    if (!showTokenInfo && !showMobileTokenInfo) return;
    const handler = (e: MouseEvent) => {
      if (showTokenInfo && popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setShowTokenInfo(false);
      }
      if (showMobileTokenInfo && mobilePopoverRef.current && !mobilePopoverRef.current.contains(e.target as Node)) {
        setShowMobileTokenInfo(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showTokenInfo, showMobileTokenInfo]);

  if (!textWithoutImages && !reasoning && images.length === 0) return null;

  const { mainText, blocks: mediaBlocks } = isUser ? parseMediaBlocks(textWithoutImages) : { mainText: textWithoutImages, blocks: [] }
  const displayText = isUser ? mainText : textWithoutImages

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={cn('flex group', isUser ? 'justify-end' : 'justify-start')}>
      <div className={cn('flex items-stretch', isUser ? 'max-w-[80%]' : 'max-w-[85%]')}>
      <div className="relative max-w-full min-w-0 flex-1">
        {/* Reasoning content (collapsible, shown above the main bubble for assistant) */}
        {!isUser && reasoning && (
          <div
            className="mb-1 rounded-xl border border-[var(--border)] overflow-hidden"
            style={{ background: 'var(--bg-tertiary, var(--bg-secondary))' }}
          >
            <button
              onClick={() => setReasoningExpanded(v => !v)}
              className="flex items-center gap-1.5 w-full px-3 py-1.5 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Brain className="w-3.5 h-3.5 text-[var(--accent)]" />
              <span className="font-medium">Thinking</span>
              {reasoningExpanded ? (
                <ChevronDown className="w-3 h-3 ml-auto" />
              ) : (
                <ChevronRight className="w-3 h-3 ml-auto" />
              )}
            </button>
            {reasoningExpanded && (
              <div className="px-3 pb-2 border-t border-[var(--border)]">
                <pre
                  className="whitespace-pre-wrap font-[inherit] text-[12px] text-[var(--text-secondary)] italic leading-relaxed max-h-[300px] overflow-y-auto mt-1.5 break-words"
                  style={{ lineHeight: 'var(--cjk-line-height)' }}
                >
                  {reasoning}
                </pre>
              </div>
            )}
          </div>
        )}

        {images.length > 0 && (
          <div className={displayText || mediaBlocks.length > 0 ? 'mb-2' : ''}>
            <AttachmentPreview
              urls={images.map((image) => image.previewUrl)}
              paths={images.map((image) => image.displayPath)}
              isUser={isUser}
            />
          </div>
        )}

        {(displayText || mediaBlocks.length > 0) && (
          <>
            <div
              className={cn(
                'rounded-2xl text-sm leading-relaxed overflow-hidden',
                isMobile ? 'px-4 py-3' : 'px-4 py-2.5',
                isUser
                  ? 'bg-[var(--accent)] text-white rounded-br-md'
                  : 'bg-[var(--bg-secondary)] text-[var(--text-primary)] rounded-bl-md border border-[var(--border)]',
              )}
            >
              {displayText &&
                (isUser ? (
                  <pre className="whitespace-pre-wrap font-[inherit] break-words">{displayText}</pre>
                ) : (
                  <MarkdownRenderer content={displayText} />
                ))}
              {mediaBlocks.map((block, i) => (
                <MediaBlockIndicator key={i} block={block} />
              ))}
            </div>
            <div
              className={cn(
                'flex items-center gap-2 mt-0.5 text-[10px] text-[var(--text-secondary)]',
                isUser ? 'justify-end' : 'justify-start',
              )}
            >
              {message.timestamp && <span>{formatTimestamp(message.timestamp)}</span>}
              <button
                onClick={handleCopy}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:text-[var(--text-primary)]"
                title="Copy"
              >
                {copied ? <Check className="w-3 h-3 text-[var(--success)]" /> : <Copy className="w-3 h-3" />}
              </button>
              {tokenStats && !isUser && (
                <div className="relative" ref={popoverRef}>
                  <button
                    onClick={() => setShowTokenInfo(!showTokenInfo)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:text-[var(--accent)] flex items-center gap-0.5"
                    title="Token usage"
                  >
                    <Info className="w-3 h-3" />
                    <span>{formatTokenCount(tokenStats.total_tokens)}</span>
                  </button>
                  {showTokenInfo && (
                    <TokenInfoPopover
                      stats={tokenStats}
                      sessionKey={sessionKey}
                      turnSeq={tokenStats.turn_seq ?? undefined}
                      isMobile={isMobile}
                      onClose={() => setShowTokenInfo(false)}
                    />
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {/* Mobile-only token info button - positioned outside bubble on the right, vertically centered */}
        {isMobile && tokenStats && !isUser && (
          <div className="relative" ref={mobilePopoverRef}>
            <button
              onClick={() => setShowMobileTokenInfo(v => !v)}
              className="absolute -right-8 -translate-y-full min-w-[44px] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--accent)] active:text-[var(--accent)] transition-colors"
              title="Token usage"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            {showMobileTokenInfo && (
              <TokenInfoPopover
                stats={tokenStats}
                sessionKey={sessionKey}
                turnSeq={tokenStats.turn_seq ?? undefined}
                isMobile={true}
                onClose={() => setShowMobileTokenInfo(false)}
              />
            )}
          </div>
        )}
      </div>
      {/* Right-side token label (desktop only) */}
      {!isUser && !isMobile && tokenStats && (
        <button
          onClick={() => {
            const params = new URLSearchParams({ session_key: sessionKey || '' })
            if (tokenStats.conversation_id) params.set('conversation_id', tokenStats.conversation_id)
            if (tokenStats.turn_seq != null) params.set('turn_seq', String(tokenStats.turn_seq))
            navigate(`/tokens?${params.toString()}`)
          }}
          className="text-[10px] font-mono text-[var(--text-secondary)] whitespace-nowrap ml-2 self-center hover:text-[var(--accent)] transition-colors"
          title="查看 Token 统计"
        >
          ⚡ {formatTokenCount(tokenStats.total_tokens)}
        </button>
      )}
      </div>
    </div>
  );
}, (prev, next) => {
  return prev.message.content === next.message.content &&
         prev.tokenStats === next.tokenStats
})
