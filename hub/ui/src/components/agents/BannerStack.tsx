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
   */
  tone?: 'problem' | 'offer'
  /** An offer the operator can accept from the banner itself. */
  action?: {
    label: string
    onClick: () => void
    pending?: boolean
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
