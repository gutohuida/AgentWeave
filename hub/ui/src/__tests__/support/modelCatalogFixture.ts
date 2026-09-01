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
}

export const MODEL_CATALOG_FIXTURE: ModelCatalogResponse = {
  providers: ['claude', 'codex'].map((provider) => ({
    provider,
    label: provider,
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
        default: 'acceptEdits',
        apply: { style: 'flag' as const, template: '--permission-mode {value}' },
      },
    ],
  })),
}
