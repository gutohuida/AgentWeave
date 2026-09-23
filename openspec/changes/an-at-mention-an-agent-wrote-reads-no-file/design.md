# Design — an `@`-mention an agent wrote reads no file

**R1, 2026-09-23** (day window). I read every file:line below in this round. Every "measured" row
was run in this round against `claude` 2.1.280 (`claude --version`), from
`testbed/scratch/atpath0923/`. The rows are consolidated in
`scripts/drive/d2_0923_at_mention_tokeniser.py`. Each measurement is one real Haiku turn with every
file tool disallowed.

**How expansion was detected.** The model's reply is not used. The CLI writes a session transcript
(`~/.claude/projects/<cwd-slug>/<session_id>.jsonl`), and it contains an
`"attachment":{"type":"file"` record exactly when the harness read the file. That is deterministic.
Several unexpanded variants got a reply that called the message a prompt injection, and the reply
alone could not have told "not read" apart from "read and withheld".

## Context

**One choke point.** Every agent turn's prompt is built in one place. `turn_scheduler.py:408-411`
is the only caller of `trigger_agent_directly`, and it passes
`message=format_turn_prompt(selected)`. `agent_trigger.py:1091` then prepends the Hub's notices
(`prompt = "\n\n".join([*notices, message])`). `runner_commands.py:283` appends `["-p", prompt]` for
Claude. The later `prompt=prompt` sites in `agent_trigger.py` (`:1282`, `:2017`, `:2867`) pass the
same string on to the executor and the Codex app-server path. They do not compose a new one.

**R2: the choke point is one for agent turns, not for every `claude -p` the Hub runs.** There are
exactly three `"-p"` sites in `hub/hub` (`grep`): `runner_commands.py:283` (agent turns),
`worker.py:139` (`build_worker_command`) and `conversation_titles.py:71` (`build_title_command`).
The last two are one-shot workers with no permission posture at all, and both put recorded text on
the command line:

