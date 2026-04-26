interface EmptyStateProps {
  icon: string   // Material Symbols Rounded name
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
        <span
          className="material-symbols-rounded select-none"
          style={{
            fontSize: 32,
            fontVariationSettings: `'FILL' 0, 'wght' 400`,
            color: 'var(--text-3)',
          }}
        >
          {icon}
        </span>
      </div>
      <p className="text-lg font-normal" style={{ color: 'var(--text)' }}>{title}</p>
      {description && <p className="mt-2 text-sm" style={{ color: 'var(--text-3)' }}>{description}</p>}
    </div>
  )
}
