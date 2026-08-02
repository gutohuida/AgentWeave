export interface ConversationBanner {
  id: string
  message: string
}

interface BannerStackProps {
  banners: ConversationBanner[]
}

/**
 * Renders directly above the composer. Order is the caller's responsibility —
 * this component only renders whatever array it is given, in that order, so a
 * cleared condition drops out without reshuffling the ones that remain.
 */
export function BannerStack({ banners }: BannerStackProps) {
  if (banners.length === 0) return null

  return (
    <div data-testid="banner-stack" className="flex flex-col gap-1.5">
      {banners.map((banner) => (
        <div
          key={banner.id}
          role="alert"
          data-testid="conversation-banner"
          data-banner-id={banner.id}
          className="rounded-lg border px-3 py-2 text-xs"
          style={{
            background: 'rgba(239,68,68,0.08)',
            borderColor: 'rgba(239,68,68,0.28)',
            color: 'var(--red)',
          }}
        >
          {banner.message}
        </div>
      ))}
    </div>
  )
}
