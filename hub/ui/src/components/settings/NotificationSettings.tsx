import * as React from 'react'
import { Button } from '@/components/ui/button'
import { SettingsGroup, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import { appWindowApi } from '@/hooks/useNotifications'
import type { NotifyKind } from '@/lib/notify/classify'
import { DEFAULT_NOTIFY_PREFS, loadNotifyPrefs, saveNotifyPrefs, type NotifyPrefs } from '@/lib/notify/prefs'
import { playSound } from '@/lib/sound/player'

const KINDS: Array<{ kind: NotifyKind; label: string; description: string }> = [
  { kind: 'ask', label: 'An agent needs you', description: 'A question, or a permission to decide.' },
  { kind: 'fail', label: 'Work stalled or failed', description: 'A stall, a failed run, a suspended message chain, a loop stopped short.' },
  { kind: 'reply', label: 'An agent replied to you', description: 'A turn you started in a conversation finished. Silent while you are watching that conversation.' },
  { kind: 'done', label: 'Work finished', description: 'A loop that worked through its whole queue.' },
]

/** Sound and notifications: the operator's own, for every project on this Hub, kept by this window
 *  (change `agentweave-calls-you-with-its-own-sound`). The sound switch also reaches the native
 *  app's opening sound, through its bridge. */
export function NotificationSettings() {
  const [prefs, setPrefs] = React.useState<NotifyPrefs>(loadNotifyPrefs)
  const change = (next: NotifyPrefs) => {
    setPrefs(next)
    saveNotifyPrefs(next)
    if (next.sound !== prefs.sound) appWindowApi()?.sound?.(next.sound)?.catch(() => {})
  }
  const volumePercent = Math.round(prefs.volume * 100)
  return (
    <SettingsGroup
      title="Sound and notifications"
      description="For you, across every project on this Hub. In front, a toast and a quiet sound; behind, the sound, a count in the title and a flashing taskbar button."
    >
      <SettingsRow
        label="Sound"
        description="Also the sound AgentWeave makes when it opens."
        changed={prefs.sound !== DEFAULT_NOTIFY_PREFS.sound}
        onReset={() => change({ ...prefs, sound: DEFAULT_NOTIFY_PREFS.sound })}
        control={
          <Switch
            checked={prefs.sound}
            onCheckedChange={(sound) => change({ ...prefs, sound })}
            aria-label="Sound"
            data-testid="notify-sound"
          />
        }
      />
      <SettingsRow
        label="Volume"
        htmlFor="notify-volume"
        inactive={!prefs.sound}
        changed={prefs.volume !== DEFAULT_NOTIFY_PREFS.volume}
        onReset={() => change({ ...prefs, volume: DEFAULT_NOTIFY_PREFS.volume })}
        control={
          <div className="flex items-center gap-2">
            <input
              id="notify-volume"
              data-testid="notify-volume"
              type="range"
              min={0}
              max={100}
              step={5}
              value={volumePercent}
              onChange={(e) => setPrefs({ ...prefs, volume: Number(e.target.value) / 100 })}
              onPointerUp={() => change(prefs)}
              onKeyUp={() => change(prefs)}
              className="w-28 accent-[var(--brand-madder)]"
            />
            <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">{volumePercent}%</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={!prefs.sound}
              onClick={() => playSound('ask', prefs.volume * 0.7)}
              data-testid="notify-preview"
            >
              Play
            </Button>
          </div>
        }
      />
      {KINDS.map(({ kind, label, description }) => (
        <SettingsRow
          key={kind}
          label={label}
          description={description}
          changed={prefs.kinds[kind] !== DEFAULT_NOTIFY_PREFS.kinds[kind]}
          onReset={() => change({ ...prefs, kinds: { ...prefs.kinds, [kind]: DEFAULT_NOTIFY_PREFS.kinds[kind] } })}
          control={
            <Switch
              checked={prefs.kinds[kind]}
              onCheckedChange={(on) => change({ ...prefs, kinds: { ...prefs.kinds, [kind]: on } })}
              aria-label={label}
              data-testid={`notify-kind-${kind}`}
            />
          }
        />
      ))}
    </SettingsGroup>
  )
}
