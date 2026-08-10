import { Button } from '@/components/ui/button'

export interface ConversationBanner {
  id: string
  message: string
  /**
   * Whether this is something wrong or something offered.
   *
   * Every banner used to be red, because every banner was a problem. A checkpoint waiting to be
   * cut over to is not a problem — it is an offer, and colouring it like a failure would say the
   * opposite of what it means.
   *
   * `info` is neither: a standing statement about what this conversation is for, which the operator
   * can act on but is not being asked to. A task binding coloured as an offer would read as a
   * prompt to release it every time they open the thread.
   */
  tone?: 'problem' | 'offer' | 'info'
  /** An offer the operator can accept from the banner itself. */
  action?: {
    label: string
    onClick: () => void
    pending?: boolean
  }
  /** Declining, where declining is a real answer rather than just ignoring the banner. */
  secondaryAction?: {
    label: string
    onClick: () => void
  }
}

interface BannerStackProps {
  banners: ConversationBanner[]
}

const TONES = {
  problem: {
    background: 'color-mix(in srgb, var(--red) 8%, transparent)',
    borderColor: 'color-mix(in srgb, var(--red) 28%, transparent)',
    color: 'var(--red)',
  },
  offer: {
    background: 'color-mix(in srgb, var(--blue) 8%, transparent)',
    borderColor: 'color-mix(in srgb, var(--blue) 28%, transparent)',
    color: 'var(--blue)',
  },
  // Quieter than both, on purpose: this one is always there while the binding is, so anything
  // louder would compete with the banners that appear because something needs deciding.
  info: {
    background: 'var(--surface-3)',
    borderColor: 'var(--border)',
    color: 'var(--text-2)',
  },
} as const

/**
 * Renders directly above the composer. Order is the caller's responsibility —
 * this component only renders whatever array it is given, in that order, so a
 * cleared condition drops out without reshuffling the ones that remain.
 */
export function BannerStack({ banners }: BannerStackProps) {
  if (banners.length === 0) return null

  return (
    <div data-testid="banner-stack" className="flex flex-col gap-1.5">
      {banners.map((banner) => {
        const tone = TONES[banner.tone ?? 'problem']
        return (
          <div
            key={banner.id}
            // An offer is not an alert. Announcing it as one would interrupt a screen-reader
            // user for something that is merely available.
            role={banner.tone === 'offer' ? 'status' : 'alert'}
            data-testid="conversation-banner"
            data-banner-id={banner.id}
            data-banner-tone={banner.tone ?? 'problem'}
            className="flex items-center gap-3 rounded-lg border px-3 py-2 text-xs"
            style={{ background: tone.background, borderColor: tone.borderColor, color: tone.color }}
          >
            <span className="flex-1">{banner.message}</span>
            {banner.secondaryAction && (
              <Button
                variant="ghost"
                size="xs"
                data-testid={`banner-dismiss-${banner.id}`}
                onClick={banner.secondaryAction.onClick}
              >
                {banner.secondaryAction.label}
              </Button>
            )}
            {banner.action && (
              <Button
                variant="primary"
                size="xs"
                data-testid={`banner-action-${banner.id}`}
                disabled={banner.action.pending}
                onClick={banner.action.onClick}
              >
                {banner.action.pending ? 'Working…' : banner.action.label}
              </Button>
            )}
          </div>
        )
      })}
    </div>
  )
}
