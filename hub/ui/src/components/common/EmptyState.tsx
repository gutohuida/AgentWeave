import { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
      <Icon className="mb-4 h-10 w-10 opacity-40" />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="mt-1 text-xs opacity-70">{description}</p>}
    </div>
  )
}
