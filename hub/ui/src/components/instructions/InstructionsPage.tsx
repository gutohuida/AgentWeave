import { useState, useEffect } from 'react'
import { useInstructions, useSaveInstructions } from '@/api/instructions'
import { readableApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Icon } from '@/components/common/Icon'
import { SettingsSection } from '@/components/environment/SettingsSection'

/**
 * The project's instructions, editable — but only once they have actually been read.
 *
 * **Why the three branches, and why in this order.** The page used to render a two-branch
 * `isLoading ? skeleton : editor`, which meant every state that is not "in flight" produced a
 * textarea seeded from `content`'s initial `''`. A failed read therefore presented an empty editor
 * over stored instructions, and one click on Save wrote the emptiness back (F271). The gate is
 * `data` present rather than `!isError`, because `data === undefined` is reached by two routes and
 * only one of them is an error: the in-flight route opens on *every* visit, and a drive measured a
 * live, enabled Save sitting beside the skeleton.
 *
 * `data` is tested **first**, not `isError`, and that ordering is load-bearing in the other
 * direction: React Query keeps the last successful `data` for a key across a failing background
 * refetch, so an `isError`-first render would yank a loaded editor out from under an operator
 * mid-edit. A refetch that fails leaves what was read on screen.
 *
 * `isLoading` is deliberately not destructured. In a `data`-first render `!data && !isError` is
 * exactly the not-yet-answered state — in flight, or the query disabled because no project is
 * selected — so binding it would only add an unused name that `--max-warnings 0` refuses.
 *
 * **Save is gated by the same test, via `actions`.** `SettingsSection` renders `actions` in its
 * heading, a sibling of the `{children}` these branches live in, so the branch below does not gate
 * it and `disabled` would not either: an inert button still leaves the two `data === undefined`
 * routes to be closed by markup rather than by the write never being possible.
 */
export function InstructionsPage() {
  const { data, isError, error, refetch } = useInstructions()
  const saveMutation = useSaveInstructions()
  const [content, setContent] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (data) {
      setContent(data.content)
    }
  }, [data])

  useEffect(() => {
    if (saveMutation.isSuccess) {
      setSaved(true)
      const timer = setTimeout(() => setSaved(false), 2000)
      return () => clearTimeout(timer)
    }
  }, [saveMutation.isSuccess])

  const handleSave = () => {
    saveMutation.mutate(content)
  }

  return (
    <SettingsSection
      title="Instructions"
      description="These rules are prepended to every agent's role guide at session start."
      actions={data ? (
        <div className="flex items-center gap-3">
          {saved && <span role="status" className="flex items-center gap-1 text-xs" style={{ color: 'var(--green)' }}><Icon name="check" size={13} />Saved</span>}
          <Button variant="primary" size="sm" onClick={handleSave} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      ) : undefined}
    >
      {data ? (
        <div className="py-4">
          <Textarea
            aria-label="Project instructions"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Enter project-wide instructions here..."
            className="min-h-[400px] w-full resize-y p-4 font-mono text-sm leading-relaxed"
            style={{
              background: 'var(--surface)',
            }}
            spellCheck={false}
          />
          {/* A rejected PUT used to re-enable the button and say nothing at all, leaving the
              operator believing the save landed — a breach of *Saving reports its outcome*, which
              this component has always been bound by. */}
          {saveMutation.isError && (
            <div
              role="alert"
              className="mt-4 flex items-start gap-2 rounded-md px-4 py-3 text-xs leading-relaxed"
              style={{ background: 'var(--surface-2)', border: '1px solid var(--red)', color: 'var(--red)' }}
            >
              <Icon name="alert_triangle" size={15} className="mt-0.5 shrink-0" />
              <span>
                <strong>These instructions were not saved.</strong>{' '}
                {readableApiError(saveMutation.error, 'The Hub did not return a reason.')}{' '}
                What you typed is still here — press Save to try again.
              </span>
            </div>
          )}
          <div
            className="mt-4 flex items-start gap-2 rounded-md px-4 py-3"
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              color: 'var(--text-3)',
              fontSize: 12,
            }}
          >
            <Icon name="info" size={15} className="mt-0.5 shrink-0" />
            <span><strong style={{ color: 'var(--text-2)' }}>Session boundary.</strong> Changes take effect when agents start a new session. Running sessions are not affected.</span>
          </div>
        </div>
      ) : isError ? (
        /* Stated inside `{children}`, never in place of the whole section: the section's title and
           its statement of what it governs are rendered by `SettingsSection`'s heading, and
           *A configuration section states what it governs* requires them in every state. */
        <div
          role="alert"
          className="my-4 flex items-start gap-2 rounded-md px-4 py-3 text-xs leading-relaxed"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--red)', color: 'var(--text-2)' }}
        >
          <Icon name="alert_triangle" size={15} className="mt-0.5 shrink-0" style={{ color: 'var(--red)' }} />
          <div className="min-w-0 flex-1">
            <div style={{ color: 'var(--red)' }}>
              <strong>This project&apos;s instructions could not be loaded.</strong>
            </div>
            {/* A dropped connection produces no `ApiError`, so there is no server sentence to
                quote and the fallback is what shows. The reassurance below is stated
                unconditionally rather than only in that fallback, so it also holds for an error
                response that does carry a body. */}
            <p className="mt-1">{readableApiError(error, 'The Hub did not return a reason.')}</p>
            <p className="mt-1" style={{ color: 'var(--text-3)' }}>
              Nothing stored has been changed. The editor stays hidden rather than showing an empty
              one, so it cannot overwrite instructions it never read.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => { void refetch() }}
            >
              Retry
            </Button>
          </div>
        </div>
      ) : (
        <div aria-label="Loading instructions" className="space-y-3 py-4">
          <div className="skeleton h-[400px] w-full" />
          <div className="skeleton h-12 w-full" />
        </div>
      )}
    </SettingsSection>
  )
}
