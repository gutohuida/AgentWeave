import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { Field, SettingsGroup, SettingsNotice, SettingsPage, SettingsRow } from '@/components/ui/settings'
import type { JourneyStep, SpecSize } from '@/api/spec'
import { CommittedTextarea } from './CommittedInput'

/**
 * Project settings → Spec steps (`a-project-orders-its-own-spec-steps`, restyled by
 * `settings-in-the-app-s-style-where-you-expect-them`). The steps a change walks, in order, with
 * the operator's own among them. Every action applies at once — adding, moving or removing a step,
 * a size, or an instruction when you leave its field — and the container saves the whole list,
 * which the Hub validates. The seven built-in steps stay, in their order.
 */

const SIZES: ReadonlyArray<{ value: SpecSize; label: string }> = [
  { value: 'fix', label: 'Fix' },
  { value: 'small', label: 'Small' },
  { value: 'large', label: 'Large' },
]
const DEFAULT_NEW_SIZES: SpecSize[] = ['small', 'large']
const MAX_KEY = 48

/** Built-in steps by what an operator calls them; the key stays in the title for a reference. */
const BUILT_IN_TITLES: Record<string, string> = {
  intake: 'Intake',
  requirements: 'Requirements',
  'requirements-and-acceptance': 'Requirements and acceptance',
  acceptance: 'Acceptance criteria',
  approach: 'Approach',
  tasks: 'Tasks',
  build: 'Build',
}

/** A step is custom when it carries its own text; a built-in step is its key alone. */
const isCustom = (step: JourneyStep) => step.instructions !== undefined

function stepTitle(step: JourneyStep): string {
  if (isCustom(step)) return step.title ?? step.key
  return BUILT_IN_TITLES[step.key] ?? step.key.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

/** The key a title gives a custom step: a lowercase slug, the form the Hub accepts. */
function slug(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_KEY)
    .replace(/-+$/, '')
}

function sizeWords(sizes: SpecSize[] | undefined): string {
  const chosen = SIZES.filter((s) => sizes?.includes(s.value)).map((s) => s.label.toLowerCase())
  return chosen.length ? `Runs for ${chosen.join(', ')} changes` : 'Runs for no size yet'
}

/** Which sizes a step joins: toggles, any number of them. */
function SizePicks({ value, onChange, label }: { value: SpecSize[]; onChange: (next: SpecSize[]) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="aw-picks">
      {SIZES.map((size) => {
        const on = value.includes(size.value)
        return (
          <button
            key={size.value}
            type="button"
            data-slot="pick"
            className="aw-pick"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((v) => v !== size.value) : SIZES.map((s) => s.value).filter((v) => v === size.value || value.includes(v)))}
          >
            {on ? <Icon name="check" size={12} /> : null}
            {size.label}
          </button>
        )
      })}
    </div>
  )
}

