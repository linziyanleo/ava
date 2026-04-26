import { useCallback, useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { cn } from '../../lib/utils'

export interface CodeBlockProps {
  language?: string
  code: string
  className?: string
}

function useIsDark() {
  const [isDark, setIsDark] = useState(() =>
    typeof document !== 'undefined'
      ? !document.documentElement.classList.contains('light')
      : true,
  )

  useEffect(() => {
    const root = document.documentElement
    const observer = new MutationObserver(() => {
      setIsDark(!root.classList.contains('light'))
    })
    observer.observe(root, { attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  return isDark
}

export function CodeBlock({ language, code, className }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const isDark = useIsDark()

  const handleCopy = useCallback(() => {
    if (!navigator.clipboard) return
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }, [code])

  return (
    <div
      className={cn(
        'overflow-hidden rounded-lg border border-[var(--border)]',
        className,
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between gap-3 px-4 py-2 text-xs',
          isDark
            ? 'bg-slate-900 text-slate-300'
            : 'bg-slate-100 text-slate-600',
        )}
      >
        <span className="font-mono lowercase">
          {language || 'text'}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className={cn(
            'inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 font-mono transition-colors',
            isDark
              ? 'hover:bg-slate-800 hover:text-slate-100'
              : 'hover:bg-slate-200 hover:text-slate-900',
          )}
          aria-label="复制代码"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
          <span>{copied ? '已复制' : '复制'}</span>
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={isDark ? oneDark : oneLight}
        customStyle={{
          margin: 0,
          padding: '1rem',
          fontSize: '0.85rem',
          lineHeight: 1.6,
          borderRadius: 0,
        }}
        PreTag="pre"
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}
