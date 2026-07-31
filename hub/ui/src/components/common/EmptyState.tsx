import { Icon } from './Icon'

interface EmptyStateProps {
  icon: string   // Icon name — see the map in ./Icon.tsx
  title: string
  description?: string
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div
        className="mb-4 flex items-center justify-center rounded-full"
        style={{ width: 64, height: 64, background: 'var(--surface-3)' }}
      >
        <Icon name={icon} size={32} style={{ color: 'var(--text-3)' }} />
      </div>
      <p className="text-lg font-normal" style={{ color: 'var(--text)' }}>{title}</p>
      {description && <p className="mt-2 text-sm" style={{ color: 'var(--text-3)' }}>{description}</p>}
    </div>
  )
}