- **The checkpoint worker.** `checkpoint_generation.build_generation_prompt` (`:230-240`)
  interpolates the conversation transcript (`_transcript_since`, `:166-227`: every inbound entry's
  `content`, so operator and peer text, and the agent's own `text` outputs), the previous
  checkpoint's body and the agent's `submit_checkpoint_notes` text. `run_worker` spawns it in a
  fresh temp directory (`worker.py:436-454`). The same checkpoint's probe
  (`_PROBE_PROMPT.format(rendered=render_checkpoint(checkpoint))`, `:633`) interpolates the body
  that worker wrote.
- **The conversation titler.** `_PROMPT.format(excerpt=excerpt)` (`conversation_titles.py:198`),
  the opening message and the agent's first reply, spawned with the project directory as `cwd`.

**Measured in R2** (`scripts/drive/d3_0923_worker_at_mention.py`, argv built by the Hub's own
`build_generation_prompt`/`build_worker_command`/`build_title_command`, `claude` 2.1.280, run twice
on fresh markers): **both expand** an agent's `@<outside path>`. The checkpoint worker's own JSON
reply carried the marker, so the file's contents reach the stored checkpoint body, which the
operator reads and `delivery_content` (`checkpoint_cutover.py:58-60`) hands to the successor
agent. D7 covers both workers.

**The context file is not a vector.** An agent turn's canonical context reaches the CLI through
`--append-system-prompt-file` (`runner_commands.py:244-245`). Measured in R2, same probe: an
`@<outside path>` in mention position in that file is **not** expanded (no attachment, marker
absent from the transcript).

**`format_turn_prompt`** (`inbound_queue.py:101-130`) labels each entry by `origin_type`: `operator`
becomes "Operator", `job` becomes "Scheduled job", and anything else becomes `Agent "<origin_agent>"`.
It then appends `entry.content` unescaped (`:129`).

**Who writes each origin's content** (the call sites of `new_entry`):

| origin_type | Site | Content, and who authored it |
|---|---|---|
| `operator` | `agent_trigger.py:1498` (`POST /agent/trigger`, Hub key only) | the operator's composer text |
| `operator` | `messages.py:268` when `by_operator` (`run_id is None`, `:62`) | the operator's chat text |
| `operator` | `questions.py:165` | `_batch_delivery_text`: **the agent's own question** plus the operator's answer |
| `operator` | `agent_trigger.py:1498`, from the board's **Start work** (`hub/ui/src/api/tasks.ts:446-465`, `useStartWorkOnTask`, called by `TaskCard.tsx:93`) | **R3:** `` `Work on task ${taskId}: ${title}` ``, composed in the browser. `title` is the task's title, which an agent can author (`create_task`, `mcp_server.py:248-249`). See D8 |
| `agent` | `messages.py:268` | another agent's `send_message` (`mcp_server.py:237`) |
| `agent` | `agents.py:2185` | the delegation task text from a spawning agent |
| `job` | `scheduler.py:3314` / `:3335`, `:3664-3668` | `f"{briefing}\n{job.message}"`. The briefing (`scheduler.py:2556-2731`) interpolates the loop's `purpose` (`:2661`), the claimed task's title (`:2666`, `:2674`), description (`:2677`) and acceptance criteria (`:2682`), and a prior checkpoint (`:2691-2696`). `job.message` comes from `POST /jobs` or MCP `create_job`/`create_loop`, by the operator or by an agent when `allow_agent_jobs` is on (`jobs.py:560-570`, `created_by_run_id` at `:693`) |
| `checkpoint` | `checkpoint_cutover.py:136` | `delivery_content(checkpoint)`, built from the agent's `submit_checkpoint_notes` |
| `checkpoint` | `checkpoint_trigger.py:242` | the fixed `_NOTES_REQUEST` (Hub text) |
| `divergence` | `run_divergence.py:262` | `_response_prompt` (`:192-214`) or `_failed_review_prompt` (`:489-506`). Hub text, but both interpolate `task.title`, which an agent can author (`create_task`). R2: agent text, so D3's default-deny is needed here, not merely harmless |

`origin_type == "operator"` is trustworthy. An agent reaches the queue only through a run credential
(`agent_auth.py`), and `messages.py:62` marks a message as the operator's only when no run is bound.
Two operator-origin entries carry agent text: the question echo (D4), and **(R3)** the board's
Start work message, whose task title an agent can have written (D8). Both mix the two authors in
one string, so each is neutralised where it is composed, while the halves can still be told apart.
(R2 checked the one route that
queues `operator` with no run: `POST /agent/trigger` depends on `get_project`, which calls
`_operator_from_credential` (`auth.py:134-159`), so a run credential cannot reach it.) `new_entry`
accepts a closed set of five origins (`inbound_queue.py:41-44`), so "an origin added later" means
someone edits that tuple; D3's default-deny makes that edit safe by default.

Two line numbers corrected in R2: the loopless job path sets `content = job.message`
(`scheduler.py:3157`) and reaches the same `new_entry` at `:3335`; the loop path's second site is
`:3660-3668`. The chat view renders stored entry content at `api/v1/agent_chat.py:205` (R1 cited
`agent_chat.py:195`).

**A pre-existing mislabel, out of scope here:** `format_turn_prompt` has no label for `checkpoint`
or `divergence`, so both fall through to `f'Agent "{entry.origin_agent}"'`, and `new_entry`
forbids `origin_agent` for them (`:45-46`). The agent reads `Agent "None" (hop 0):` above a
checkpoint or a divergence response. Filed as F410; not fixed here, because it changes every
checkpoint and divergence prompt for a reason unrelated to F409.

**The operator relies on expansion.** The composer's `@` trigger inserts
`@` + `quoteMentionValue(value)` (`hub/ui/src/lib/composerTrigger.ts:69-72`, `:81-83`, `:91-99`).
The value is a workspace path from `git ls-files` (`workspace_paths.py:31`). The CLI's expansion of
that token is what makes the picker attach the file.

**What the tokeniser does**, measured (`E` = the file was attached):

| Text before the path | E | | Text before the path | E |
|---|---|---|---|---|
| `@<abs>` (after a space) | **E** | | `\@<abs>` | — |
| `@../secret/secret.txt` | **E** | | `\\@<abs>` | — |
| `@"<abs>"` | **E** | | `ops\@example.com and \@<abs>` | — |
| `@C:\…\secret.txt` | **E** | | `@ <abs>`, `@@<abs>` | — |
| newline, tab, U+00A0, U+3000 or U+2028, then `@` | **E** | | U+200B or U+2060, then `@` | — |
| **U+FEFF**, then `@` | **E** | | `＠<abs>` (U+FF20) | — |
| inside a ```` ``` ```` fence, after `> ` | **E** | | `` `@ ``, `"@`, `(@`, `x@` | — |
| `@<abs>.` (trailing dot) | **E** | | `:` `,` `;` `=` `[` `{` `<` `'` `\|` `*` `-` `/` `_` `1` `#` `!` then `@` | — |

A relative `@inside.txt` of a file in the working directory also expands (**E**). That is harmless,
because the agent can read it anyway, but it shows expansion is not limited to absolute paths.

**`client_composed`**, measured with the Hub's own `--mcp-config` (the canonical `mcp_server.py`,
`HUB_URL` pointed at a dead port, no tool called):

