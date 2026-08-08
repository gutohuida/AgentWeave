import type { ModelCatalogResponse } from '@/api/modelCatalog'

/**
 * A catalog shaped like the Hub's, trimmed to what the settings page reads.
 *
 * Both providers declare the same four postures with the same labels, exactly as
 * `hub/hub/model_catalog.py` does — the settings page takes their union, so a fixture where they
 * differed would test a catalog the Hub cannot produce.
 */
export const MODEL_CATALOG_FIXTURE: ModelCatalogResponse = {
  providers: ['claude', 'codex'].map((provider) => ({
    provider,
    label: provider,
    models: [],
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
