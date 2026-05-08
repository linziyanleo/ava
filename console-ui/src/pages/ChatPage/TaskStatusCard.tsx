import type { DirectTaskMessage } from './types'
import { ConversationTaskCard } from './ConversationTaskCard'

export function TaskStatusCard({ task }: { task: DirectTaskMessage }) {
  return <ConversationTaskCard task={task} variant="standalone" />
}
