// Fills in any mock/fixtures/*.json that is missing from mock/fixtures-stub/, so the mock loads and
// typechecks on a fresh checkout. The recorded fixtures are the operator's own data and gitignored;
// a recorded file is never overwritten. Record real ones with the mock/record_*.py scripts.
import { copyFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const from = join(here, 'fixtures-stub')
const to = join(here, 'fixtures')
mkdirSync(to, { recursive: true })
for (const f of readdirSync(from)) {
  if (f.endsWith('.json') && !existsSync(join(to, f))) copyFileSync(join(from, f), join(to, f))
}
