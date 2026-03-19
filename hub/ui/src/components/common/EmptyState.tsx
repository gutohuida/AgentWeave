interface EmptyStateProps {
  icon: string   // Material Symbols Rounded name
  title: string
  description?: string
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div
        className="mb-4 m3-icon-container"
        style={{ width: 64, height: 64, background: 'var(--surface-highest)' }}
      >
        <span
          className="material-symbols-rounded select-none"
          style={{
            fontSize: 32,
            fontVariationSettings: `'FILL' 0, 'wght' 400`,
            color: 'var(--primary)',
          }}
        >
          {icon}
        </span>
      </div>
      <p className="m3-headline-small text-foreground">{title}</p>
      {description && <p className="mt-2 m3-body-medium" style={{ color: 'var(--on-sv)' }}>{description}</p>}
    </div>
  )
}
