import { AppSettingsScreen } from '@/components/settings/AppSettingsScreen'
import { toast } from '@/lib/toast'
import type { ScreenProps } from '../routes'

/** App settings, as the app renders them: the operator's own (sound and notifications,
 *  appearance, the Hub connection), reached from the rail footer on every screen. The page is the
 *  real component; the mock only supplies navigation. */
export default function AppSettings({ route, go }: ScreenProps) {
  const section = route.kind === 'app-settings' ? route.section : 'notifications'
  return (
    <AppSettingsScreen
      section={section}
      onSelectSection={(next) => go({ kind: 'app-settings', section: next })}
      onOpenSetup={() => toast({ title: 'Hub connection', description: 'Opens the connection dialog (unchanged in this mock).' })}
      back={{ label: 'Back to AgentWeave', onClick: () => go({ kind: 'tab', tab: 'overview' }) }}
    />
  )
}
