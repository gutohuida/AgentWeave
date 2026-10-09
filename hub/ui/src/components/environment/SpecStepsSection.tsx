import { useEffect, useState, type ReactNode } from 'react'
import { readableApiError } from '@/api/client'
import {
  useProjectJourney,
  useSaveProjectJourney,
  type JourneyStep,
  type SpecSize,
} from '@/api/spec'
import { Button } from '@/components/ui/button'
import { SettingsSection } from '@/components/environment/SettingsSection'

const SIZES: SpecSize[] = ['fix', 'small', 'large']
const DEFAULT_NEW_SIZES: SpecSize[] = ['small', 'large']
const MAX_KEY = 48
const field = 'control-field block px-2 py-1.5 text-xs'

/** A settings row with its controls under the label rather than beside it: a step holds Markdown,
 *  which needs the width the label column would take. */
function StepRow({
  label,
  description,
  children,
}: {
  label: string
  description: string
  children: ReactNode
}) {
  return (
    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
      <div className="min-w-0">
        <div className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{label}</div>
        <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-3)' }}>{description}</p>
      </div>
      {children}
    </div>
  )
}

/** A step is custom when it carries its own text; a built-in step is its key alone. */
const isCustom = (step: JourneyStep) => step.instructions !== undefined

/** The key a title gives a custom step: a lowercase slug, the form the Hub accepts. */
function slug(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_KEY)
    .replace(/-+$/, '')
}

/** What goes on the wire: built-in steps by key (plus an appended instruction), custom steps with
 *  their text and sizes. Only what a step holds, so saving an unchanged journey sends what it read. */
function toEntry(step: JourneyStep): JourneyStep {
  const append = step.append?.trim() ? { append: step.append } : {}
  if (!isCustom(step)) return { key: step.key, ...append }
  return {
    key: step.key,
    title: step.title,
    instructions: step.instructions,
    sizes: step.sizes,
    ...append,
  }
}

/**
 * The project's spec steps (`a-project-orders-its-own-spec-steps`, FR-6): the steps a change walks
 * in order, with the operator's own steps among them. Paste Markdown to insert a step at any
 * position, append an instruction to any step, remove or move a custom step, then save; the Hub
 * validates the whole list and writes `spec/journey.json`. The seven built-in steps stay, in their
 * order — the Hub refuses a list that drops or reorders them.
 */
