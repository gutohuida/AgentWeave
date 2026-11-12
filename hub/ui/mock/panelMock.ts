import type { DiffFile } from '@/components/common/DiffView'
import type { ChangeMark } from '@/components/panel/FilesTab'

// mock state: the replica records no workspace listing, diffs or shell, so the Changes, Files and
// Terminal tabs are fed this hand-written Terra checkout. The agent is mid-way through the build's
// "Desktop window and projects" task.

export const BASE_BRANCH = 'master'

const ROOT_PATHS = [
  'README.md',
  'package.json',
  'tsconfig.json',
  '.gitignore',
  'docs/architecture.md',
  'docs/plugins.md',
  'src/main.ts',
  'src/app/App.tsx',
  'src/app/routes.ts',
  'src/app/projects/ProjectList.tsx',
  'src/app/projects/projectStore.ts',
  'src/app/plugins/PluginHost.tsx',
  'src/app/plugins/manifest.ts',
  'src/desktop/tray.ts',
  'src/desktop/menu.ts',
  'src/styles/app.css',
  'tests/projects.test.ts',
  'tests/manifest.test.ts',
]

/** The project root: master as checked out in the project directory. */
export const ROOT_FILES = ROOT_PATHS

/** The agent's worktree: the root plus what its branch added, minus what it deleted. */
export const WORKTREE_FILES = [...ROOT_PATHS.filter((p) => p !== 'src/desktop/menu.ts'), 'src/desktop/window.ts', 'src/app/projects/ProjectSwitcher.tsx', 'tests/window.test.ts']

const PATCHES = {
  window: `diff --git a/src/desktop/window.ts b/src/desktop/window.ts
new file mode 100644
--- /dev/null
+++ b/src/desktop/window.ts
@@ -0,0 +1,14 @@
+import { BrowserWindow } from 'electron'
+import { lastBounds, saveBounds } from './bounds'
+
+/** The one desktop window. It reopens where the operator left it. */
+export function openMainWindow(url: string): BrowserWindow {
+  const win = new BrowserWindow({ ...lastBounds(), minWidth: 960, minHeight: 600, show: false })
+  win.once('ready-to-show', () => win.show())
+  win.on('close', () => saveBounds(win.getBounds()))
+  void win.loadURL(url)
+  return win
+}`,
  switcher: `diff --git a/src/app/projects/ProjectSwitcher.tsx b/src/app/projects/ProjectSwitcher.tsx
new file mode 100644
--- /dev/null
+++ b/src/app/projects/ProjectSwitcher.tsx
@@ -0,0 +1,9 @@
+import { useProjects } from './projectStore'
+
+export function ProjectSwitcher() {
+  const { projects, current, open } = useProjects()
+  return (
+    <select value={current?.id} onChange={(e) => open(e.target.value)}>
+      {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
+    </select>
+  )`,
  store: `diff --git a/src/app/projects/projectStore.ts b/src/app/projects/projectStore.ts
--- a/src/app/projects/projectStore.ts
+++ b/src/app/projects/projectStore.ts
@@ -12,9 +12,14 @@ export interface Project {
   id: string
   name: string
   path: string
+  /** When it was last opened, for the switcher's order. */
+  openedAt: number | null
 }

-export const useProjects = create<ProjectState>(() => ({ projects: [], current: null }))
+export const useProjects = create<ProjectState>((set) => ({
+  projects: [],
+  current: null,
+  open: (id) => set((s) => ({ current: s.projects.find((p) => p.id === id) ?? null })),
+}))`,
  main: `diff --git a/src/main.ts b/src/main.ts
--- a/src/main.ts
+++ b/src/main.ts
@@ -1,8 +1,7 @@
 import { app } from 'electron'
-import { buildMenu } from './desktop/menu'
+import { openMainWindow } from './desktop/window'
 import { createTray } from './desktop/tray'

 app.whenReady().then(() => {
-  buildMenu()
   createTray()
+  openMainWindow(process.env.TERRA_URL ?? 'http://localhost:5173')
 })`,
  menu: `diff --git a/src/desktop/menu.ts b/src/desktop/menu.ts
deleted file mode 100644
--- a/src/desktop/menu.ts
+++ /dev/null
@@ -1,6 +0,0 @@
-import { Menu } from 'electron'
-
-/** The old application menu, replaced by the window's own controls. */
-export function buildMenu(): void {
-  Menu.setApplicationMenu(null)
-}`,
  test: `diff --git a/tests/window.test.ts b/tests/window.test.ts
new file mode 100644
--- /dev/null
+++ b/tests/window.test.ts
@@ -0,0 +1,7 @@
+import { openMainWindow } from '../src/desktop/window'
+
+test('the window reopens at its last size', () => {
+  const win = openMainWindow('about:blank')
+  expect(win.getBounds().width).toBeGreaterThanOrEqual(960)
+})
+`,
}

