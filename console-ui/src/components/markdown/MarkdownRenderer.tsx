import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { cn } from '../../lib/utils'
import { CodeBlock } from './CodeBlock'
import 'katex/dist/katex.min.css'

export interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const components: Components = {
    code({ className: codeClassName, children, ...props }) {
      const match = /language-([\w-]+)/.exec(codeClassName || '')
      const code = String(children).replace(/\n$/, '')
      const isInline = !match && !code.includes('\n')

      if (isInline) {
        return (
          <code
            className={cn(
              'rounded bg-black/20 px-1 py-0.5 font-mono text-[0.85em] text-[var(--accent)]',
              codeClassName,
            )}
            {...props}
          >
            {children}
          </code>
        )
      }

      return <CodeBlock language={match?.[1]} code={code} className="my-3" />
    },
    pre({ children: markdownChildren }) {
      return <>{markdownChildren}</>
    },
    a({ children, href, ...props }) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent)] underline underline-offset-2 hover:opacity-80"
          {...props}
        >
          {children}
        </a>
      )
    },
    table({ children }) {
      return (
        <div className="my-2 overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">{children}</table>
        </div>
      )
    },
    th({ children }) {
      return (
        <th className="border border-[var(--border)] bg-[var(--bg-tertiary,var(--bg-secondary))] px-3 py-1.5 text-left font-semibold">
          {children}
        </th>
      )
    },
    td({ children }) {
      return (
        <td className="border border-[var(--border)] px-3 py-1.5">
          {children}
        </td>
      )
    },
  }

  return (
    <div
      className={cn('markdown-body min-w-0', className)}
      style={{ lineHeight: 'var(--cjk-line-height)' }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