export function SpecStepsSection() {
  const { data, error: loadError } = useProjectJourney()
  const save = useSaveProjectJourney()
  // The operator's unsaved edits; null shows what the Hub last answered, so the list is there on
  // the first render that has data, not one effect later.
  const [draft, setDraft] = useState<JourneyStep[] | null>(null)
  const steps = draft ?? data?.steps ?? []
  const setSteps = (change: (current: JourneyStep[]) => JourneyStep[]) =>
    setDraft((current) => change(current ?? data?.steps ?? []))
  const [after, setAfter] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [sizes, setSizes] = useState<SpecSize[]>(DEFAULT_NEW_SIZES)
  const [addError, setAddError] = useState<string | null>(null)

  // A fresh answer (our own save, or another surface's) replaces the edits.
  useEffect(() => setDraft(null), [data])

  const patch = (key: string, change: Partial<JourneyStep>) =>
    setSteps((current) => current.map((s) => (s.key === key ? { ...s, ...change } : s)))
  const move = (index: number, by: number) =>
    setSteps((current) => {
      const next = [...current]
      const [item] = next.splice(index, 1)
      next.splice(index + by, 0, item)
      return next
    })

  const addStep = () => {
    const key = slug(title)
    if (!key) return setAddError('The title needs at least one letter or digit to make a key from.')
    if (steps.some((s) => s.key === key)) {
      return setAddError(`A step with the key ${key} already exists; give this one another title.`)
    }
    // `after` null means "after the last step"; '' means before the first.
    const at = after === '' ? 0 : steps.findIndex((s) => s.key === (after ?? steps[steps.length - 1]?.key)) + 1
    const entry: JourneyStep = {
      key,
      title: title.trim(),
      instructions: markdown.trim(),
      sizes: SIZES.filter((s) => sizes.includes(s)),
    }
    setSteps((current) => [...current.slice(0, at), entry, ...current.slice(at)])
    setTitle('')
    setMarkdown('')
    setSizes(DEFAULT_NEW_SIZES)
    setAddError(null)
  }

  const diagnostics = data?.diagnostics ?? []
  const canAdd = title.trim() !== '' && markdown.trim() !== ''

  return (
    <SettingsSection
      title="Spec steps"
      description="The steps a spec change walks, in order. Add your own by pasting Markdown, append an instruction to any step, then save."
      actions={(
        <Button
          type="button"
          variant="primary"
          size="sm"
          data-testid="spec-steps-save"
          disabled={save.isPending || !data}
          onClick={() => save.mutate({ steps: steps.map(toEntry) })}
        >
          Save steps
        </Button>
      )}
    >
      {loadError && (
        <div data-testid="spec-steps-load-error" role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>
          {readableApiError(loadError, "This project's spec steps could not be read.")}
        </div>
      )}
      {!data && !loadError && <div aria-label="Loading spec steps" className="skeleton my-4 h-[58px] w-full" />}
      {data && (
      <div data-testid="spec-steps">
        {diagnostics.length > 0 && (
          <div data-testid="spec-steps-diagnostics" role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>
            {diagnostics.map((d) => <p key={d.message}>{d.message}</p>)}
            <p>Until it is fixed, changes are briefed with the built-in steps.</p>
          </div>
        )}
        {steps.map((step, index) => {
          const custom = isCustom(step)
          return (
            <StepRow
              key={step.key}
              label={custom ? (step.title ?? step.key) : step.key}
              description={custom ? `Your step · ${step.key} · ${(step.sizes ?? []).join(', ')}` : 'Built in'}
            >
              <div data-testid={`spec-steps-row-${step.key}`} className="w-full space-y-1.5">
                {custom && (
                  <textarea
                    aria-label={`Instructions for ${step.key}`}
                    value={step.instructions}
                    rows={4}
                    onChange={(event) => patch(step.key, { instructions: event.target.value })}
                    className={`${field} w-full font-mono`}
                  />
                )}
                <textarea
                  aria-label={`Instruction appended to ${step.key}`}
                  placeholder="Append an instruction to this step"
                  value={step.append ?? ''}
                  rows={2}
                  onChange={(event) => patch(step.key, { append: event.target.value })}
                  className={`${field} w-full`}
                />
                {custom && (
                  <div className="flex items-center gap-1.5">
                    <Button type="button" variant="ghost" size="sm" aria-label={`Move ${step.key} up`} disabled={index === 0} onClick={() => move(index, -1)}>↑</Button>
                    <Button type="button" variant="ghost" size="sm" aria-label={`Move ${step.key} down`} disabled={index === steps.length - 1} onClick={() => move(index, 1)}>↓</Button>
                    <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${step.key}`} onClick={() => setSteps((current) => current.filter((s) => s.key !== step.key))}>✕</Button>
                  </div>
                )}
              </div>
            </StepRow>
          )
        })}

        <StepRow label="Add a step" description="Paste the Markdown the step should brief an agent with. It joins the journeys of the sizes you tick.">
          <div className="w-full space-y-1.5">
            <div className="flex items-center gap-1.5">
              <select
                aria-label="Add after"
                data-testid="spec-steps-add-after"
                value={after ?? steps[steps.length - 1]?.key ?? ''}
                onChange={(event) => setAfter(event.target.value)}
                className={`${field} w-56`}
              >
                <option value="">At the start</option>
                {steps.map((s) => <option key={s.key} value={s.key}>After {s.key}</option>)}
              </select>
              <input
                aria-label="New step title"
                data-testid="spec-steps-new-title"
                placeholder="Title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className={`${field} flex-1`}
              />
            </div>
            <textarea
              aria-label="New step Markdown"
              data-testid="spec-steps-new-markdown"
              placeholder="Paste Markdown"
              rows={5}
              value={markdown}
              onChange={(event) => setMarkdown(event.target.value)}
              className={`${field} w-full font-mono`}
            />
            <div className="flex items-center gap-3 text-xs">
              {SIZES.map((size) => (
                <label key={size} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    className="control-choice"
                    data-testid={`spec-steps-new-size-${size}`}
                    checked={sizes.includes(size)}
                    onChange={(event) =>
                      setSizes((current) =>
                        event.target.checked ? [...current, size] : current.filter((s) => s !== size),
                      )
                    }
                  />
                  {size}
                </label>
              ))}
              <Button type="button" variant="outline" size="sm" data-testid="spec-steps-add" disabled={!canAdd} onClick={addStep}>
                Add step
              </Button>
            </div>
            {addError && (
              <p data-testid="spec-steps-add-error" role="alert" className="text-xs" style={{ color: 'var(--red)' }}>
                {addError}
              </p>
            )}
          </div>
        </StepRow>

        {save.isSuccess && <div role="status" className="py-3 text-xs" style={{ color: 'var(--green)' }}>Steps saved.</div>}
        {save.error && (
          <div data-testid="spec-steps-refusal" role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>
            {readableApiError(save.error, 'The steps could not be saved.')}
          </div>
        )}
      </div>
      )}
    </SettingsSection>
  )
}
