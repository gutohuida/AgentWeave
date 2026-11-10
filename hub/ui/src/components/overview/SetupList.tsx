import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import '@/styles/setup.css'

/**
 * What a project still needs before it can do its work (`a-project-says-what-it-still-needs`):
 * its folder found, a git repository, an agent, and every agent able to run. Shown at the top of
 * Overview and of Project settings while anything is left; each item opens what resolves it.
 * Presentational: the container works the items out from the Hub's state.
 */

export type SetupItemKey = 'folder' | 'repository' | 'agent' | 'can-run'

export interface SetupItem {
  /** One per kind, except `can-run`, which is one per agent that cannot run. */
  id: string
  key: SetupItemKey
  title: string
  detail: string
  action: { label: string; onClick: () => void }
  /** Only the repository item may be dismissed: without the others nothing works. */
  dismissable?: boolean
}

const ICON: Record<SetupItemKey, string> = {
  folder: 'folder',
  repository: 'call_split',
  agent: 'person_add',
  'can-run': 'terminal',
}

export function SetupList({
  items,
  dismissed = [],
  place,
  onDismiss,
  onRestore,
}: {
  items: SetupItem[]
  /** Items the operator dismissed; listed (with a way back) only in settings. */
  dismissed?: SetupItem[]
  place: 'overview' | 'settings'
  onDismiss?: (item: SetupItem) => void
  onRestore?: (item: SetupItem) => void
}) {
  const restorable = place === 'settings' ? dismissed : []
  if (!items.length && !restorable.length) return null
  return (
    <section className="aw-setup" data-place={place} aria-label="Still to set up" data-testid="setup-list">
      {items.length ? (
        <>
          <header className="aw-setup-head">
            <h2 className="aw-setup-title">
              {items.length === 1 ? 'One thing before this project can work' : `${items.length} things before this project can work`}
            </h2>
          </header>
          <ul className="aw-setup-items">
            {items.map((item) => (
              <li key={item.id} className="aw-setup-item" data-testid={`setup-item-${item.id}`} data-key={item.key}>
                <span className="aw-setup-icon" aria-hidden="true">
                  <Icon name={ICON[item.key]} size={14} />
                </span>
                <div className="aw-setup-body">
                  <p className="aw-setup-item-title">{item.title}</p>
                  <p className="aw-setup-item-detail">{item.detail}</p>
                </div>
                <span className="aw-setup-actions">
                  {item.dismissable && onDismiss ? (
                    <Button variant="ghost" size="xs" onClick={() => onDismiss(item)}>
                      Not for this project
                    </Button>
                  ) : null}
                  <Button variant="outline" size="sm" onClick={item.action.onClick}>
                    {item.action.label}
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {restorable.length ? (
        <p className="aw-setup-dismissed">
          {restorable.map((item) => (
            <span key={item.id}>
              Dismissed: {item.title.toLowerCase()}.{' '}
              {onRestore ? (
                <button type="button" data-slot="link" className="aw-link aw-link-inline" onClick={() => onRestore(item)}>
                  Show it again
                </button>
              ) : null}
            </span>
          ))}
        </p>
      ) : null}
    </section>
  )
}

/** The rail's mark: how many items are left, naming them on hover. Not a control of its own: it
 *  sits inside the project's row, which opens Overview. */
export function SetupCount({ titles }: { titles: string[] }) {
  if (!titles.length) return null
  const label = `${titles.length} to set up: ${titles.join('; ')}`
  return (
    <span className="aw-setup-count" data-testid="setup-count" role="img" aria-label={label} title={label}>
      {titles.length}
    </span>
  )
}
