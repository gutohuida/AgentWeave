import type { ReactNode } from 'react'
import '@/styles/profiles.css'

/**
 * A profile's name as a way in: a real link to that profile's page, wherever its name is printed
 * (the Profiles page, the Overview's rows, a thread's bar). `href` is the page's address, so open
 * in a new tab and copy link work; a plain click calls `onOpen` instead of reloading.
 *
 * The accessible name says where the link goes ("Open Builder's profile"), and it contains the
 * visible name, so voice control by the printed name still works (vault P24, P7).
 */
export function ProfileLink({
  name,
  href,
  onOpen,
  children,
  className,
}: {
  name: string
  href: string
  onOpen: () => void
  /** What the link shows; the profile's name by default. An icon-only link passes its icon. */
  children?: ReactNode
  className?: string
}) {
  return (
    <a
      href={href}
      data-slot="profile-link"
      className={['aw-profile-link', className].filter(Boolean).join(' ')}
      aria-label={`Open ${name}’s profile`}
      onClick={(event) => {
        // Let the browser handle a new-tab or new-window click.
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
        event.preventDefault()
        event.stopPropagation()
        onOpen()
      }}
    >
      {children ?? name}
    </a>
  )
}
