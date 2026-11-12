import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { landOnSetting } from './landOnSetting'
import { SettingsSearchBox, SettingsSearchResults } from './SettingsSearch'
import '@/styles/settings.css'

/** Settings with their own section list, inside the content area (the app's rail stays put).
 *
 *  Replaces the rail swapping itself for a configuration menu under three names ("Environment"
 *  back link, "Configuration" heading, "Settings" item, "PROJECT CONFIGURATION" eyebrows). One
 *  page, one name, a section list on the left that never moves while the right side scrolls.
 *  Used for both Project settings and an agent's settings. */

export interface SettingsNavItem<T extends string> {
  id: T
  label: string
  icon: string
  /** A short count or state shown at the end of the item ("9", "Off"). */
  meta?: React.ReactNode
  /** The heading this item sits under; a heading shows where the group changes. Items without
   *  one sit in a single unheaded list. */
  group?: string
}

export function SettingsNavLayout<T extends string>({
  title,
  subtitle,
  back,
  items,
  active,
  onSelect,
  footer,
  agent,
  landing,
  children,
}: {
  title: string
  subtitle?: React.ReactNode
  /** A way back to where these settings belong (an agent's settings go back to its conversations). */
  back?: { label: string; onClick: () => void }
  items: ReadonlyArray<SettingsNavItem<T>>
  active: T
  onSelect: (id: T) => void
  /** A link that ends the section list, to settings of another scope (Project and agent settings
   *  point at App settings, where the operator's own settings live). */
  footer?: { label: string; icon: string; onClick: () => void }
  /** The agent whose settings these are, when they are an agent's. */
  agent?: string
  /** The setting the location names (its row's label): scrolled to, highlighted and focused. */
  landing?: string | null
  children: React.ReactNode
}) {
  const [query, setQuery] = React.useState('')
  const [landed, setLanded] = React.useState(0)
  const scrollRef = React.useRef<HTMLDivElement>(null)
  const searching = query.trim() !== ''
  React.useEffect(() => {
    if (!landing || searching || !scrollRef.current) return
    return landOnSetting(scrollRef.current, landing)
  }, [landing, active, agent, landed, searching])
  return (
    <div className="aw-settings-layout">
      <nav className="aw-settings-nav" aria-label={title}>
        {back ? (
          <button type="button" data-slot="settings-back" className="aw-settings-back" onClick={back.onClick}>
            <Icon name="arrow_left" size={13} />
            {back.label}
          </button>
        ) : null}
        <div className="aw-settings-nav-head">
          <span className="aw-settings-nav-title">{title}</span>
          {subtitle ? <span className="aw-settings-nav-sub">{subtitle}</span> : null}
        </div>
        <SettingsSearchBox value={query} onChange={setQuery} />
        <ul className="aw-settings-nav-list">
          {items.map((item, index) => (
            <li key={item.id}>
              {item.group && item.group !== items[index - 1]?.group ? <span className="aw-settings-nav-group">{item.group}</span> : null}
              <button
                type="button"
                data-slot="settings-nav-item"
                className="aw-settings-nav-item"
                data-active={item.id === active ? 'true' : 'false'}
                aria-current={item.id === active ? 'page' : undefined}
                onClick={() => onSelect(item.id)}
              >
                <Icon name={item.icon} size={14} className="aw-settings-nav-icon" />
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {item.meta !== undefined ? <span className="aw-settings-nav-meta">{item.meta}</span> : null}
              </button>
            </li>
          ))}
        </ul>
        {footer ? (
          <button type="button" data-slot="settings-nav-footer" className="aw-settings-nav-footer" onClick={footer.onClick}>
            <Icon name={footer.icon} size={13} />
            {footer.label}
          </button>
        ) : null}
      </nav>
      <div className="aw-settings-scroll" ref={scrollRef}>
        {searching ? (
          <SettingsSearchResults
            query={query}
            agent={agent}
            onChosen={() => {
              setQuery('')
              setLanded((n) => n + 1)
            }}
          />
        ) : (
          children
        )}
      </div>
    </div>
  )
}