| Frame | file attached | `mcp__agentweave__*` in the deferred-tools listing | Model could name the Hub's tools |
|---|---|---|---|
| plain stream-json user frame | yes | 27 tools (81 name hits) | yes, it listed them |
| `"client_composed": true` | **no** | **0** | **no**: *"No visible tools start with `mcp__agentweave`"* |

The attachments that remained under `client_composed` were `instructions`, `session_context`, `date`
and `prompt_snapshot`. The ones dropped were `environment`, `model`, `deferred_tools_delta`,
`deferred_tools_record`, `mcp_instructions_delta`, `skill_listing` and `total_tokens_reminder`.

## Decisions

### D1 — Neutralise at composition, by origin; do not change the transport

Put the fix in `format_turn_prompt`, where the origin of each block is still known. By
`runner_commands.py:283` the prompt is one flat string, and nothing can tell the operator's `@`
from a peer's.

Rejected: shape (a) of the research file, stream-json input with `client_composed` on agent frames.
It works for the file read, and it blinds the agent to the Hub. The measured table above is the
reason. Another variant would send a plain frame first (the Hub preamble) and a composed frame
second. R1 did not measure it: a second frame on stdin is a second user message, and possibly a
second turn. It would also change how every Claude run is spawned in order to fix one tokeniser.

### D2 — Escape every `@`, unconditionally: `text.replace("@", "\\@")`

Three rules were considered:

1. **Mention position only** (`(?<!\S)@`). This depends on matching the CLI's whitespace set.
   Measured: U+FEFF expands a mention, and Python's `\S` counts it as non-space, so this rule leaks
   today.
2. **Only paths that leave the workspace.** This needs the CLI's path resolution copied at compose
   time: `@"…"` quoting, `~`, Windows separators, symlinks inside the workspace that point out, and
   `@server:resource` MCP mentions. Each one is a place to be wrong. Leaving in-workspace mentions
   expandable also buys nothing, because the agent can read those files with a tool.
