/** The pure rules of the Team-lanes Overview: how profiles are ordered and how their spend compares.
 *  No React, so a test can pin them. */

export type LaneStatus = 'working' | 'idle' | 'waiting' | 'stalled'

export interface LaneOrderKey {
  status: LaneStatus
  asks: number
  name: string
}

const STATUS_RANK: Record<LaneStatus, number> = { waiting: 0, stalled: 1, working: 2, idle: 3 }

const needsYou = (l: LaneOrderKey) => l.asks > 0 || l.status === 'waiting' || l.status === 'stalled'

/** Needs-you first (a profile waiting on you, stalled, or holding open questions), then working,
 *  then idle; ties by name so a refresh never shuffles lanes. */
export function compareLanes(a: LaneOrderKey, b: LaneOrderKey): number {
  return (needsYou(a) ? 0 : 1) - (needsYou(b) ? 0 : 1) || STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.asks - a.asks || a.name.localeCompare(b.name)
}

/** Each lane's share of the largest spend today, 0..1. Null spend stays null (unknown, never zero). */
export function spendShare(spend: number | null, all: (number | null)[]): number | null {
  if (spend == null) return null
  const max = Math.max(0, ...all.filter((v): v is number => v != null))
  return max > 0 ? spend / max : 0
}