export function SpecStepsSettings({
  steps,
  diagnostics = [],
  notices,
  onChange,
}: {
  steps: JourneyStep[]
  /** What the Hub found wrong with the project's steps file. */
  diagnostics?: { message: string }[]
  /** A refusal of the last change, shown under the heading. */
  notices?: React.ReactNode
  /** The whole list after one change, and the sentence a toast says. */
  onChange: (steps: JourneyStep[], said: string) => void
}) {
  const [appending, setAppending] = React.useState<string | null>(null)
  const [after, setAfter] = React.useState<string>(steps[steps.length - 1]?.key ?? '')
  const [title, setTitle] = React.useState('')
  const [markdown, setMarkdown] = React.useState('')
  const [sizes, setSizes] = React.useState<SpecSize[]>(DEFAULT_NEW_SIZES)
  const [addError, setAddError] = React.useState<string | null>(null)

  const patch = (key: string, change: Partial<JourneyStep>, said: string) =>
    onChange(steps.map((s) => (s.key === key ? { ...s, ...change } : s)), said)
  const move = (index: number, by: number) => {
    const next = [...steps]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item!)
    onChange(next, `Moved ${stepTitle(item!)} ${by < 0 ? 'up' : 'down'}`)
  }

  const addStep = () => {
    const key = slug(title)
    if (!key) return setAddError('The title needs at least one letter or digit.')
    if (steps.some((s) => s.key === key)) return setAddError('A step with that title already exists; give this one another.')
    const at = after === '' ? 0 : steps.findIndex((s) => s.key === after) + 1
    const entry: JourneyStep = { key, title: title.trim(), instructions: markdown.trim(), sizes: SIZES.map((s) => s.value).filter((v) => sizes.includes(v)) }
    onChange([...steps.slice(0, at), entry, ...steps.slice(at)], `Added the step ${entry.title}`)
    setTitle('')
    setMarkdown('')
    setSizes(DEFAULT_NEW_SIZES)
    setAddError(null)
  }

  return (
    <SettingsPage icon="list_tree" title="Spec steps" description="The steps a spec change walks, in order. Add your own, or add an instruction to any step.">
      {notices}
      {diagnostics.length ? (
        <SettingsNotice tone="error" title="This project's steps file has a problem." testId="spec-steps-diagnostics">
          {diagnostics.map((d) => (
            <p key={d.message}>{d.message}</p>
          ))}
          <p>Until it is fixed, changes are briefed with the built-in steps.</p>
        </SettingsNotice>
      ) : null}

      <SettingsGroup title="Steps, in order">
        {steps.map((step, index) => {
          const custom = isCustom(step)
          const showAppend = appending === step.key || Boolean(step.append?.trim())
          const name = stepTitle(step)
          return (
            <SettingsRow
              key={step.key}
              listItem
              label={
                <span className="aw-step-label">
                  <span className="aw-step-index">{index + 1}</span>
                  {name}
                  {custom ? null : <span className="aw-step-badge">Built in</span>}
                </span>
              }
              description={custom ? sizeWords(step.sizes) : undefined}
              control={
                <span className="aw-step-actions">
                  {showAppend ? null : (
                    <Button variant="ghost" size="xs" onClick={() => setAppending(step.key)}>
                      <Icon name="add" size={13} /> Add an instruction
                    </Button>
                  )}
                  {custom ? (
                    <>
                      <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Move ${name} up`} title="Move up" disabled={index === 0} onClick={() => move(index, -1)}>
                        <Icon name="arrow_upward" size={13} />
                      </button>
                      <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Move ${name} down`} title="Move down" disabled={index === steps.length - 1} onClick={() => move(index, 1)}>
                        <Icon name="arrow_downward" size={13} />
                      </button>
                      <button
                        type="button"
                        data-slot="icon-button"
                        className="aw-icon-button"
                        aria-label={`Remove ${name}`}
                        title="Remove"
                        onClick={() => onChange(steps.filter((s) => s.key !== step.key), `Removed the step ${name}`)}
                      >
                        <Icon name="delete" size={13} />
                      </button>
                    </>
                  ) : null}
                </span>
              }
            >
              {custom || showAppend ? (
                <div className="aw-step-body" data-testid={`spec-steps-row-${step.key}`}>
                  {custom ? (
                    <>
                      <CommittedTextarea
                        ariaLabel={`Instructions for ${name}`}
                        value={step.instructions ?? ''}
                        mono
                        minRows={3}
                        validate={(d) => (d.trim() ? null : 'A step needs instructions.')}
                        onCommit={(v) => patch(step.key, { instructions: v }, `Saved the instructions for ${name}`)}
                      />
                      <SizePicks label={`Sizes ${name} runs for`} value={step.sizes ?? []} onChange={(next) => patch(step.key, { sizes: next }, `${name}: ${sizeWords(next).toLowerCase()}`)} />
                    </>
                  ) : null}
                  {showAppend ? (
                    <CommittedTextarea
                      ariaLabel={`Instruction added to ${name}`}
                      placeholder="An instruction added to the end of this step's brief"
                      value={step.append ?? ''}
                      minRows={2}
                      onCommit={(v) => {
                        patch(step.key, { append: v.trim() ? v : undefined }, v.trim() ? `Saved the added instruction for ${name}` : `Removed the added instruction from ${name}`)
                        if (!v.trim()) setAppending(null)
                      }}
                    />
                  ) : null}
                </div>
              ) : null}
            </SettingsRow>
          )
        })}
      </SettingsGroup>

      <SettingsGroup title="Add a step" description="Paste the Markdown the step briefs an agent with. It joins the changes of the sizes you pick.">
        <div className="aw-step-form">
          <Field label="Title" htmlFor="new-step-title">
            <Input id="new-step-title" data-testid="spec-steps-new-title" value={title} placeholder="Security review" onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Comes" htmlFor="new-step-after">
            <MenuSelect
              id="new-step-after"
              testId="spec-steps-add-after"
              value={after}
              onChange={setAfter}
              options={[{ value: '', label: 'First' }, ...steps.map((s) => ({ value: s.key, label: `After ${stepTitle(s)}` }))]}
            />
          </Field>
          <Field label="Runs for">
            <SizePicks label="Sizes the new step runs for" value={sizes} onChange={setSizes} />
          </Field>
          <Field label="Instructions" htmlFor="new-step-markdown" error={addError ?? undefined}>
            <Textarea id="new-step-markdown" data-testid="spec-steps-new-markdown" className="font-mono aw-textarea-grow" rows={4} value={markdown} placeholder="Paste Markdown" onChange={(e) => setMarkdown(e.target.value)} />
          </Field>
          <Button size="sm" className="self-start" data-testid="spec-steps-add" disabled={!title.trim() || !markdown.trim()} onClick={addStep}>
            <Icon name="add" size={13} /> Add step
          </Button>
        </div>
      </SettingsGroup>
    </SettingsPage>
  )
}
