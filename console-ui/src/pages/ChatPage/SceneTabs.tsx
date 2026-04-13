import { Bot, Clock, Radio, Monitor, Terminal, MoreHorizontal } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { SceneType, SessionMeta } from './types'
import { SCENE_LABELS, SCENE_ORDER } from './types'

interface SceneTabsProps {
  sessions: SessionMeta[]
  activeScene: SceneType
  onSceneChange: (scene: SceneType) => void
}

const SCENE_ICONS: Record<SceneType, React.ElementType> = {
  telegram: Bot,
  cron: Clock,
  heartbeat: Radio,
  console: Monitor,
  cli: Terminal,
  other: MoreHorizontal,
  feishu: Bot,
  QQ: Bot,
  wx: Bot,
  discord: Bot,
}

export function SceneTabs({ sessions, activeScene, onSceneChange }: SceneTabsProps) {
  const scenesWithData = new Set(sessions.map((s) => s.scene))
  scenesWithData.add('console')
  const availableScenes = SCENE_ORDER.filter((s) => scenesWithData.has(s))

  return (
    <div className="flex items-center gap-1 px-4 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border)] overflow-x-auto rounded-t-xl">
      {availableScenes.map((scene) => {
        const Icon = SCENE_ICONS[scene]
        const count = sessions.filter((s) => s.scene === scene).length
        return (
          <button
            key={scene}
            onClick={() => onSceneChange(scene)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap',
              activeScene === scene
                ? 'bg-[var(--accent)] text-white'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            <span>{SCENE_LABELS[scene]}</span>
            <span className={cn(
              'text-[10px] px-1.5 py-0.5 rounded-full min-w-[1.25rem] text-center',
              activeScene === scene
                ? 'bg-white/20'
                : 'bg-[var(--bg-tertiary)]',
            )}>
              {count}
            </span>
          </button>
        )
      })}
    </div>
  )
}
