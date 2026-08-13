# Design — A document earns its name

## D1. The Hub mints the path; the browser stops guessing

**Decision.** `POST /project/documents` accepts `path: Optional[str]`. When it is absent the Hub
mints a placeholder and returns it. The two UI call sites send no path and read the one they get
back.

**Why not keep it client-side.** `documentPathFor` is called from two components with two different
inputs — the operator's raw first message and the (possibly model-rewritten) conversation title —
so the same action through two doors already produces two names. A generator in one place cannot
diverge from itself. It also has to be server-side anyway: the rename slugifies a subject the agent
supplies over MCP, which never touches the browser, and having two slug implementations in two
languages is how they drift.

**Why `path` stays accepted rather than being removed.** Tests, the existing UI's picker flows and
any operator scripting a document into place all pass one, and an explicit path is still the only
way to create a document at a chosen location. Optional is the smaller change and the honest one:
the Hub mints *when not told*.

## D2. What a placeholder is

`spec/changes/<colour>-<mythic-animal>/spec.html`, in a new `hub/hub/spec_naming.py`.

- Both word lists are lowercase ASCII, single words, no hyphens — so the slug contract in
  `validate_spec_path` holds by construction rather than by validation.
- The lists are sized so the product comfortably exceeds any realistic document count in one
  project; collisions are handled rather than assumed away.
- **Collision handling:** mint, check the database and the filesystem, retry a bounded number of
  times, then fall back to appending a short random suffix. The bounded retry is not an
  optimisation — an unbounded loop against a full namespace never returns.
- **Randomness is real randomness.** No seed, no derivation from the title, no counter. A
  reproducible placeholder would be treated as identity within a week.

**Why a colour and an animal** rather than a number or a UUID. The name is spoken — "the amber
griffin one" — during the minutes between creating a document and the agent learning what it is.
`spdoc-8f2a1c` is unpronounceable and `exploration-3` reads like an ordinal that means something.
The pairing is memorable, obviously arbitrary, and short enough to sit in a path segment.

## D3. Rename takes a subject, not a path

`rename_spec_document(path, subject)`.

The agent supplies prose — `"Personal houseplant watering tracker"` — and the Hub slugifies it to
`houseplant-watering-tracker`. The agent never composes a path.

**Why.** `validate_spec_path` is the single door that stops a document being written to an arbitrary
location beneath `spec/`. A rename that accepted a target path would be a second door, opened to the
least trusted caller in the system, guarded by the same validation and no other. Slugifying a
subject means the caller cannot express a directory traversal, a hidden segment or a different
filename at all — the shapes are unreachable rather than rejected.

The slug is derived by a Python port of the rule already in `hub/ui/src/lib/specDocumentName.ts`:
NFKD-normalise, strip combining marks, lowercase, collapse non-alphanumerics to `-`, trim, truncate.
Truncation is to a bound that keeps the whole path inside `SPEC_PATH_MAX_LENGTH` with the
`spec/changes/` prefix and `/spec.html` suffix accounted for, not to a bare slug length — the
existing TS bound of 64 was chosen against neither.

**A subject that slugifies to nothing is refused**, with the reason. `"???"` is not a name, and
minting a second placeholder to stand in for a failed rename would be worse than saying so.

## D4. What a rename actually moves

The handoff recorded this as "the file, the `path` column and the index entry and nothing else".
Reading the code, it is the file, the column, and **pending queue entries** — and *not* the index.

| Reference | What happens |
|---|---|
| The file on disk | Moved. `Path.replace` onto the resolved new path, parents created first. |
| `SpecDocument.path` | Updated. The unique constraint `(project_id, path)` still holds. |
| `SpecDocument.id`, requirement identifiers, digests, `spec_document_events` | Untouched. Identity never was the path. |
| `InboundQueueEntry.spec_document` | **Updated where not yet delivered.** A queued turn carries a path snapshot; a rename between queueing and spawning would otherwise hand the agent a path that no longer resolves. |
| `spec/index.json` | **Not touched.** The Hub reads this file and has never written it. |
| React Query keys, SSE `spec_updated`, URL state | Follow through the response and the event; see D6. |

**Why pending queue entries and not delivered ones.** A delivered entry is history — it records the
path that was open when the turn ran, and rewriting history to stay tidy is how a record stops being
one. An undelivered entry is a pending instruction, and a pending instruction naming a path that no
longer exists is simply wrong.

**Why the index is left alone.** The Hub does not own `spec/index.json`. It parses it, validates it
and reports on it — `read_index` returns `valid | absent | unreadable | invalid` and a diagnostics
list, and a manifest entry pointing at a file that is not there already surfaces as `missing`. After
a rename that is a *true statement about the operator's file*. Silently editing it to make the
diagnostic go away would mean the Hub writing a document the operator maintains by hand, on the
strength of an inference.

## D5. Ordering: the filesystem move goes last

Validate → check the target is free (database and disk) → update the column and the queue entries in
the transaction → **move the file** → record the event.

The move is last among the things that can fail loudly, because a failed database transaction rolls
back and a failed file move does not. If the move throws, the transaction has not committed and
nothing has changed. If the move succeeds and the commit then fails, the file is at the new path and
the row still names the old one — which `divergence` already models and reports, rather than
corrupting anything.

**Refusals, all before anything moves:** the document is approved; the target path is taken by
another document or an existing file; the subject slugifies to nothing; the resulting path fails
`validate_spec_path`.

## D6. The open document follows the rename

The rename response carries `{"path": <new>, "previous_path": <old>}` and a `spec_updated` SSE event
carries both. The UI's document identity is its path — the React Query key, the router state and
`SpecDocumentPanel`'s `path` prop all hold it — so the panel swaps to the new path and invalidates
the old key.

**Why not introduce an id-keyed frontend now.** It is the structurally better answer and it is a
much larger change: every query key, the URL scheme, the picker, the tree and the bridge are
path-keyed today, and `SpecDocument.id` is currently read by nothing outside
`spec_document_events.document_id`. Making rename work correctly does not require it; the event
carries both paths, which is enough for the one transition that occurs. Recorded here as the thing
to do if a second path-mutating operation ever appears.

## D7. The agent is told to rename, in the turn

`spec_turn_notice(EXPLORING)` gains one sentence: rename the document with `rename_spec_document`
as soon as the interview establishes what it is about.

**Why in the turn notice** rather than only the charter or the tool description. This is the exact
lesson of `2026-08-13-the-spec-tool-reaches-the-agent`: guidance that lives only in standing context
is read before the operator's message exists and loses to whatever the message triggers. The rename
is an action the agent must take *in a particular turn*, on information it acquires *during* that
turn. It belongs in the channel that arrives with the turn.

**Why "as soon as it knows" and not "before submitting".** Binding the rename to submission would
put the placeholder on screen for the whole interview, which is the part an operator watches.

## D8. The two renderer defects

Both in `hub/hub/spec_render.py`, found by reading the first agent-authored document.

**Acceptance criteria render in payload order.** `_acceptance` at `:134` iterates
`payload.acceptance_criteria` as submitted. The live document's criteria run
`FR-1, FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-8, FR-8, FR-7, FR-9`. Sorting by each criterion's
requirement position in `payload.requirements` fixes it, **stably** — criteria for one requirement
keep their submitted order relative to each other, because that order is the author's and carries
their emphasis.

**An empty `open_questions` renders as nothing.** A reader cannot distinguish a document whose
questions were asked and resolved from one where none were ever asked. The section renders with an
explicit "None outstanding" when the list is empty and the document has been written at least once.

Neither is behavioural; both are why the document is read rather than skimmed.
