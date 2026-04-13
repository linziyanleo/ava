import { useRef, useEffect } from 'react'

interface ScreencastViewProps {
  frame: string | null // base64 JPEG data
  connected: boolean
}

export default function ScreencastView({ frame, connected }: ScreencastViewProps) {
  const imgRef = useRef<HTMLImageElement>(null)

  useEffect(() => {
    if (frame && imgRef.current) {
      imgRef.current.src = `data:image/jpeg;base64,${frame}`
    }
  }, [frame])

  if (!connected) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[var(--bg-primary)] rounded-lg border border-[var(--border)]">
        <div className="text-center text-[var(--text-secondary)]">
          <div className="text-4xl mb-4">🌐</div>
          <p className="text-lg">未连接</p>
          <p className="text-sm mt-2">等待 PageAgent 会话启动...</p>
        </div>
      </div>
    )
  }

  if (!frame) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[var(--bg-primary)] rounded-lg border border-[var(--border)]">
        <div className="text-center text-[var(--text-secondary)]">
          <div className="animate-pulse text-lg">等待画面...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex items-center justify-center bg-black rounded-lg overflow-hidden">
      <img
        ref={imgRef}
        alt="Browser screencast"
        className="max-w-full max-h-full object-contain"
        draggable={false}
      />
    </div>
  )
}
