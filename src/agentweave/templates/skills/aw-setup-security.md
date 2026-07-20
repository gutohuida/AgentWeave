---
name: aw-setup-security
description: Configure AgentWeave security and quality guardrails — review gates, echo-chamber protection, dependency/slopsquatting checks, attribution, decision docs, guardian roles, and secrets hygiene. Use when hardening a project or auditing its agentweave.yml quality block. For full project setup use aw-setup.
---

Configure the security and quality guardrails for this project. They live in the `quality:` block of `agentweave.yml`, plus role assignments and secrets hygiene.

**Project:** {project_name} — **agents:** {agents_list}

## 1. Review the current posture

1. Read `agentweave.yml` — is there a `quality:` block?
2. `agentweave roles list` — is any agent a `guardian`, `security_engineer`, `code_reviewer`, or `verifier`?
3. `agentweave status` — the Quality Health section shows active guards and review backlog.

## 2. The quality: block

Walk the user through each guard, with the recommendation:

```yaml
quality:
  # Every task must pass review before it can be approved.
  # Pair with a code_reviewer or verifier role on a DIFFERENT agent.
  review_required: true

  # Prevent the same agent from implementing AND reviewing a task.
  # off = allow self-review | warn = flag it | enforce = block it.
  # Recommended: warn for solo projects, enforce for teams.
  echo_chamber_guard: warn

  # Flag hallucinated or unresolvable package names during review
  # (slopsquatting protection). Recommended: true.
  dependency_check: true

  # Stamp completed tasks with the agent name and session ID (audit trail).
  attribution_tag: true

  # Require a decision doc for completed work: all | non_trivial | never.
  # Docs are written to docs_path (default .agentweave/code-docs).
  docs_threshold: never
  # docs_path: .agentweave/code-docs
```

Explain the trade-off of each choice as you go: guards slow the loop down; for a solo toy project `review_required: false` + `echo_chamber_guard: off` is legitimate, but `dependency_check: true` costs nothing and catches real attacks.

## 3. Role-level security

Guards work best with the right roles (`agentweave roles set <agent> <csv>`, or `roles:` in the yml — see `aw-setup-roles`):

- `guardian` — AI-specific safety review: slopsquatting, prompt injection, scopes, secrets. Assign when `dependency_check` or untrusted inputs are in play.
- `security_engineer` — human-title security review: auth/authz, vulnerability audit.
- `verifier` / `code_reviewer` — required capacity when `review_required: true`; must be a different agent than the implementer when `echo_chamber_guard: enforce`.

## 4. Secrets hygiene checklist

Verify each item and fix what's missing:

- [ ] API keys live only in the project-root `.env` (gitignored, auto-loaded). Never in `agentweave.yml` — the `env:` field lists variable **names**, not values.
- [ ] `.agentweave/transport.json` (contains the Hub `aw_live_...` key) is gitignored.
- [ ] The `.gitignore` block written by `agentweave init` is intact: it covers `.agentweave/tasks/*/`, `.agentweave/messages/*/`, `.agentweave/agents/*.json`, `.agentweave/session.json`, `.agentweave/transport.json`, `.agentweave/logs/`, and `.env`.
- [ ] No keys in shell history files committed anywhere; Hub keys use the `aw_live_` format and are stored in `~/.agentweave/hub/.env`, outside the repo.
- [ ] If this repo was ever committed with a secret, treat it as leaked — rotate the key.

## 5. Apply and verify

```bash
# after editing agentweave.yml:
agentweave activate
agentweave doctor
agentweave status    # Quality Health section reflects the guards
```

Then summarize the final posture: which guards are on, who reviews, and any remaining secrets-hygiene gaps.
