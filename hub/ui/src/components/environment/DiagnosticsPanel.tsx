import { useStatus } from '@/api/status'
import { Icon } from '@/components/common/Icon'
import { SettingsSection } from '@/components/environment/SettingsSection'
import { Button } from '@/components/ui/button'
import { useCopy } from '@/hooks/useCopy'

export function DiagnosticsPanel() {
  const { data, isLoading } = useStatus()
  const { copied, copy } = useCopy()
  const output = JSON.stringify(data ?? {}, null, 2)
  return (
    <SettingsSection
      title="Diagnostics"
      description="Raw Hub status for troubleshooting this project. Values update with the live status query."
      actions={!isLoading ? (
        <Button variant="outline" size="sm" onClick={() => copy(output)}>
          <Icon name={copied ? 'check' : 'content_copy'} size={14} />
          {copied ? 'Copied' : 'Copy status'}
        </Button>
      ) : undefined}
    >
      <div className="py-4">
        {isLoading ? (
          <div aria-label="Loading diagnostics" className="space-y-2">
            <div className="skeleton h-4 w-1/3" />
            <div className="skeleton h-52 w-full" />
          </div>
        ) : (
          <pre className="settings-code-surface p-4 font-mono text-xs leading-relaxed" tabIndex={0}>
            {output}
          </pre>
        )}
      </div>
    </SettingsSection>
  )
}
