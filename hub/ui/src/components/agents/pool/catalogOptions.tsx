import { ProviderMark } from '@/components/common/Icon'
import type { SelectOption } from '@/components/ui/menu'
import { catalogModelLabel, type ProviderDescriptor } from '@/api/modelCatalog'
import type { RunnerLaunchability } from '@/api/runners'

/**
 * The model catalog as the app's themed menus offer it (`a-profile-s-pool-and-a-new-chat-can-use-
 * any-model-of-any-provider`, FR-1 and FR-9): a provider with its mark, then that provider's models
 * by display name. The pool editor and both profile-creation dialogs choose from these, so the
 * three offer the same models in the same words.
 */

/** Every catalog provider, its mark beside its name. Given `launchability`, a provider whose CLI
 *  cannot run here is listed but not choosable, saying why. */
export function providerOptions(
  providers: ProviderDescriptor[],
  launchability?: Record<string, RunnerLaunchability>,
): SelectOption<string>[] {
  return providers.map((entry) => {
    const verdict = launchability?.[entry.provider]
    return {
      value: entry.provider,
      label: entry.label,
      icon: <ProviderMark provider={entry.provider} label={entry.label} />,
      disabled: launchability ? verdict?.runnable !== true : false,
      detail: verdict && !verdict.runnable && verdict.reason ? verdict.reason : undefined,
    }
  })
}

/** Every model the catalog declares for `provider`, by display name with the provider's mark, and,
 *  with `aliases`, each declared alias after them ("opus — latest (now Opus 5.5)"). */
export function modelOptions(provider: ProviderDescriptor | undefined, { aliases = false } = {}): SelectOption<string>[] {
  if (!provider) return []
  const mark = <ProviderMark provider={provider.provider} label={provider.label} />
  const models = provider.models.map((model) => ({ value: model.id, label: model.label, icon: mark }))
  if (!aliases) return models
  const latest = provider.models.flatMap((model) =>
    model.aliases.map((alias) => ({ value: alias, label: catalogModelLabel(model, alias), detail: 'Follows the newest model', icon: mark })),
  )
  return [...models, ...latest]
}

/** The model a provider is chosen with: its catalog default, else its first model. */
export function defaultModel(provider: ProviderDescriptor | undefined): string {
  return provider?.models.find((m) => m.default)?.id ?? provider?.models[0]?.id ?? ''
}

/** A name to suggest for a profile on `provider` ("claude-reviewer"), or a neutral one before a
 *  provider is chosen. */
export function namePlaceholder(provider: string, role = 'reviewer'): string {
  return provider ? `${provider}-${role}` : role
}