3. **Every `@`.** This depends on one measured fact: the character before a neutralised `@` is
   always the inserted `\`, and a `\` before `@` blocks expansion whatever precedes it (`\\@` and
   `ops\@x and \@<abs>` are measured). It needs no mirror of the tokeniser.

Rule 3 is chosen. It costs readability: `a@b.com` reaches the agent as `a\@b.com`, and a decorator in
a pasted snippet as `\@pytest.fixture`. See Risks.

### D3 — Every origin except `operator` is neutralised, including `job`

The rule is default-deny: `content if entry.origin_type == "operator" else neutralise(content)`. A
future origin is neutralised until someone decides otherwise.

`job` is neutralised as a whole, even when the operator wrote `job.message`. Three reasons:
- The entry's content is the Hub briefing with agent-authored task fields interpolated, joined to
  `job.message` in one string at two firing sites (`scheduler.py:3314`, `:3668`).
- Exempting operator-authored jobs would mean escaping field by field at both sites and trusting
  `created_by_run_id`.
- What is lost is small. The job editor has no `@` picker (the trigger lives only in
  `Composer.tsx`/`ComposerTriggerMenu.tsx`). A hand-typed `@path` in a job prompt still names the
  file, and the agent reads it with a tool call that the posture judges, which is how the boundary
  is meant to work.

**This is an open question for the operator (Q1).**

### D4 — The question echo neutralises only the question

`_batch_delivery_text` builds `Question: {q}\n\nAnswer: {a}` for one question and a numbered list
for several. Both forms interpolate `row.question`, which the agent wrote through `ask_user`, and
`row.answer`, which the operator wrote. Neutralise `row.question` at both interpolations
(`questions.py:229`, `:233`) and leave `row.answer` alone. This case has an agent reading a file
through its own text: it can turn its next turn into a read outside the posture's view, which the
posture exists to prevent even for the agent itself.

**R2, a consequence D5 did not state.** The echo is escaped where it is composed
(`questions.py:162-170` stores `_batch_delivery_text`'s result as the entry's `content`), not where
the turn is composed, because by then the question and the answer are one string. So this one
entry's *stored* content carries `\@`, and the chat view renders stored content
(`api/v1/agent_chat.py:205`): the operator sees `\@` inside the echoed question. The `Question` row
itself keeps the original. Accepted: the alternative is a column or a second entry to keep the two
halves apart, for a cosmetic difference in an echo of the agent's own words.

### D5 — Stored text is untouched

`agent_chat.py:195` renders queue entries from stored `content`. Neutralising at write time would
put `\@` in the operator's view of a peer's message and would corrupt round-trips (a checkpoint's
notes read back by `read_checkpoint`). Only the runner prompt changes. The two exceptions are the
mixed-author strings, which are escaped where they are composed and stored that way: the question
echo (D4) and, from R3, the board's Start work message (D8).

### D6 — Say so once, in the queue preamble

When the composed blocks contain the two characters `\@` anywhere, add one sentence after the
preamble line: *"In text the operator did not write, every at-sign is shown with a backslash
before it, so that the text cannot make your harness attach a file; the original has no
backslash."* Without it, the agent sees an unexplained backslash. With it, the agent knows the text
is quoted content and not an escape to reproduce. The sentence is Hub text, so it is not itself
neutralised. It spells the character as "at-sign" and uses no literal `@`, so it has nothing to
expand.

**R2 changed the trigger** from "`format_turn_prompt` inserted a backslash" to "the blocks contain
`\@`". R1's trigger missed the question echo: D4 escapes it in `questions.py`, before
`format_turn_prompt` runs, inside an `operator` entry that `format_turn_prompt` passes through
untouched, so R1's rule would have delivered an escaped question with no explanation. The new
trigger catches it without the two modules sharing any state. Its only other effect: an operator who
types `\@` themselves also gets the sentence, which is still true and harmless. The constant lives
beside `neutralise_file_mentions` (D7) so both composers can use it. A turn whose blocks contain no
`\@` is byte-identical to today; that includes every operator-only turn except a question echo, or
(R3, D8) a Start work message, that had an at-sign to escape.

### D7 — The one-shot workers neutralise their whole prompt (R2)

`worker.build_worker_command` and `conversation_titles.build_title_command` apply
`neutralise_file_mentions` to the entire `prompt` they are given, in both the `claude` and the
`codex` branch, before placing it in argv.

- **The whole prompt, not per interpolation.** No worker has a use for expansion. Every byte after
  the fixed template is recorded text, the operator's included, and no composer picker feeds a
  worker. The three templates (`_GENERATION_PROMPT`, `_PROBE_PROMPT`, the titler's `_PROMPT`)
  contain no at-sign, and a test pins that, so neutralising the whole string never alters Hub
  text.
- **At the builder.** There is one builder per spawn kind. The two checkpoint kinds share
  `build_worker_command`, and any future worker prompt gets the same treatment without having to opt in.
- **Codex too**, for D3's reason. Whether `codex exec` expands `@` is unverified, and `\@` is
  harmless text.
- **The module.** `neutralise_file_mentions` and the D6 sentence go in a new
  `hub/hub/file_mentions.py`. They do not go in `inbound_queue.py`, so `worker.py` and
  `conversation_titles.py` do not import queue code for a string function.

Two consequences need their own lines. **Both were revised in R3** (Round log R3-2, R3-3). R2
had them as a generation-template rule plus an undo in the probe's answers.

- **What a worker returns is un-escaped in code, not by asking the model.** A new
  `restore_file_mentions(text)` beside `neutralise_file_mentions` is its exact inverse,
  `text.replace("\\@", "@")`. For any text `T`, `restore(neutralise(T)) == T`, including a `T` that
  already contained `\@`, because every at-sign in the neutralised text has exactly one inserted
  backslash in front of it. `worker._interpret` (`worker.py:489-535`) applies it to every string in
  the parsed JSON payload, recursively, **before** `output_model.model_validate`. That is one place
  for both checkpoint kinds (`checkpoint_generation.py:547`, `:636`, the only `run_worker` callers)
  and any later worker. `generate_conversation_title` applies it to the CLI's output before
  `title_from_output` (`conversation_titles.py:206`). The stored checkpoint body and the stored
  title therefore carry no `\@` whatever the model does. The requirement's "SHALL NOT carry the
  neutralisation" becomes something a unit test can pin. A prompt instruction cannot give that.
  **`_GENERATION_PROMPT` is unchanged and `CHECKPOINT_PROMPT_VERSION` stays `checkpoint/1`.** R2's
  rule is dropped. It is not needed: measured in R3, generation stored no `\@` with or without it
  (3 of 3 runs each). And it would make the inverse lossy, because a model told to drop the
  backslash turns an original `\@` (sent as `\\@`) into `@`. The stored invocation's `answer_text`
  keeps the raw reply, as a diagnostic.
- **The probe's path comparison is made insensitive to the escape on both sides.** The probe asks
  for file paths "exactly as written", and the rendered checkpoint lists `files_changed`
  (`:293-294`), so `packages/@scope/x` reaches the probe as `packages/\@scope/x`. **Measured in
  R3:** Haiku copied it that way in 2 of 3 probe runs. Today's `_normalise` (`:370-373`) maps `\`
  to `/` and would grade that answer missing and invented. The restore above already turns
  `packages/\@scope/x` back into `packages/@scope/x`. Alone, it would leave R2's residual: a reply
  written with Windows separators, `node_modules\@types\x`, becomes `node_modules@types\x`.
  `_normalise` therefore also drops any run of separators directly before an at-sign, after it maps
  `\` to `/`: `re.sub(r"/+@", "@", …)`. This is applied to **both** the envelope and the answers,
  as `_normalise` already is (`:384`, `:390`). `packages/@scope/x`, `packages/\@scope/x`,
  `node_modules\@types\x` and a leading `\@scope/x` all compare equal to the envelope's form. The
  cost is that `a/@b` and `a@b` compare equal. Two such paths in one checkpoint is not a case worth a
  rule. The probe template is unchanged, so `PROBE_PROMPT_VERSION` stays.

### D8 — The board's Start work neutralises the task title where it composes the message (R3)

`useStartWorkOnTask` (`hub/ui/src/api/tasks.ts:446-465`) posts
`` message: `Work on task ${taskId}: ${title}` `` to `POST /agent/trigger`, which queues it as an
`operator` entry (`agent_trigger.py:1498`). D3 passes operator entries through untouched, and
`title` can be an agent's (`create_task`). So an agent that titles a task
`Fix @/home/u/.ssh/id_rsa handling` makes the next agent the operator starts on that task attach
the file. It is the same shape as the question echo (D4): two authors in one string, separable only
where it is built. Here that place is the browser.

The fix is `` `Work on task ${taskId}: ${neutraliseFileMentions(title)}` ``, with a one-line
`neutraliseFileMentions` in a new `hub/ui/src/lib/fileMentions.ts`. It carries a comment naming
`hub/hub/file_mentions.py` as the rule it mirrors. The task id is Hub-minted and holds no at-sign.
Consequences, the same as D4's:
- The stored message shows `\@` in the chat, because it is the operator entry's content.
- D6's trigger fires on it, so the agent is told what the backslash means.
- The `Task` row keeps its title.

Rejected: resolving it in the Hub. The route could find `named_task.title` inside `body.message` and
escape that substring. That is string surgery on a message it did not compose, and it breaks the
first time the UI's wording changes. Rejected, and offered to the operator as **Q3**: drop the title
from the message (`Work on task ${taskId}`). The run is bound to the task anyway, and that is the
cleanest possible invariant ("operator content is the operator's"). But it costs the operator the
title in the chat, and the conversation titler loses its best input.

This is a UI change. The bundle is refreshed and `hub/ui/src` and `hub/hub/static/ui` are committed
together (`.claude/rules/`). The committed bundle reaches `:8000` on its next reload, with no
restart. Only this one message changes.

## Risks

- **A Windows-separator probe answer before a scoped directory.** R2 recorded this as a residual
  of its answers-only undo. **Closed in R3** by D7's symmetric `_normalise`. Task 1.9 includes the
  case.
- **A worker reply that is not valid JSON because of the escape (R3).** `\@` is not a legal JSON
  string escape. A model that copied an escaped at-sign into a string value *without* doubling the
  backslash would produce text that `extract_json_object` cannot parse (checked in R3: it returns
  `None`), and the invocation would record `unparseable`. **Measured in R3, not observed.** Nine
  Haiku worker turns (`scripts/drive/d4_0923_worker_json_escape.py`) returned zero unparseable
  replies. Every copied at-sign came back as `\\@` in the raw JSON, which is a valid escape that
  decodes to `\@`, and the restore then undoes it. If another model does it, the failure is loud (an
  `unparseable` checkpoint, recorded with its raw answer), not a wrong stored body. Accepted without
  a lenient parser: rewriting a model's JSON before parsing it is a larger, riskier change than the
  one being guarded.
- **An agent copies `\@` into a file.** A peer's message with a decorator or an email reaches the
  agent as `\@…`, and an agent pasting a snippet verbatim could write the backslash. It is
  mitigated by D6, which names the notation once per turn. The residual risk is real and low:
  peer messages are prose far more often than code. R2 should judge whether the notice is worth its
  tokens.
- **The CLI changes its tokeniser.** Suppose a future CLI treats `\@` as an escape for a literal `@`
  and expands whatever follows. `\\@` would still be blocked, but `\@` would not. The probe's
  `escaped` and `escaped_twice` rows exist to catch this. The probe needs a real Haiku turn per row,
  so it is not a CI test. It is a drive step to rerun after a CLI upgrade (tasks 3.2).
- **Hub text interpolating agent text outside the queue. R2 closed it for the notices.**
  `agent_trigger.py:1074-1091` prepends three notices. `access_path_notice` and
  `auto_snapshot_notice` (`launchability.py:383-440`) interpolate nothing. `spec_turn_notice`
  (`:316-381`) interpolates only `path`, at `:369-373`, inside a backtick span and a quoted
  argument. That path is the controlling **operator** entry's `spec_document`
  (`turn_scheduler.py:400`). An agent cannot choose one containing an at-sign:
  `create_spec_document` takes no path, and the Hub mints a placeholder
  (`mcp_server.py:1723-1742`, `spec_service.py:95-112`). `rename_spec_document` takes prose and
  derives the path from `slugify`, which is `[a-z0-9-]` only (`spec_naming.py:98-121`,
  `agent_actions.py:1360-1368`). `validate_spec_path` (`spec_manifest.py:61-83`) does not itself
  forbid `@` or spaces, so an operator-typed path could carry one. That is operator text, so it is
  out of scope. R2 found the real outside-the-queue case elsewhere: the one-shot workers (Context,
  D7).

## Open Questions

1. **Q1 (D3):** Is it acceptable that an operator-authored scheduled job's prompt no longer expands a
   hand-typed `@path`? The alternative is field-level escaping in the two job firing sites and
   trusting `created_by_run_id`.
2. **Q2 (D2):** Does the operator accept `a\@b.com` in what agents read, in exchange for a rule that
   does not mirror the CLI's tokeniser?
3. **Q3 (D8, R3):** Board Start work: keep the task title in the message with its at-signs escaped
   (the default, D8), or drop the title from the message so that operator-origin content is only
   ever the operator's?

## Round log

- **R1, 2026-09-23:** explored and proposed. Every tokeniser and `client_composed` claim above was
  measured in this round. The research file's claim that the Hub never sends `client_composed` was
  checked: `grep` for `input-format`, `stream-json` input and `client_composed` in `hub/hub` finds
  none. The research file's recommended shape (a) was **rejected on measurement** (D1). The fallback
  shape (b) was **narrowed to "every `@`"** because the U+FEFF row broke the mention-position rule.
- **R2, 2026-09-23 (day window, D-3):** a fresh comparison against the code. I read every site
  again, starting from `grep` rather than from R1's table. Nine results:
  - **R2-1, scope: R1's "one choke point" held for agent turns only.** `grep '"-p"'` finds three
    spawn sites, not one. The checkpoint worker and the conversation titler put recorded agent text
    on `claude -p` with no posture at all. **Measured to expand**, and the checkpoint worker's reply
    carried the file's contents into what becomes the stored checkpoint
    (`scripts/drive/d3_0923_worker_at_mention.py`, twice). Added D7, a Context section, a second
    requirement paragraph with two scenarios, and tasks 1.7 to 1.10, 2.3a and 4.2a.
  - **R2-2, a regression D7 would have caused and now avoids.** The probe copies file paths
    "exactly as written", and `_normalise` turns `\` into `/`. So a changed file under `@scope/`
    would have been graded missing and invented, and the checkpoint marked `failed`. D7 undoes the
    escape in the answers first (task 1.9). The residual Windows-separator case is in Risks.
  - **R2-3, the D6 trigger moved.** R1's "`format_turn_prompt` inserted a backslash" never fires
    for the question echo. D4 escapes it upstream, inside an `operator` entry. The trigger is now
    "the blocks contain `\@`" (task 1.3a).
  - **R2-4, D5 was not quite true.** The question echo's *stored* content carries `\@`, and the
    chat renders stored content (`api/v1/agent_chat.py:205`). This is stated in D4 and accepted.
  - **R2-5, notices closed.** `access_path_notice` and `auto_snapshot_notice` interpolate nothing.
    `spec_turn_notice` interpolates only the operator entry's `spec_document`, and an agent cannot
    mint a path containing an at-sign. Details are in Risks, third bullet.
  - **R2-6, divergence is agent text.** `task.title` is interpolated. D3 already covered it, and the
    table row is corrected.
  - **R2-7, the context file is not a vector.** `--append-system-prompt-file` with an
    `@<outside path>` in mention position was measured: no attachment. It is left alone.
  - **R2-8, trust and tests.** `/agent/trigger` accepts only an operator credential. `new_entry`'s
    origin set is closed. No test in `test_inbound_queue.py`, `test_delivery_attempts.py`,
    `test_checkpoint_generation.py`, `test_title_generation.py` or the questions tests puts an
    at-sign in content these composers would change, so no existing exact-string assertion is
    expected to move. Line numbers were corrected (`scheduler.py:3157`, `:3660-3668`,
    `agent_chat.py`'s path). Out of scope: `checkpoint`/`divergence` blocks are labelled
    `Agent "None"`, filed as **F410**.
  - **R2-9, tokeniser rerun:** **41/41 rows match** (exit 0, fresh marker) on `claude` 2.1.280. D2 stands.
  - `openspec validate --strict`: valid after these edits. **R3 must not start from these notes.**
- **R3, 2026-09-23 (day window, D-4):** a second fresh comparison. The proposal and D1-D7 were read
  as the claims under test. R2's Round log was not read until R3-1 to R3-4 had been found. I started from `grep` for every `"-p"`, `exec` and stdin write in
  `hub/hub` and `src/agentweave`, then every `origin_type=` site, then every browser-composed
  `message:` template in `hub/ui/src`. Four results:
  - **R3-1, a second operator-origin entry carries agent text (new D8).** The board's Start work
    posts `` `Work on task ${taskId}: ${title}` `` as the operator (`tasks.ts:455`), and an agent
    can author the title. R1 and R2 both held that only the question echo mixes authors; neither
    looked at what the browser composes. Fixed at composition in the UI, D4's pattern. The
    alternative is Q3. New tasks 1.11, 2.3b and 4.2b. This makes the change a UI change (bundle
    refresh).
  - **R3-2, D7's "stored output carries no `\@`" was a SHALL enforced only by a prompt rule.**
    Replaced by `restore_file_mentions`, the exact inverse, applied in `worker._interpret` to the
    parsed payload and to the titler's output. The template rule and the `checkpoint/2` bump are
    dropped. **Measured** (`scripts/drive/d4_0923_worker_json_escape.py`, 9 Haiku turns, `claude`
    2.1.280): generation stored 0 `\@` both with R2's rule and without it (3/3 each), so the rule
    bought nothing observable, and it would have made the inverse lossy. Task 1.10 is rewritten.
  - **R3-3, the probe's grading made symmetric.** Measured: Haiku copied `packages/\@scope/...`
    verbatim in 2 of 3 probe runs. Today's `_normalise` fails those. R2's answers-only undo and
    R3's symmetric rule both pass them, but only the symmetric rule also passes the
    Windows-separator form. R2 had accepted that residual; it is now closed. Task 1.9 is widened.
  - **R3-4, a risk checked and not observed.** `\@` is an illegal JSON escape, and
    `extract_json_object` returns `None` on a raw `\@` inside a string (run in R3). In all 9 turns
    Haiku emitted `\@`, the legal form. Recorded in Risks as loud-if-it-happens.
  - **Held, re-derived rather than re-read:**
    - The agent-turn choke point. `trigger_agent_directly` has one caller, `turn_scheduler.py:408`.
    - Exactly three `"-p"` sites. No SDK spawn. The CLI package's subprocess calls carry no prompt
      (`docker`, a browser, PowerShell, `mcp list`).
    - D2's inverse property. `\@` in the original goes out as `\@` and restores to `\@`.
    - D3's default-deny over the five origins.
    - D6's trigger. It now also fires for D8.
  - `openspec validate --strict`: valid after these edits.
