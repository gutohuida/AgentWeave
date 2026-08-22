import { Icon } from './Icon'

interface EmptyStateProps {
  icon: string   // Icon name — see the map in ./Icon.tsx
  title: string
  description?: string
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div
        className="mb-4 flex items-center justify-center"
        style={{ width: 52, height: 52, borderRadius: 'var(--radius-lg)', background: 'var(--surface-2)', border: '1px solid var(--border-region)' }}
      >
        <Icon name={icon} size={25} style={{ color: 'var(--text-3)' }} />
      </div>
      <p className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{title}</p>
      {description && <p className="mt-1.5 max-w-sm text-xs leading-5" style={{ color: 'var(--text-3)' }}>{description}</p>}
    </div>
  )
}
