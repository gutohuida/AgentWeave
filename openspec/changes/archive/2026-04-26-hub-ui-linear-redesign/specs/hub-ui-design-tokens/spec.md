## ADDED Requirements

### Requirement: CSS token set replaces Material Design 3 tokens
The system SHALL define all visual design values as CSS custom properties in `hub/ui/src/index.css`. All M3 tokens (`--p-cont`, `--on-p-cont`, `--s-cont`, `--on-s-cont`, `--t-cont`, `--on-t-cont`, `--sur-var`, `--on-sv`, `--surface-lowest`, `--surface-low`, `--surface-high`, `--surface-highest`, `--elev-1`, `--elev-2`, `--elev-3`, `--m-divider`, `--hover-overlay`, `--card-hover-shadow`) SHALL be removed. All `m3-*` CSS utility class definitions SHALL be removed from `index.css`.

#### Scenario: Dark mode token values are defined
- **WHEN** `[data-mode="dark"]` or no mode attribute is set on `<html>`
- **THEN** the following tokens are available with these exact values:
  - `--bg: #09090b`
  - `--surface: #111113`
  - `--surface-2: #18181b`
  - `--surface-3: #27272a`
  - `--border: rgba(255,255,255,0.08)`
  - `--border-hi: rgba(255,255,255,0.12)`
  - `--text: #fafafa`
  - `--text-2: #a1a1aa`
  - `--text-3: #71717a`
  - `--green: #22c55e`
  - `--amber: #f59e0b`
  - `--red: #ef4444`
  - `--blue: #3b82f6`
  - `--purple: #a855f7`
  - `--radius: 6px`
  - `--radius-sm: 4px`
  - `--radius-lg: 8px`
  - `--destructive: #ef4444`
  - `--destructive-fg: #ffffff`

#### Scenario: Light mode token values are defined
- **WHEN** `[data-mode="light"]` is set on `<html>`
- **THEN** the following tokens are overridden:
  - `--bg: #ffffff`
  - `--surface: #fafafa`
  - `--surface-2: #f4f4f5`
  - `--surface-3: #e4e4e7`
  - `--border: rgba(0,0,0,0.08)`
  - `--border-hi: rgba(0,0,0,0.12)`
  - `--text: #09090b`
  - `--text-2: #52525b`
  - `--text-3: #a1a1aa`
  - All semantic colors (`--green`, `--amber`, `--red`, `--blue`, `--purple`) unchanged

#### Scenario: No M3 token is used anywhere in the codebase
- **WHEN** a developer runs `grep -r 'var(--p-cont\|--on-p-cont\|--s-cont\|--on-s-cont\|--elev-\|--surface-low\|--surface-high\|--sur-var\|--on-sv\|--m-divider)' hub/ui/src/`
- **THEN** the command returns zero matches

#### Scenario: No M3 utility class is used anywhere in the codebase
- **WHEN** a developer runs `grep -r 'm3-' hub/ui/src/`
- **THEN** the command returns zero matches

### Requirement: Body font defaults to Inter, monospace font to JetBrains Mono
The `<body>` element SHALL use Inter as its primary font family. Code and timestamp elements SHALL use JetBrains Mono. Both fonts SHALL be loaded from Google Fonts in `hub/ui/index.html`.

#### Scenario: Inter font is loaded
- **WHEN** the page loads
- **THEN** the browser loads Inter with weights 400, 500, and 600 from Google Fonts

#### Scenario: JetBrains Mono font is loaded
- **WHEN** the page loads
- **THEN** the browser loads JetBrains Mono with weights 400 and 500 from Google Fonts

#### Scenario: Body uses Inter
- **WHEN** any body text is rendered
- **THEN** the computed `font-family` is Inter (or the system sans-serif fallback if unavailable)

#### Scenario: Log/timestamp elements use JetBrains Mono
- **WHEN** a log timestamp or inline code element is rendered
- **THEN** the computed `font-family` is JetBrains Mono (or the system monospace fallback)

### Requirement: Semantic color usage is consistent across all components
Colors SHALL only be used for semantic meaning. `--green` is used exclusively for running/success/ok states. `--amber` is used exclusively for waiting/warning/blocked states. `--red` is used exclusively for error/rejected/critical states. `--blue` is used exclusively for primary actions and the principal role tag. `--purple` is used exclusively for dev role tags and secondary labels. No decorative or arbitrary color is used.

#### Scenario: Running agent renders a green status dot
- **WHEN** an agent has `status === 'running'` or `status === 'active'`
- **THEN** its status indicator renders using `--green`

#### Scenario: Waiting agent renders an amber status dot
- **WHEN** an agent has `status === 'waiting'`
- **THEN** its status indicator renders using `--amber`

#### Scenario: Idle agent renders a muted status dot
- **WHEN** an agent has `status === 'idle'`
- **THEN** its status indicator renders using `--surface-3` (muted gray)
