import { useStatus } from '@/api/status'
import { SettingsSection } from '@/components/environment/SettingsSection'

export function DiagnosticsPanel() {
  const { data } = useStatus()
  return (
    <SettingsSection title="Diagnostics" description="Raw Hub status, for troubleshooting this project.">
      <pre className="mt-3 overflow-auto rounded p-3 text-xs" style={{ background: 'var(--surface-2)' }}>
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </SettingsSection>
  )
}
