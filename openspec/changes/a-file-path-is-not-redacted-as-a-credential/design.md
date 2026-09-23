# Design — a file path is not redacted as a credential

No operator decision is involved. The finding itself says the narrowing "wants its own change with
its own reproduction" (F278, `scripts/drive/FINDINGS.md:21632`). This is that change.

## Context

- `_SECRET_VALUE_RE` (`hub/hub/runner_events.py:57-60`) has three alternatives: `aw_live_…` and
  `sk-…`, both anchored at the start of a word (F118), and the catch-all `[A-Za-z0-9+/=]{32,}`.
- `redact_secrets` (`runner_events.py:63-81`) walks dicts, lists and tuples, and calls
  `_SECRET_VALUE_RE.sub("<redacted>", value)` on every string.
- It has three callers: `tool_use_event` (`runner_events.py:177`), `tool_result_event`
  (`runner_events.py:206`) and the loop error summary (`scheduler.py:94`).
- `tool_use_event` reads `write_paths` off the structured input **before** redaction
  (`runner_events.py:164-176`), and it does so because of F278. That field is correct today and
  stays correct.

## Decisions

### D1 — Keep the pattern, and decide in the replacement

`_SECRET_VALUE_RE.sub` gets a function instead of the literal `"<redacted>"`. The function keeps a
match only when all of these hold:

1. The match came from the **catch-all**. A match that starts with `aw_live_` or `sk-` came from a
   prefix alternative and is always redacted. The function can tell which alternative matched
   through `m.lastindex` once each alternative is its own group. Checking the prefix string would
   also work. **R2 chose named groups**: drop today's single outer group (nothing reads
   `group(1)`; `redact_secrets` is its only user, via `sub`) and name the catch-all
   `(?P<entropy>[A-Za-z0-9+/=]{32,})`, so the test is `m.lastgroup == "entropy"`. It states which
   rule matched instead of re-deriving it from the text. Task 1.3 covers the prefix case either way.
2. Split on `/`, it has **at least three non-empty segments**.
3. Every segment fully matches `[a-z0-9]+|[A-Z]?[a-z]+(?:[A-Z][a-z]+)*`. That is a lowercase or
   digit word (`src`, `v1`, `python3`), or a capitalised or camel-case word (`Users`,
   `AgentWeave`).

A kept match still has each segment of **32 or more characters** replaced by `<redacted>`. So
`…/v1/tokens/<40 hex>` keeps its path and loses the value.

**Rejected: removing `/` from the class.** That misses a base64 credential containing `/` (the AWS
secret key shape `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`, redacted today). The value would lose
only its middle, and 13- and 18-character fragments of a key would be stored.

**Rejected: requiring `+` or `=` in the run.** Most base64 secrets carry neither.

**Rejected: two segments.** Measured on 2026-09-24: with two segments allowed, 3 of 790,914 random
32-character base64 strings containing `/` would survive (for example
`PcLhqFyu/UlhzTdyfoFuXclWcJlKlmCn`). With three, 0 of 791,738 did.

### D2 — What was measured, and the residual

Measured at `ce086b6` with the D1 function over `hub.runner_events._SECRET_VALUE_RE`:

| input | today | with D1 |
|---|---|---|
| `/Users/operator/code/agentweave/hub/main.py` | `<redacted>.py` | intact |
| `src/services/user/repository/handler.py` | `<redacted>.py` | intact |
| `/workspace/proj/.agentweave/worktrees/beta/src/app.py` | `/workspace/proj/.<redacted>.py` | intact |
| `/home/runner/work/AgentWeave/AgentWeave/hub/hub/scheduler.py` | `<redacted>.py` | intact |
| `https://api.example.com/v1/tokens/<40 hex>` | `https://api.example.<redacted>` | `…/v1/tokens/<redacted>` |
| `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` | `<redacted>` | `<redacted>` |
| the four credentials in `test_a_credential_is_still_redacted` | `<redacted>` | `<redacted>` |
| `spread-fairness-metric-fix-for-idle-staff`, `task-…` | intact | intact |

The residual: of 1,146,498 random base64 strings (32–128 characters) that contain `/`, **1**
survived. That is about 1e-6, and it applies only to a secret with no known prefix. Today's rule
already lets through every credential shorter than 32 characters and every one containing `.`, `_`
or `-`. The finding records "zero recorded true positives that the two prefixes would have
missed". R2 should re-run the measurement, not trust this number.

**R2 re-ran it independently** (own implementation of D1, over the module's pattern at `ce086b6`):
0 survivors in 685,660 random base64 strings of 32–128 characters containing `/`, and every row of
the table above reproduced. One narrowing R1 did not state: an all-capitals segment (`README`,
`API`) is not an "ordinary word", so `/usr/lib/python3/dist/packages/foo/README/x` is still
redacted whole. Accepted: widening the segment rule to capitals admits more of base64's alphabet.

### D3 — Why nothing else in the product depends on the defect

`write_paths` is read before redaction and does not change. What the operator sees is the recorded
`payload["input"]` and `payload["output"]`, which will now show the paths. Nothing parses
`<redacted>` back out. `grep -rn "<redacted>" hub/hub hub/ui/src` finds only the producer and tests.
R2 ran the grep: the only other `"<redacted>"` in `hub/hub` is `jobs.py:61`, the job-failure
summary's own redactor (`_safe_error_summary`). It is a producer, not a reader, and its class
`[A-Za-z0-9_=-]` has no `/`, so like the CLI twin it never had F278. It is not changed here.

## What each caller returns when this raises

`redact_secrets` is pure. The new replacement function uses only `re` and `str.split`, so it cannot
raise on a `str` input. None of the three callers catches around it today, and none needs to.

## Round log

- **R1 (2026-09-24):** proposed. Measured D2 on `ce086b6`.
- **R2 (2026-09-24):** every code claim re-derived and the residual re-measured (0 of 685,660).
  D1 item 1 decided (named group). Two notes added: all-capitals segments stay redacted, and
  `jobs.py`'s separate redactor is untouched.
