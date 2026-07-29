# Verification record

Date: 2026-07-29

## Automated verification

- Focused runner/collector/safety/legacy/transport matrix: 297 passed.
- Full CLI suite: 982 passed, 4 skipped.
- Ruff over `src`: passed.
- Black check over `src`: passed, 30 files unchanged.
- Mypy over `src`: passed with no issues in 28 source files. Mypy also reported that its current
  release no longer supports the configured Python 3.8 target; this was informational and did not
  fail the run.
- Full Hub suite: 240 passed, 4 skipped. Three existing Alembic `path_separator` deprecation
  warnings were emitted.
- Full Hub UI suite: 15 files and 85 tests passed.
- TypeScript and Vite production build: passed, 434 modules transformed.
- UI lint could not start because installed ESLint 9 requires `eslint.config.js` and the project
  does not yet have a flat config. No lint result is claimed.
- MkDocs was not installed in the project virtual environment, so the documentation build could
  not start. Navigation YAML and local links were checked directly.

The focused matrix covered every stdout adapter, cross-adapter conformance, canonical constructors,
payload redaction/bounds, legacy context normalization, Codex rollout collection, Copilot OTel
collection, Kimi Wire collection, OpenCode model-limit resolution, invocation binding, new-session
replacement, stale-session rejection, and HTTP rolling compatibility.

## Installed-runner smoke tests

Each CLI ran a metadata-only fresh turn and a resumed turn in a unique directory under the system
temporary directory. Raw response content was not printed or inspected. Only event kinds, session
identity, usage-field names, exit status, and availability classification were summarized. Every
temporary directory was removed after its probe.

| Runner | Version | Result | Metadata observed |
|---|---|---|---|
| Claude Code | 2.1.220 | Fresh/resume passed; same session | assistant, system init, success result, input/cache/output usage |
| Codex CLI | 0.145.0 | Fresh/resume passed; same thread | thread/turn/item events and token usage |
| OpenCode | 1.18.5 | Fresh/resume passed; same session | step start/finish, text, input/output/cache/reasoning/total |
| Kimi Code | 0.29.1 | Fresh/resume passed; same recovered session | assistant and resume-hint metadata |
| GitHub Copilot CLI | 1.0.75 | Fresh/resume passed; same session | assistant lifecycle/message events and invocation-scoped OTel usage |

No provider quota, authentication, or availability failure occurred. Copilot OTel included
input/output/reasoning usage (and cache-read usage on the resumed turn) while exposing no prompt,
response, message, or content attributes. This supersedes the earlier documentation-derived
Copilot fixture status.

## Live Hub and UI verification

An isolated Hub database, Vite server, and headless Chrome profile were created outside the
repository and removed after verification.

- Structured streams representing the live-verified Claude and Codex adapters were posted with
  run IDs, sequences, kinds, and versioned payloads.
- Agent output visibly rendered grouped thinking, paired tool use/result, text, status, and
  diagnostic semantics.
- Activity visibly projected semantic `TOOL_USE` and `TOOL_RESULT` rows.
- Spec chat used the shared renderer, showed thinking/tools/text, and excluded diagnostics.
- Overview and agent surfaces visibly distinguished:
  - measured usage with a 75% warning bar;
  - a 42,000-token sample with unknown limit and no percentage;
  - unavailable context;
  - unsupported context.
- A Codex sample was first posted as measured at 80% for an old session, then replaced by a newer
  session's unavailable snapshot. REST and the UI both showed the new unavailable state and no
  stale 80% bar.

## Separation, privacy, and scope audit

- Parser conformance tests prove output events and usage samples remain independent.
- Claude usage-only, Codex usage-only, and OpenCode usage-only tests produce no fabricated output.
- Hub context ingress persists a latest EventLog snapshot and never creates an `AgentOutput`.
- Copilot collector tests prove raw content attributes are not surfaced; the live OTel smoke
  confirmed content capture was absent.
- Canonical breakdowns allow only numeric token fields. Raw provider dictionaries and Wire/OTel
  records are not transported or persisted.
- The implementation adds no process cancellation, message threading, cost reporting, automatic
  reset/handoff policy, or Kimi v1 expansion. Retained Kimi v1 parsing remains regression-only
  compatibility.