/** What the agent's last turn changed. */
export const TURN_CHANGES: DiffFile[] = [
  { path: 'src/desktop/window.ts', status: 'A', patch: PATCHES.window },
  { path: 'src/main.ts', status: 'M', patch: PATCHES.main },
  { path: 'src/desktop/menu.ts', status: 'D', patch: PATCHES.menu },
]

/** Everything on the agent's branch since it left master. */
export const BRANCH_CHANGES: DiffFile[] = [
  ...TURN_CHANGES,
  { path: 'src/app/projects/ProjectSwitcher.tsx', status: 'A', patch: PATCHES.switcher },
  { path: 'src/app/projects/projectStore.ts', status: 'M', patch: PATCHES.store },
  { path: 'tests/window.test.ts', status: 'A', patch: PATCHES.test },
]

export const CHANGE_MARKS: Record<string, ChangeMark> = Object.fromEntries(BRANCH_CHANGES.map((f) => [f.path, f.status as ChangeMark]))

/** File bodies the mock can open; any other file shows a short stand-in. */
export const FILE_CONTENT: Record<string, string> = {
  'README.md': `# Terra

Terra is the desktop control centre for the agents working on your projects.

## Running it

1. \`npm install\`
2. \`npm run dev\` starts the app against a local Hub.

## Plugins

Each project can load plugins; see [docs/plugins.md](docs/plugins.md).

| Command | What it does |
|---|---|
| \`npm run dev\` | The app, reloading as you edit |
| \`npm test\` | Every test |
`,
  'src/desktop/window.ts': PATCHES.window
    .split('\n')
    .filter((l) => l.startsWith('+') && !l.startsWith('+++'))
    .map((l) => l.slice(1))
    .join('\n'),
}

export function contentFor(path: string): string {
  return FILE_CONTENT[path] ?? `// ${path}\n// (the mock holds the full text of README.md and src/desktop/window.ts only)\n`
}

/** A recorded shell session: [text, tone] per line. */
export const TERMINAL_LINES: Array<[string, 'prompt' | 'out' | 'ok' | 'err' | 'dim']> = [
  ['PowerShell 7.5.2', 'dim'],
  ['PS C:\\Users\\huida\\Projects\\Terra\\.agentweave\\worktrees\\Builder> git status --short', 'prompt'],
  [' M src/main.ts', 'out'],
  [' D src/desktop/menu.ts', 'out'],
  ['?? src/desktop/window.ts', 'out'],
  ['PS C:\\Users\\huida\\Projects\\Terra\\.agentweave\\worktrees\\Builder> npm test -- window', 'prompt'],
  ['', 'out'],
  ['> terra@0.4.0 test', 'dim'],
  ['> vitest run window', 'dim'],
  ['', 'out'],
  [' ✓ tests/window.test.ts (1 test) 41ms', 'ok'],
  ['', 'out'],
  [' Test Files  1 passed (1)', 'ok'],
  ['      Tests  1 passed (1)', 'ok'],
  ['PS C:\\Users\\huida\\Projects\\Terra\\.agentweave\\worktrees\\Builder> ', 'prompt'],
]

export const WORKTREE_DIR = 'C:\\Users\\huida\\Projects\\Terra\\.agentweave\\worktrees\\'
export const ROOT_DIR = 'C:\\Users\\huida\\Projects\\Terra'
