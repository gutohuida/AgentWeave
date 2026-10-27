import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { applyColorMode } from '@/lib/colorMode'
import type { AppSettingsSection } from '@/lib/navigation'
import { useConfigStore, type ModeId } from '@/store/configStore'
import { NotificationSettings } from './NotificationSettings'
import { SettingsNavLayout } from './SettingsNavLayout'

const SECTIONS: ReadonlyArray<{ id: AppSettingsSection; label: string; icon: string }> = [
  { id: 'notifications', label: 'Sound and notifications', icon: 'notifications' },
  { id: 'appearance', label: 'Appearance', icon: 'palette' },
  { id: 'connection', label: 'Hub connection', icon: 'link' },
]

const SCOPE = 'Yours, for every project on this Hub. Kept by this window.'

/**
 * App settings: the operator's own, as opposed to a project's or an agent's.
 *
 * Sound and notifications, light or dark, and the Hub this window talks to are kept per window
 * (`prefs.ts`, the config store), not per project, so they live here rather than inside one
 * project's settings, and the page opens with no project at all (the rail's footer reaches it on
 * every screen).
 */
export function AppSettingsScreen({
  section,
  onSelectSection,
  onOpenSetup,
  back,
}: {
  section: AppSettingsSection
  onSelectSection: (section: AppSettingsSection) => void
  /** Opens the Hub connection dialog (address and key). */
  onOpenSetup: () => void
  /** Where the operator came from, when they came from a project. */
  back?: { label: string; onClick: () => void }
}) {
  let body: React.ReactNode
  switch (section) {
    case 'notifications':
      body = <NotificationSettings />
      break
    case 'appearance':
      body = <AppearanceSettings />
      break
    case 'connection':
      body = <ConnectionSettings onOpenSetup={onOpenSetup} />
      break
  }
  return (
    <div className="h-full min-h-0" data-testid={`app-settings-${section}`}>
      <SettingsNavLayout
        title="App settings"
        subtitle="Yours, on this Hub"
        back={back}
        items={SECTIONS}
        active={section}
        onSelect={onSelectSection}
      >
        <SettingsPage icon="settings" title="App settings" description={SCOPE}>
          {body}
        </SettingsPage>
      </SettingsNavLayout>
    </div>
  )
}

function AppearanceSettings() {
  const mode = useConfigStore((state) => state.mode)
  return (
    <SettingsGroup title="Appearance" description="Light or dark, for this window.">
      <SettingsRow
        label="Theme"
        control={
          <Segmented<ModeId>
            label="Appearance"
            value={mode}
            onChange={applyColorMode}
            options={[
              { value: 'light', label: 'Light' },
              { value: 'dark', label: 'Dark' },
            ]}
          />
        }
      />
    </SettingsGroup>
  )
}

function ConnectionSettings({ onOpenSetup }: { onOpenSetup: () => void }) {
  const hubUrl = useConfigStore((state) => state.hubUrl)
  const configured = useConfigStore((state) => state.isConfigured)
  return (
    <SettingsGroup title="Hub connection" description="The Hub this window reads and writes. The key stays in this window’s session.">
      <SettingsRow
        label="Hub address"
        description={configured ? 'Connected with a saved key.' : 'No key saved yet.'}
        control={
          <div className="flex items-center gap-2">
            <span className="text-xs tabular-nums" data-testid="hub-address">
              {hubUrl || '—'}
            </span>
            <Button variant="outline" size="sm" onClick={onOpenSetup}>
              Change
            </Button>
          </div>
        }
      />
    </SettingsGroup>
  )
}
