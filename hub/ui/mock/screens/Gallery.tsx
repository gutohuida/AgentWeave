import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { DropZone } from '@/components/ui/dropzone'
import { Input } from '@/components/ui/input'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuSelect, MenuTrigger } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { Field, SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/lib/toast'
import { Icon } from '@/components/common/Icon'
import { describeCron, formatAgo, formatDateTime, formatDay, formatDuration, formatMoney, formatTokens, formatTokensExact } from '@/lib/format'
import type { ScreenProps } from '../routes'

/** Every new primitive in one place, in both themes, so each can be judged on its own before it
 *  is judged in a screen. */
export default function Gallery({ now }: ScreenProps) {
  const [on, setOn] = React.useState(true)
  const [off, setOff] = React.useState(false)
  const [view, setView] = React.useState<'board' | 'dependencies'>('board')
  const [sub, setSub] = React.useState<'ledger' | 'activity' | 'logs'>('ledger')
  const [runner, setRunner] = React.useState('claude-default')
  const [name, setName] = React.useState('')
  const [hops, setHops] = React.useState('6')

  return (
    <SettingsPage icon="palette" title="Primitives & motion" description="The shared pieces every screen in this mock is built from. Each one replaces several one-off versions in today's build.">
      <SettingsGroup title="Switch" description="Replaces 21 native checkboxes. Press and hold to see the thumb stretch toward where it is going.">
        <SettingsRow label="Agents may start flows" description="Needed for create_job, create_flow and create_loop." control={<Switch checked={on} onCheckedChange={(v) => { setOn(v); toast({ title: v ? 'Agents may start flows' : 'Agents may no longer start flows', tone: 'success' }) }} aria-label="Agents may start flows" />} />
        <SettingsRow label="Vault distillation" description="Off: sources stay in the vault without facts." control={<Switch checked={off} onCheckedChange={setOff} aria-label="Vault distillation" />} />
      </SettingsGroup>

      <SettingsGroup title="Segmented" description="One control for every view switch. Arrow keys move between options.">
        <SettingsRow label="Tasks view" control={<Segmented label="Tasks view" value={view} onChange={setView} options={[{ value: 'board', label: 'Board' }, { value: 'dependencies', label: 'Dependencies' }]} />} />
        <SettingsRow label="Activity view, with counts" control={<Segmented label="Activity view" value={sub} onChange={setSub} options={[{ value: 'ledger', label: 'Ledger' }, { value: 'activity', label: 'Activity', count: 65 }, { value: 'logs', label: 'Logs', count: 500 }]} />} />
      </SettingsGroup>

      <SettingsGroup title="Select and menus" description="A themed menu instead of the operating system's list: full labels, a second line saying what each choice means, the current one checked.">
        <SettingsRow
          label="Runner"
          description="Which runner does this job."
          changed={runner !== 'claude-default'}
          onReset={() => setRunner('claude-default')}
          control={
            <MenuSelect
              label="Runner"
              value={runner}
              onChange={setRunner}
              options={[
                { value: 'claude-default', label: 'Claude (default)', detail: 'Provider default model', icon: 'smart_toy' },
                { value: 'opus', label: 'Claude Code — Opus 5.5', detail: 'claude-opus-5-5', icon: 'smart_toy' },
                { value: 'sonnet', label: 'Claude Code — Sonnet 5.5', detail: 'claude-sonnet-5-5', icon: 'smart_toy' },
                { value: 'none', label: 'None', detail: 'This job does nothing until a runner is chosen' },
              ]}
            />
          }
        />
        <SettingsRow
          label="Overflow menu"
          description="Secondary actions live behind one button instead of a row of text links."
          control={
            <Menu>
              <MenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <Icon name="more_horiz" size={14} /> More
                </Button>
              </MenuTrigger>
              <MenuContent>
                <MenuItem icon="restart_alt">Reopen</MenuItem>
                <MenuItem icon="archive" shortcut="A">Archive</MenuItem>
                <MenuSeparator />
                <MenuItem icon="delete" destructive>Delete document…</MenuItem>
              </MenuContent>
            </Menu>
          }
        />
      </SettingsGroup>

      <SettingsGroup title="Fields" description="A default height for every field, and one reserved line for its hint or error, so validation never moves the layout.">
        <SettingsRow label="Name" stacked control={<Field hint="Shown wherever this source is listed." htmlFor="g-name"><Input id="g-name" value={name} placeholder="Kickoff call with the operator" onChange={(e) => setName(e.target.value)} /></Field>} />
        <SettingsRow label="Hop budget" description="Agent-to-agent hops before a chain pauses for you." changed={hops !== '6'} onReset={() => setHops('6')} control={<Field error={Number(hops) < 1 ? 'At least 1 hop.' : undefined} htmlFor="g-hops"><Input id="g-hops" inputMode="numeric" value={hops} aria-invalid={Number(hops) < 1} onChange={(e) => setHops(e.target.value)} style={{ width: 96 }} /></Field>} />
      </SettingsGroup>

      <SettingsGroup title="Dialog, toast and drop zone" description="Overlays scale from 0.98 and fade in 200ms; they leave in 140ms. Toasts rise in, pause on hover and carry one action.">
        <SettingsRow
          label="Dialog"
          control={
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm">Open dialog</Button>
              </DialogTrigger>
              <DialogContent
                title="Archive Builder?"
                description="Builder leaves the sidebar, task assignment and peer recipients. Everything it did stays, under its name."
                footer={
                  <>
                    <DialogClose asChild><Button variant="ghost" size="sm">Keep Builder</Button></DialogClose>
                    <DialogClose asChild><Button variant="destructive" size="sm" onClick={() => toast({ title: 'Builder archived', action: { label: 'Undo', onClick: () => toast({ title: 'Builder restored', tone: 'success' }) } })}>Archive Builder</Button></DialogClose>
                  </>
                }
              />
            </Dialog>
          }
        />
        <SettingsRow
          label="Toasts"
          control={
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => toast({ title: 'Settings saved', tone: 'success' })}>Success</Button>
              <Button variant="outline" size="sm" onClick={() => toast({ title: 'Could not reach the Hub', description: 'Retrying in 5 seconds.', tone: 'error' })}>Error</Button>
            </div>
          }
        />
        <SettingsRow label="Drop zone" stacked control={<div className="w-full"><DropZone title="Drop files or folders" hint="Text, Markdown, PDF or images, up to 10 MB each." onFiles={(files) => toast({ title: `${files.length} file${files.length === 1 ? '' : 's'} added` })} /></div>} />
      </SettingsGroup>

      <SettingsGroup title="Numbers and dates" description="One format for each kind of value, everywhere. Exact values sit in the title.">
        <div className="tablebox-mock">
          {[
            ['Tokens', formatTokens(31843065), formatTokensExact(31843065)],
            ['Money', formatMoney(78.08), formatMoney(1234.5)],
            ['Duration', formatDuration(239), formatDuration(3725)],
            ['Date and time', formatDateTime('2026-10-16T19:04:17Z', now), 'one style, no locale drift'],
            ['A calendar day', formatDay('2026-10-14', now), ''],
            ['Relative', formatAgo('2026-10-16T19:04:17Z', now), formatAgo('2026-10-17T12:06:00Z', now)],
            ['Schedule', describeCron('*/5 * * * *'), '*/5 * * * * in the tooltip'],
          ].map(([k, a, b]) => (
            <div key={k} className="aw-settings-row" style={{ gridTemplateColumns: '180px 1fr 1fr' }}>
              <span className="aw-settings-row-label">{k}</span>
              <span className="tabular text-[13px]">{a}</span>
              <span className="text-[12.5px]" style={{ color: 'var(--text-3)' }}>{b}</span>
            </div>
          ))}
        </div>
      </SettingsGroup>
    </SettingsPage>
  )
}
