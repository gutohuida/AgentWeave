import React from 'react'
import { BRAND_MARKS, BRAND_PREFIX } from './brandMarks'
import {
  Activity,
  CircleAlert,
  TriangleAlert,
  Archive,
  ArrowDown,
  ArrowLeft,
  BadgeCheck,
  ChartColumn,
  BookOpen,
  Bot,
  CalendarClock,
  Check,
  CircleCheck,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Clock,
  Cpu,
  Copy,
  FileText,
  FilePlusCorner,
  ArrowUpRight,
  Folder,
  FolderOpen,
  FolderPlus,
  FolderSearch,
  Flag,
  Globe,
  CircleQuestionMark,
  House,
  Hourglass,
  Infinity as InfinityIcon,
  Info,
  Link2,
  ListChecks,
  ListFilter,
  MessageSquare,
  Moon,
  Ellipsis,
  EllipsisVertical,
  NotebookPen,
  PanelRightClose,
  Pause,
  Pencil,
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
  Square,
  Star,
  Sun,
  Tag,
  Terminal,
  Trash2,
  UserPlus,
  Users,
  Wrench,
  X,
  Zap,
  // Generic file-type glyphs, used for the types simple-icons has no mark for (PowerShell, Java,
  // C#, plain text) and as the fallback everywhere else. Real brand marks live in `brandMarks.ts`.
  Braces,
  Container,
  Database,
  FileCodeCorner,
  FileCog,
  FileImage,
  FileBracesCorner,
  FileLock,
  FileTypeCorner,
  GitBranch,
  Hash,
  Package,
  Palette,
  ScrollText,
  Sheet,
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
  all_inclusive: InfinityIcon,
  // --- file-type glyphs (see fileIcons.ts for the extension -> name mapping) ---
  file_braces: Braces,
  file_code: FileCodeCorner,
  file_config: FileCog,
  file_container: Container,
  file_database: Database,
  file_image: FileImage,
  file_json: FileBracesCorner,
  file_lock: FileLock,
  file_markdown: ScrollText,
  file_package: Package,
  file_sheet: Sheet,
  file_style: Palette,
  file_type: FileTypeCorner,
  file_vcs: GitBranch,
  hash: Hash,
  archive: Archive,
  arrow_downward: ArrowDown,
  arrow_left: ArrowLeft,
  article: FileText,
  badge: BadgeCheck,
  bar_chart: ChartColumn,
  bolt: Zap,
  build: Wrench,
  chat: MessageSquare,
  check: Check,
  check_circle: CircleCheck,
  close: X,
  content_copy: Copy,
  dark_mode: Moon,
  delete: Trash2,
  description: FileText,
  edit: Pencil,
  edit_note: NotebookPen,
  error: CircleAlert,
  error_outline: CircleAlert,
  event_note: CalendarClock,
  expand_more: ChevronDown,
  chevron_right: ChevronRight,
  file_plus: FilePlusCorner,
  filter_list: ListFilter,
  folder: Folder,
  flag: Flag,
  flight: Plane,
  folder_open: FolderOpen,
  folder_plus: FolderPlus,
  folder_search: FolderSearch,
  group: Users,
  help: CircleQuestionMark,
  home: House,
  hourglass_top: Hourglass,
  info: Info,
  light_mode: Sun,
  link: Link2,
  list_alt: ClipboardList,
  memory: Cpu,
  menu_book: BookOpen,
  monitoring: Activity,
  more_horiz: Ellipsis,
  more_vert: EllipsisVertical,
  move_up: ArrowUpRight,
  pause: Pause,
  play_arrow: Play,
  public: Globe,
  refresh: RefreshCw,
  restart_alt: RotateCcw,
  right_panel_close: PanelRightClose,
  schedule: Clock,
  search: Search,
  send: Send,
  settings: Settings,
  smart_toy: Bot,
  star: Star,
  stop: Square,
  sync: RotateCw,
  tag: Tag,
  task_alt: ListChecks,
  person_add: UserPlus,
  terminal: Terminal,
  verified: BadgeCheck,
  verified_user: ShieldCheck,
  warning: TriangleAlert,
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

/**
 * Provider brand marks (composer/chrome refinement §4, design.md Decision 3).
 *
 * Not lucide icons — a provider's logo is a fixed trademark, not a line-icon in a
 * consistent stroke family, so these are plain inline SVG rather than another entry in
 * `ICONS` above. They still live in this module so there remains one import site for all
 * iconography, per CLAUDE.md's one-icon-system rule.
 *
 * Paths are each provider's own published mark (Anthropic's and OpenAI's), not an
 * AgentWeave or t3code asset — MIT covers the surrounding code, not these trademarks.
 * OpenAI's mark renders in `currentColor` (it is designed as a monochrome mark that
 * matches surrounding text in both themes); Anthropic's uses its own fixed brand colour
 * via `--provider-claude`, which does not vary by theme (see index.css).
 */
const PROVIDER_MARKS: Record<string, React.FC<{ size: number }>> = {
  codex: ({ size }) => (
    <svg width={size} height={size} viewBox="0 0 256 260" aria-hidden="true" fill="currentColor">
      <path d="M239.184 106.203a64.716 64.716 0 0 0-5.576-53.103C219.452 28.459 191 15.784 163.213 21.74A65.586 65.586 0 0 0 52.096 45.22a64.716 64.716 0 0 0-43.23 31.36c-14.31 24.602-11.061 55.634 8.033 76.74a64.665 64.665 0 0 0 5.525 53.102c14.174 24.65 42.644 37.324 70.446 31.36a64.72 64.72 0 0 0 48.754 21.744c28.481.025 53.714-18.361 62.414-45.481a64.767 64.767 0 0 0 43.229-31.36c14.137-24.558 10.875-55.423-8.083-76.483Zm-97.56 136.338a48.397 48.397 0 0 1-31.105-11.255l1.535-.87 51.67-29.825a8.595 8.595 0 0 0 4.247-7.367v-72.85l21.845 12.636c.218.111.37.32.409.563v60.367c-.056 26.818-21.783 48.545-48.601 48.601Zm-104.466-44.61a48.345 48.345 0 0 1-5.781-32.589l1.534.921 51.722 29.826a8.339 8.339 0 0 0 8.441 0l63.181-36.425v25.221a.87.87 0 0 1-.358.665l-52.335 30.184c-23.257 13.398-52.97 5.431-66.404-17.803ZM23.549 85.38a48.499 48.499 0 0 1 25.58-21.333v61.39a8.288 8.288 0 0 0 4.195 7.316l62.874 36.272-21.845 12.636a.819.819 0 0 1-.767 0L41.353 151.53c-23.211-13.454-31.171-43.144-17.804-66.405v.256Zm179.466 41.695-63.08-36.63L161.73 77.86a.819.819 0 0 1 .768 0l52.233 30.184a48.6 48.6 0 0 1-7.316 87.635v-61.391a8.544 8.544 0 0 0-4.4-7.213Zm21.742-32.69-1.535-.922-51.619-30.081a8.39 8.39 0 0 0-8.492 0L99.98 99.808V74.587a.716.716 0 0 1 .307-.665l52.233-30.133a48.652 48.652 0 0 1 72.236 50.391v.205ZM88.061 139.097l-21.845-12.585a.87.87 0 0 1-.41-.614V65.685a48.652 48.652 0 0 1 79.757-37.346l-1.535.87-51.67 29.825a8.595 8.595 0 0 0-4.246 7.367l-.051 72.697Zm11.868-25.58 28.138-16.217 28.188 16.218v32.434l-28.086 16.218-28.188-16.218-.052-32.434Z" />
    </svg>
  ),
  claude: ({ size }) => (
    <svg
      width={size}
      height={size}
      viewBox="0 0 256 257"
      aria-hidden="true"
      style={{ fill: 'var(--provider-claude)' }}
    >
      <path d="m50.228 170.321 50.357-28.257.843-2.463-.843-1.361h-2.462l-8.426-.518-28.775-.778-24.952-1.037-24.175-1.296-6.092-1.297L0 125.796l.583-3.759 5.12-3.434 7.324.648 16.202 1.101 24.304 1.685 17.629 1.037 26.118 2.722h4.148l.583-1.685-1.426-1.037-1.101-1.037-25.147-17.045-27.22-18.017-14.258-10.37-7.713-5.25-3.888-4.925-1.685-10.758 7-7.713 9.397.649 2.398.648 9.527 7.323 20.35 15.75L94.817 91.9l3.889 3.24 1.555-1.102.195-.777-1.75-2.917-14.453-26.118-15.425-26.572-6.87-11.018-1.814-6.61c-.648-2.723-1.102-4.991-1.102-7.778l7.972-10.823L71.42 0 82.05 1.426l4.472 3.888 6.61 15.101 10.694 23.786 16.591 32.34 4.861 9.592 2.592 8.879.973 2.722h1.685v-1.556l1.36-18.211 2.528-22.36 2.463-28.776.843-8.1 4.018-9.722 7.971-5.25 6.222 2.981 5.12 7.324-.713 4.73-3.046 19.768-5.962 30.98-3.889 20.739h2.268l2.593-2.593 10.499-13.934 17.628-22.036 7.778-8.749 9.073-9.657 5.833-4.601h11.018l8.1 12.055-3.628 12.443-11.342 14.388-9.398 12.184-13.48 18.147-8.426 14.518.778 1.166 2.01-.194 30.46-6.481 16.462-2.982 19.637-3.37 8.88 4.148.971 4.213-3.5 8.62-20.998 5.184-24.628 4.926-36.682 8.685-.454.324.519.648 16.526 1.555 7.065.389h17.304l32.21 2.398 8.426 5.574 5.055 6.805-.843 5.184-12.962 6.611-17.498-4.148-40.83-9.721-14-3.5h-1.944v1.167l11.666 11.406 21.387 19.314 26.767 24.887 1.36 6.157-3.434 4.86-3.63-.518-23.526-17.693-9.073-7.972-20.545-17.304h-1.36v1.814l4.73 6.935 25.017 37.59 1.296 11.536-1.814 3.76-6.481 2.268-7.13-1.297-14.647-20.544-15.1-23.138-12.185-20.739-1.49.843-7.194 77.448-3.37 3.953-7.778 2.981-6.48-4.925-3.436-7.972 3.435-15.749 4.148-20.544 3.37-16.333 3.046-20.285 1.815-6.74-.13-.454-1.49.194-15.295 20.999-23.267 31.433-18.406 19.702-4.407 1.75-7.648-3.954.713-7.064 4.277-6.286 25.47-32.405 15.36-20.092 9.917-11.6-.065-1.686h-.583L44.07 198.125l-12.055 1.555-5.185-4.86.648-7.972 2.463-2.593 20.35-13.999-.064.065Z" />
    </svg>
  ),
}

function providerInitials(label: string): string {
  const words = label.replace(/[_-]+/g, ' ').split(/\s+/u).filter(Boolean)
  if (words.length === 0) return '?'
  if (words.length === 1) return words[0]!.slice(0, 2).toUpperCase()
  return words.slice(0, 2).map((word) => word[0]?.toUpperCase() ?? '').join('')
}

interface ProviderMarkProps {
  /** The model catalog's provider identity (e.g. "claude", "codex") — never a hardcoded
   * literal at the call site; resolved here against the known mark set. */
  provider: string
  /** Shown for an unknown provider instead of a wrong or missing mark. */
  label: string
  size?: number
  className?: string
}

/** Every name `Icon` will render. Exported so callers that *compute* a name — `fileIcons.ts` maps
 *  a filename to one — can assert in a test that every name they can produce exists here. An
 *  unknown name renders nothing and only warns to the console, which is how `all_inclusive`
 *  shipped invisible in `JobCard`. */
export const ICON_NAMES: readonly string[] = Object.keys(ICONS)

/** A provider's brand mark, or a text-initials fallback for a provider this module has no
 * mark for — the "unknown provider falls back to a text label rather than a wrong mark"
 * contract from design.md Decision 3. */
export function ProviderMark({ provider, label, size = 14, className }: ProviderMarkProps) {
  const Mark = PROVIDER_MARKS[provider]
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center${className ? ' ' + className : ''}`}
      style={{ width: size, height: size }}
      title={label}
    >
      {Mark ? (
        <Mark size={size} />
      ) : (
        <span
          className="flex items-center justify-center rounded-full text-[8px] font-semibold leading-none"
          style={{ width: size, height: size, background: 'var(--surface-3)', color: 'var(--text-2)' }}
        >
          {providerInitials(label)}
        </span>
      )}
    </span>
  )
}

export function Icon({ name, size = 24, weight = 400, className, style }: IconProps) {
  /* A `brand:` name renders a simple-icons mark instead of a lucide glyph. Handled here rather
   * than in a separate component so every existing `<Icon name=…>` call site — the file tree, the
   * tab strip, a file tab's own header — gains brand marks without being touched, and so there
   * remains exactly one import site for iconography (the reason PROVIDER_MARKS also lives here).
   *
   * Brand marks are solid filled shapes, not stroked line icons, so `weight`/`strokeWidth` has no
   * meaning for them and is ignored. They fill with `currentColor`, so a caller that sets a colour
   * still wins; `brandHex` is what supplies the brand's own colour when the caller wants it. */
  if (name.startsWith(BRAND_PREFIX)) {
    const mark = BRAND_MARKS[name.slice(BRAND_PREFIX.length)]
    if (!mark) {
      if (!warnedNames.has(name)) {
        warnedNames.add(name)
        console.warn(`[Icon] no brand mark for "${name}"`)
      }
      return null
    }
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="currentColor"
        className={`shrink-0 select-none${className ? ' ' + className : ''}`}
        style={style}
        role="img"
        aria-label={mark.title}
      >
        <path d={mark.path} />
      </svg>
    )
  }

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
