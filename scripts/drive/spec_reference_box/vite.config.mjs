// The harness page for scripts/drive/spec_reference_box.py: mounts the app's real Composer
// (hub/ui/src/components/agents/Composer.tsx) alone, with no Hub. Run from hub/ui so the
// plugin and React resolve from its node_modules; never touches hub/hub/static/ui.
import { realpathSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const ui = path.resolve(here, '../../../hub/ui')
const req = createRequire(path.join(ui, 'package.json'))
const { default: react } = await import(pathToFileURL(req.resolve('@vitejs/plugin-react')).href)
const mod = (name) => path.join(ui, 'node_modules', name)

export default {
  root: here,
  configFile: false,
  // Vite's prebundle cache goes under hub/ui/node_modules (ignored), never into this tracked tree.
  cacheDir: path.join(ui, 'node_modules', '.vite-spec-reference-box'),
  plugins: [react()],
  // The app's stylesheet goes through the app's own PostCSS (Tailwind) config.
  css: { postcss: ui },
  resolve: {
    alias: [
      { find: '@', replacement: path.join(ui, 'src') },
      { find: /^react$/, replacement: mod('react') },
      { find: /^react\/(.*)$/, replacement: mod('react') + '/$1' },
      { find: /^react-dom$/, replacement: mod('react-dom') },
      { find: /^react-dom\/(.*)$/, replacement: mod('react-dom') + '/$1' },
      { find: /^@tanstack\/react-query$/, replacement: mod('@tanstack/react-query') },
    ],
    dedupe: ['react', 'react-dom'],
  },
  // node_modules may be a junction to another checkout's; its real path serves the app's fonts.
  server: { fs: { allow: [path.resolve(here, '../../..'), realpathSync(path.join(ui, 'node_modules'))] } },
  logLevel: 'warn',
}
