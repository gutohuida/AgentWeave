# Switching opencode Models

The opencode runner in AgentWeave is **model-agnostic**. The `model:` field in `agentweave.yml` is a free-form string that gets passed verbatim to the pinned opencode binary. Whatever models your opencode build knows about, you can use — without changing AgentWeave itself.

This guide covers:

1. The minimum change to switch models
2. How the `model:` field flows through AgentWeave
3. Format requirements (`provider/model`, case sensitivity)
4. Three paths to authenticate with a provider
5. A full worked example for the top-level `opencode:` block
6. A cheatsheet of providers your pinned binary likely supports
7. A decision tree for the most common error: `ProviderModelNotFoundError`
8. A pre-flight checklist before `agentweave activate`

For installation, MCP setup, and the `cli:` binary override, see [OpenCode Agents](opencode-agents.md). For the WSL multi-install trap specifically, see [Pinning the `opencode` binary](opencode-agents.md#pinning-the-opencode-binary-wsl-multi-install-hosts).

---

## 1. Quick recipe

Edit three things in `agentweave.yml` — only the `model:` value, optionally the `env:` list, and optionally the `cli:` binary path:

```yaml
agents:
  opencode:
    runner: opencode
    model: minimax-coding-plan/MiniMax-M2.7    # ← change this
    cli: /mnt/c/Users/you/AppData/Roaming/npm/opencode   # ← keep the binary pinned
    env: [MINIMAX_API_KEY]                      # ← add any provider-required env var
```

Then:

```bash
agentweave activate
```

That's it. The next watchdog trigger uses the new model.

---

## 2. What the `model:` field actually does

AgentWeave treats the value as opaque. In `src/agentweave/watchdog.py`, the opencode launcher builds the command as:

```python
model = session.get_runner_config(agent).get("model")
if model:
    cmd += ["--model", model]
```

That's the only thing the framework does with it — the string is passed straight to the opencode binary as `--model <value>`. There is:

- No AgentWeave-side catalog of "valid models"
- No validation at `agentweave.yml` parse time (a typo only surfaces at runtime)
- No transformation (no prefixing, no fallback to defaults)

What *is* available is determined entirely by the opencode binary version you pinned (via `cli:` or the first one on `PATH`) and the providers you've registered with it.

---

## 3. Format requirements

### `provider/model` is mandatory

opencode rejects bare model names. `gpt-4` is invalid; `openai/gpt-4` is required.

### Case-sensitive on both halves

The provider ID and the model ID are matched literally. `MiniMax-M3` works; `minimax-m3` does not. Copy them exactly from your binary's catalog.

### Where to find valid IDs

```bash
<your-pinned-opencode> models
```

Lists every model your binary knows, grouped by provider. Grep for yours:

```bash
<your-pinned-opencode> models | grep minimax
```

If the model isn't in the list, your binary is too old or you have a typo.

---

## 4. Auth setup — three paths

Pick the one that fits your workflow.

### Path A — `opencode auth login` (recommended for interactive setup)

Stores the key in `~/.local/share/opencode/auth.json` (or `%USERPROFILE%\.local\share\opencode\auth.json` on Windows). One command per provider:

```bash
opencode auth login
# then pick the provider from the interactive list
```

Pros: zero file editing; key never leaves `~/.local/share/`.
Cons: not portable — each developer runs it on their own machine.

### Path B — Top-level `opencode:` block in `agentweave.yml` (repo-committed, CI-friendly)

Embeds provider config in the project yml. `agentweave activate` auto-generates `opencode.json` at the project root. See [section 5](#5-top-level-opencode-block-full-worked-example) for the full worked example.

Pros: portable across machines and CI; no `opencode auth login` needed.
Cons: less safe to commit if the yml has secrets — usually you use placeholder env vars.

### Path C — Env var only (for providers whose SDK reads env directly)

If the provider's SDK reads `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc. directly, you can skip both Path A and B and just declare the env var:

```yaml
agents:
  opencode:
    runner: opencode
    model: openai/gpt-4o
    env: [OPENAI_API_KEY]
```

The watchdog resolves the var name to its value at launch time and forwards it to the opencode subprocess. Put the actual value in `.env` (gitignored) or your shell.

---

## 5. Top-level `opencode:` block — full worked example

Use this when you want provider config to be **versioned alongside the project** (CI, shared test harness, no interactive login).

### What goes in the yml

```yaml
# agentweave.yml
opencode:
  provider:
    minimax:
      npm: "@ai-sdk/anthropic"     # provider SDK that opencode should use
      name: "MiniMax"
      options:
        baseURL: "https://api.minimaxi.com/v1"
      models:
        M3:
          name: "MiniMax-M3"
```

The `opencode:` top-level block is **opaque** to AgentWeave — AgentWeave doesn't read its keys, it just writes them to `opencode.json` at the project root.

### What `agentweave activate` does with it

- Reads the `opencode:` block from `agentweave.yml`
- Writes (or merges) it into `opencode.json` at the project root
- Uses **add-or-replace semantics**: keys you declare overwrite, other top-level keys (`mcp`, `agent`, `instructions`, etc.) are preserved
- Verifies the resulting `opencode.json` is valid JSON before saving

### After activate — what `opencode.json` looks like

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "agentweave": { "type": "local", "command": ["agentweave-mcp"] }
  },
  "provider": {
    "minimax": {
      "npm": "@ai-sdk/anthropic",
      "name": "MiniMax",
      "options": { "baseURL": "https://api.minimaxi.com/v1" },
      "models": { "M3": { "name": "MiniMax-M3" } }
    }
  }
}
```

### When to use this vs. `opencode auth login`

| Use top-level `opencode:` block when… | Use `opencode auth login` when… |
|---|---|
| Config should travel with the repo | You prefer keys to live in `~/.local/` |
| CI must run opencode without a TTY | You're on a single machine and don't commit yml |
| Multiple team members need identical provider config | You're the only user |
| You want to test provider changes via git diffs | You want to revoke a key without editing yml |

### Verify it took effect

```bash
cat opencode.json | jq .provider                  # confirm the merge
<cli> auth list                                   # opencode should now show the provider
<cli> models | grep <your-provider>              # and the models
```

---

## 6. Provider cheatsheet

The exact list of available providers depends on your pinned opencode binary version, but the major ones for 1.17.x are:

| Provider | Auth setup | Model string format | Example |
|---|---|---|---|
| **MiniMax** | `env: [MINIMAX_API_KEY]` + `.env` key, OR `opencode auth login` | `minimax-coding-plan/<model>` or `minimax-cn-coding-plan/<model>` | `minimax-coding-plan/MiniMax-M3` |
| **Anthropic** | `opencode auth login` OR `ANTHROPIC_API_KEY` | `anthropic/<model>` | `anthropic/claude-sonnet-4-5` |
| **OpenAI** | `opencode auth login` OR `OPENAI_API_KEY` | `openai/<model>` | `openai/gpt-4o` |
| **Google** | `opencode auth login` OR `GOOGLE_API_KEY` | `google/<model>` | `google/gemini-2.5-pro` |
| **Ollama** (local) | none — just `ollama serve` and `ollama pull` | `ollama/<model>` | `ollama/qwen2.5-coder:7b` |
| **`opencode/*`** (free) | none | `opencode/<model>` | `opencode/big-pickle` |

### MiniMax models your 1.17.x binary knows

The pinned opencode 1.17.x exposes 7 models per provider:

- `MiniMax-M2`
- `MiniMax-M2.1`
- `MiniMax-M2.5`
- `MiniMax-M2.5-highspeed`
- `MiniMax-M2.7`
- `MiniMax-M2.7-highspeed`
- `MiniMax-M3`

Both `minimax-coding-plan/*` (international) and `minimax-cn-coding-plan/*` (China region) providers expose the same 7 models. Pick the provider prefix that matches your account region.

### Free `opencode/*` models for smoke tests

Built into every opencode build, no auth required. Useful for verifying the AgentWeave → opencode pipeline end-to-end without spending API credits:

- `opencode/big-pickle`
- `opencode/deepseek-v4-flash-free`
- `opencode/mimo-v2.5-free`
- `opencode/nemotron-3-ultra-free`
- `opencode/north-mini-code-free`

Quality is lower than the paid models, but they reliably exercise the same code path.

---

## 7. Catalog-mismatch troubleshooting

When opencode returns `ProviderModelNotFoundError: Model not found: <provider>/<model>`, the yml and `auth.json` are almost always correct — the issue is that the opencode binary you actually invoked doesn't list that model. Walk this decision tree:

```
ProviderModelNotFoundError: Model not found: <provider>/<model>
│
├─ Step 1: Is the model string spelled correctly?
│        $ <cli> models | grep <model>
│        If not listed with that exact spelling, fix the yml (case-sensitive).
│
├─ Step 2: Is the provider registered?
│        $ <cli> auth list
│        If the provider is missing, run `opencode auth login` or add
│        a top-level `opencode:` block (see section 5).
│
├─ Step 3: Is the binary version you think it is?
│        $ which opencode
│        $ opencode --version
│        If `which` returns a different path than the one you installed,
│        a stale binary is shadowing it (very common on WSL).
│
└─ Step 4: Pin the binary that actually has the model.
         Add `cli: /abs/path/to/<binary>` to the agent in agentweave.yml
         (see opencode-agents.md#pinning-the-opencode-binary-wsl-multi-install-hosts).
         Re-run `agentweave activate`.
```

The fix is always the same shape: pick a model your **pinned** binary actually lists.

### Common false starts

- **"My `auth.json` has the provider"** — true, but the binary shadowing yours may not. Check `which opencode` and pin with `cli:`.
- **"I just upgraded opencode"** — did your shell see the new path? The old `~/.local/bin/opencode` (or npm global) can linger. `which opencode && opencode --version` confirms.
- **"I copied the model string from the docs exactly"** — case differs? `MiniMax-M3` (capital M) works; `Minimax-m3` does not. Confirm with `<cli> models | grep -i minimax`.

---

## 8. Verify before you activate

Three commands catch ~90% of "it works on my machine" problems before the watchdog hits them:

```bash
# 1. Is your model in the pinned binary's catalog?
<cli> models | grep <provider>/<model>

# 2. Is the provider registered with the binary?
<cli> auth list

# 3. Does the AgentWeave readiness check pass?
agentweave doctor
```

If all three succeed, `agentweave activate` and `agentweave start` will Just Work.

### If `agentweave doctor` reports `agent_cli_missing` for the opencode agent

Either:

- The path in `cli:` doesn't exist or isn't executable — fix the path, or remove `cli:` to fall back to `shutil.which("opencode")`
- The first `opencode` on `PATH` isn't in any directory AgentWeave searched — pin it with `cli:`

See the `cli:` section in [OpenCode Agents](opencode-agents.md#pinning-the-opencode-binary-wsl-multi-install-hosts) for the full pattern.

---

## 9. See also

- [OpenCode Agents](opencode-agents.md) — main guide; installation, MCP setup, the `cli:` override
- [FAQ: `ProviderModelNotFoundError`](faq.md#why-does-opencode-return-providermodelnotfounderror-even-though-my-yml-and-authjson-are-correct) — short pointer entry
- [agentweave.yml Reference](../reference/agentweave-yml.md) — full schema, including the `opencode:` top-level block
- [Claude-Proxy Agents](claude-proxy-agents.md) — alternative for MiniMax / GLM via Claude CLI proxy
- [OpenCode Documentation](https://sst.dev) — provider SDK reference for the top-level `opencode:` block
