import type { ModelCatalogResponse } from '@/api/modelCatalog'

/**
 * A catalog shaped like the Hub's, trimmed to what the settings page reads.
 *
 * Both providers declare the same four postures with the same labels, exactly as
 * `hub/hub/model_catalog.py` does — the settings page takes their union, so a fixture where they
 * differed would test a catalog the Hub cannot produce.
 *
 * The model lists are a trimmed subset of that same file, taken verbatim rather than invented:
 * a provider that declares *no* models is a catalog the Hub cannot produce either, and the runner
 * model select renders straight off this list.
 */
const MODELS: Record<string, ModelCatalogResponse['providers'][number]['models']> = {
  claude: [
    { id: 'claude-opus-5', label: 'Opus 5', aliases: ['opus'], context_window: 1_000_000, default: false },
    { id: 'claude-sonnet-5', label: 'Sonnet 5', aliases: ['sonnet'], context_window: 1_000_000, default: true },
    { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5', aliases: ['haiku'], context_window: 200_000, default: false },
  ],
  codex: [
    { id: 'gpt-5.6-sol', label: 'GPT-5.6-Sol', aliases: [], context_window: 272_000, default: true },
    { id: 'gpt-5.4-mini', label: 'GPT-5.4-Mini', aliases: [], context_window: 272_000, default: false },
  ],
  // `a-copilot-agent-runs-over-acp` D13: Auto first and the default, every window unknown.
  copilot: [
    { id: 'auto', label: 'Auto', aliases: [], context_window: null, default: true },
    { id: 'claude-haiku-4.5', label: 'Claude Haiku 4.5', aliases: [], context_window: null, default: false },
  ],
}

// Copilot's Permissions default is Workspace only (D8: it has no sandbox to fall back on).
const PERMISSION_DEFAULT: Record<string, string> = {
  claude: 'workspace',
  codex: 'acceptEdits',
  copilot: 'workspace',
}

export const MODEL_CATALOG_FIXTURE: ModelCatalogResponse = {
  providers: ['claude', 'codex', 'copilot'].map((provider) => ({
    provider,
    label: provider,
    // Both providers built-in by default (matches "no cache on this machine"); Codex's own
    // cache-reading state is exercised by tests that override this field directly
    // (`the-codex-models-offered-are-the-ones-its-cli-lists`, design test 9).
    source: { kind: 'built_in' as const, fetched_at: null, client_version: null, reason: `no Codex model cache` },
    models: MODELS[provider],
    controls: [
      {
        id: 'permission_mode',
        label: 'Permissions',
        kind: 'enum' as const,
        values: [
          { id: 'acceptEdits', label: 'Edit files' },
          { id: 'workspace', label: 'Workspace only' },
          { id: 'manual', label: 'Ask me' },
          { id: 'bypassPermissions', label: 'Full access' },
        ],
        default: PERMISSION_DEFAULT[provider],
        apply: { style: 'flag' as const, template: '--permission-mode {value}' },
      },
    ],
  })),
}
