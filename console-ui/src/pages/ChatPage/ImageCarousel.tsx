import { useState, useEffect, useCallback, useRef } from 'react'
import { ChevronLeft, ChevronRight, X, ZoomIn } from 'lucide-react'
import { cn } from '../../lib/utils'

interface LightboxProps {
  src: string
  alt?: string
  onClose: () => void
}

function Lightbox({ src, alt, onClose }: LightboxProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-full bg-black/50 text-white hover:bg-black/70 transition-colors"
      >
        <X className="w-5 h-5" />
      </button>
      <img
        src={src}
        alt={alt || ''}
        className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}

interface ImageCarouselProps {
  urls: string[]
  alt?: string
  maxHeight?: number
}

export function ImageCarousel({ urls, alt, maxHeight = 200 }: ImageCarouselProps) {
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  const updateScrollState = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 1)
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateScrollState()
    el.addEventListener('scroll', updateScrollState, { passive: true })
    const ro = new ResizeObserver(updateScrollState)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', updateScrollState)
      ro.disconnect()
    }
  }, [updateScrollState, urls])

  const scroll = (dir: 'left' | 'right') => {
    const el = scrollRef.current
    if (!el) return
    const amount = el.clientWidth * 0.8
    el.scrollBy({ left: dir === 'left' ? -amount : amount, behavior: 'smooth' })
  }

  if (urls.length === 0) return null

  const isSingle = urls.length === 1

  return (
    <>
      <div className="relative group/carousel">
        <div
          ref={scrollRef}
          className={cn(
            'flex gap-2 overflow-x-auto scrollbar-hide',
            isSingle && 'justify-start',
          )}
          style={{ scrollSnapType: 'x mandatory' }}
        >
          {urls.map((url, i) => (
            <div
              key={i}
              className="relative shrink-0 cursor-pointer rounded-md overflow-hidden border border-[var(--border)] hover:border-[var(--accent)] transition-colors group/img"
              style={{ scrollSnapAlign: 'start' }}
              onClick={() => setLightboxIdx(i)}
            >
              <img
                src={url}
                alt={alt || `Image ${i + 1}`}
                className="block object-cover rounded-md"
                style={{ maxHeight, maxWidth: isSingle ? '100%' : 240 }}
                loading="lazy"
              />
              <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover/img:bg-black/20 transition-colors">
                <ZoomIn className="w-5 h-5 text-white opacity-0 group-hover/img:opacity-80 transition-opacity drop-shadow-lg" />
              </div>
            </div>
          ))}
        </div>

        {!isSingle && canScrollLeft && (
          <button
            onClick={() => scroll('left')}
            className="absolute left-0 top-1/2 -translate-y-1/2 p-1 rounded-full bg-black/50 text-white hover:bg-black/70 opacity-0 group-hover/carousel:opacity-100 transition-opacity"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
        {!isSingle && canScrollRight && (
          <button
            onClick={() => scroll('right')}
            className="absolute right-0 top-1/2 -translate-y-1/2 p-1 rounded-full bg-black/50 text-white hover:bg-black/70 opacity-0 group-hover/carousel:opacity-100 transition-opacity"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>

      {lightboxIdx !== null && (
        <Lightbox
          src={urls[lightboxIdx]}
          alt={alt}
          onClose={() => setLightboxIdx(null)}
        />
      )}
    </>
  )
}
