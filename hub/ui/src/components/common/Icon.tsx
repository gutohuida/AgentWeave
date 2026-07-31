import React from 'react'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  BadgeCheck,
  BarChart3,
  BookOpen,
  Bot,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Clock,
  Cpu,
  FileText,
  FolderOpen,
  HelpCircle,
  Home,
  Info,
  ListChecks,
  ListFilter,
  MessageSquare,
  PanelRightClose,
  Pause,
  Plane,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  RotateCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Tag,
  Terminal,
  Trash2,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react'

/**
 * Single icon system for the Hub.
 *
 * This previously wrapped the Material Symbols Rounded variable font, loaded
 * from a third-party stylesheet with `display=block` — which held every icon
 * invisible until that network request completed. Icons are now SVG components
 * bundled with the app.
 *
 * The `name` API is preserved deliberately so the existing call sites are
 * unchanged by the migration.
 */
const ICONS: Record<string, LucideIcon> = {
  add: Plus,
  arrow_downward: ArrowDown,
  article: FileText,
  badge: BadgeCheck,
  bar_chart: BarChart3,
  bolt: Zap,
  chat: MessageSquare,
  check: Check,
  check_circle: CheckCircle2,
  close: X,
  delete: Trash2,
  description: FileText,
  error: AlertCircle,
  error_outline: AlertCircle,
  event_note: CalendarClock,
  expand_more: ChevronDown,
  filter_list: ListFilter,
  flight: Plane,
  folder_open: FolderOpen,
  help: HelpCircle,
  home: Home,
  info: Info,
  list_alt: ClipboardList,
  memory: Cpu,
  menu_book: BookOpen,
  monitoring: Activity,
  pause: Pause,
  play_arrow: Play,
  refresh: RefreshCw,
  restart_alt: RotateCcw,
  right_panel_close: PanelRightClose,
  schedule: Clock,
  search: Search,
  send: Send,
  settings: Settings,
  smart_toy: Bot,
  sync: RotateCw,
  tag: Tag,
  task_alt: ListChecks,
  terminal: Terminal,
  verified: BadgeCheck,
  verified_user: ShieldCheck,
  warning: AlertTriangle,
  x: X,
}

const warnedNames = new Set<string>()

interface IconProps {
  name: string
  size?: number
  /** Retained for call-site compatibility; has no effect on SVG icons. */
  fill?: 0 | 1
  /** Stroke weight. The former Material `wght` scale is mapped onto it. */
  weight?: number
  className?: string
  style?: React.CSSProperties
}

export function Icon({ name, size = 24, weight = 400, className, style }: IconProps) {
  const Glyph = ICONS[name]

  if (!Glyph) {
    // Unknown name: render nothing rather than a broken glyph or literal text.
    // Warn once per name so a missing mapping is visible without flooding the
    // console on every re-render.
    if (!warnedNames.has(name)) {
      warnedNames.add(name)
      console.warn(`[Icon] no mapping for "${name}"`)
    }
    return null
  }

  // Material weights run 100–700 around a 400 default; lucide stroke widths
  // run roughly 1–3 around 2.
  const strokeWidth = Math.max(1, Math.min(3, (weight / 400) * 2))

  return (
    <Glyph
      size={size}
      strokeWidth={strokeWidth}
      className={`shrink-0 select-none${className ? ' ' + className : ''}`}
      style={style}
      aria-hidden="true"
    />
  )
}
