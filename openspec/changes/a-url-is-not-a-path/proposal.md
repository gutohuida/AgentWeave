## Why

Under "Workspace only", the posture every ordinary Claude run gets by default
(`DEFAULT_CLAUDE_PERMISSION_MODE`, `hub/hub/runner_commands.py:66`), the Hub's approver reads a shell
command's text with one regex:

```python
# hub/hub/mcp_server.py:936
_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"'|;&><)]*")
```

The regex does not know where a word starts. It begins a candidate at any `/`, and at any letter
followed by `:/`. That produces four findings, each measured, from one mechanism:

- **F300 (A).** It refuses the request the Hub's own notice tells a run to make:
  `curl "$HUB_URL/api/v1/agent-actions/tasks"` → `'/api/v1/agent-actions/tasks' is outside your
  workspace`.
- **F312 (A).** It refuses every URL, for a filesystem reason. `curl https://example.com/x` →
  `'s://example.com/x' is outside your workspace`, because the `s:` of `https:` was read as a drive
  letter.
- **F321 (A), filed by this round.** It refuses a file in a subdirectory of the run's *own*
  workspace. `python sub/hello.py` → `Denied: '/hello.py' is outside your workspace.` That was
  **observed live** on `claude` 2.1.269 with the argv the Hub builds (`scripts/drive/FINDINGS.md`,
  F321). This breaches the shipped scenario *"Work inside the workspace proceeds"*.
- **F323 (A), filed by R2.** The same regex knows `\` only after a drive letter. So on Windows,
  `echo hi > "..\stray.txt"` in the Bash tool yields no candidate, and it is allowed. Git Bash keeps
  a backslash inside double quotes, and the file lands next to the workspace. That was **observed
  live** on `claude` 2.1.269, through the approver. This breaches the shipped scenario *"Traversal
  and links cannot escape"*.

The operator decided F300 and F312 (`spec-queue/DECISIONS.md`: F312 option C at `:630-656`, F300
narrowed at `:694`). Allow the run's own Hub URL. Refuse every other URL with a reason that names
network access rather than the filesystem. Do not become permissive about URLs in general. Do not
claim that egress is contained. They are one change because *"they must agree on what a URL is"*.

### What R1 measured, and what it changed

**1. A fix that removes only URLs cannot deliver F300's verdict.** The instructed request needs
`-H "Content-Type: application/json"`. FastAPI 0.136.3 parses a body as JSON only under that type or
none, and `curl -d` sends a form type. The regex reads `/json` out of that header and refuses the
command: F321's mechanism, one header away from F300's URL. So the change has to decide where in a
word a path may begin. That makes F321 part of it. F321 would change answer under any such fix
whether or not anybody decided it, so this change decides it.

**2. Where a word may begin is exactly what the regex's accidental refusals depend on.** The
research routine's 2026-09-12 §1 measured this, and R1 re-measured it (`design.md` D2). Five real
escapes are refused today only because the regex matches inside a word: `> ../stray.txt`,
`| tee ../stray.txt`, `cp … ../../stray.md`, `> ~/stray.txt`, and `> "$HOME/stray.txt"`. A plain
word-anchored regex allows all five, and the suite stays green: its only shell tests of `_decide`
are `hub/tests/test_permission_approver.py:103-110`. **This change keeps all five refused, and each
now names the path it refuses.**

**3. The `python -c` shape the verdicts cite as passing `_decide` does not pass it.**
`DECISIONS.md` 1c's table records `_decide → allow` for F301's `python -c` shape. Remedy 1d
(*"notice first … works today on `workspace`"*) is built on that. R1 ran F301's exact command
string (`testbed/scratch/f301shapes/shapes.py`, `S1_python_c`) through `_decide`: **deny**,
`'/api/v1/agent-actions/tasks' is outside your workspace`. The `'/api/…'` string literal is the
path. F312's reproduction's `python -c` has no URL in it, so it does not test this. Option C's
conclusion survives on other witnesses: the filter is still syntax, not containment, because
`curl example.com` (no `/`) is allowed today, and so is any `WebFetch` (D7). **But this change does
not make that `python -c` shape pass either (D6), so a notice rewritten to instruct it would
instruct a refused command.** This is a correction for the operator. It is not re-litigated here.

**4. `WebFetch` to any address is allowed under this posture today**, because `_decide` finds no
path argument in it and allows. So the verdict's URL rule is a rule about *shell command text*, and
this change says so rather than implying a network boundary.

### What R2 found, and what it changed

R2 re-derived the design against today's `_decide` and against a real shell. **R1's word reader
let through sixteen commands that today's regex refuses.** R2 ran five of them in Git Bash on this
machine, and each wrote a file outside the workspace. R1 split words at quote characters, and a
shell does not split there. It removes the quotes and joins the pieces, so `'.'./stray.txt` is
`../stray.txt`. Two more classes came out of the same re-derivation. An address accepted as the
run's own Hub can be used as a relative path that climbs out: `"$HUB_URL/../../../x"`. And a word
can end at the workspace's own name while the shell carries it on into a sibling: `../ws=y/z`.
R1's reader also refused F300's request on Windows whenever the JSON body used bash's `\"`
escapes. R2 replaced the split with a lexer that reads the command as the tool's shell will, and
kept every rule after it (`design.md` D1, D2's E and J rows, D8(f)).

R2 also found that the reason bound did not bound the reason. `repr` can render a 200-character
word as 2,002 characters (D5). And X1's answer depends on the shell: in Git Bash an unquoted
`..\stray.txt` writes *inside*, while a quoted `"..\stray.txt"` writes outside. **Today's
`_decide` allows the quoted one.** It is an escape today, and this change closes it (D2, X1b).

## What Changes

- `_decide` reads a shell command **as the shell that runs it will**. It removes the quotes and
  escapes that shell removes, joins what it joins, and marks what it expands, in the dialect of
  the tool that carries the command: `Bash`, `PowerShell`, or both when the tool is unknown. Then it
  judges each word by what it *is* at its start (`design.md` D1):
  - **A URL with a scheme** is a network address. It is allowed when its scheme, host and port are
    the run's own `HUB_URL`, and it carries no userinfo. Any other is refused, with a reason that
    says it is a network address, names `$HUB_URL` as the one address a shell command may name, and
    points at `ask_user`. A `file:` URL is a path, not a network address. **An address accepted as
    the run's own Hub is still judged as the relative path it spells**, because the shell can write
    to it.
  - **A reference to `HUB_URL`** (`$HUB_URL`, `${HUB_URL}`, `$env:HUB_URL`) followed by nothing, or
    by `/`, `?` or `#` with no expansion after it, is the run's own Hub. That holds only when the
    command names `HUB_URL` nowhere else, so a command cannot reassign it and then use it. It also
    needs the approver to have a `HUB_URL` to compare with. It too is judged as the path it spells.
  - **A word the shell expands at run time into a path** is refused, with a reason saying it cannot
    be checked. That is a variable or a command substitution anywhere in the word, or a leading
    `~`, together with a separator. Today these are refused for a false reason.
  - **An absolute path, or a plain relative path** (word characters and separators only), is
    resolved against the workspace, the relative one joined to it, and refused if it lands outside.
    The reason names the whole path, not a fragment of it. **A word that the shell's argument
    carries on** is judged as the name it continues into.
  - **Anything else containing a separator** falls back to today's reading of that word alone. This
    is the backstop that keeps `@/etc/x`, `-o/tmp/x`, `host:/x` and similar refused exactly as they
    are today.
- A refusal's reason quotes the refused word **bounded as rendered** (D5), so it always fits the
  1000-character `reason` that `POST /agent-actions/permission-decisions` accepts
  (`agent_actions.py:840`). An over-long reason is answered 422, `_report_decision` swallows that,
  and the refusal is never recorded.
- The comment and docstring on `_decide` are rewritten to say what it reads. `docs/reference/
  permission-postures.md` stops describing it as reading "absolute paths out of the command text".
- `agent-capability-plane`'s *"A run whose harness cannot use MCP is told how to reach the plane"*
  has its F300 clause corrected, because that clause becomes false. **Its F301 clause is left
  verbatim**, because `DECISIONS.md` 1d reserves that repair to the notice change.

**What moves, measured on R2's reading of this design** (`design.md` D2, 91 commands): 26
change answer on Windows.
- **21 go from refused to allowed.**
  - Seven are requests to the run's own Hub, by URL or by reference (R11, H1–H4, H15, H16).
  - Five are paths inside the workspace: `sub/hello.py` run and `git add`ed, a pytest node id,
    `origin/main...HEAD`, and `sub/../hello.py` (W1–W5).
  - One is **`curl example.com/x`**. It is the one widening that is not the verdict's, decided in
    D3 (N3).
  - Eight are R2's rows. They are request bodies and commit messages that name a path, a
    PowerShell-escaped request, and `$HUB_URL/../../x`, which writes inside (J1–J4, J7, J8, H2p,
    E14).
- **5 go from allowed to refused.** Four are Windows forms of real escapes: `"..\stray.txt"` in
  the Bash tool, and `..\stray.txt`, `%USERPROFILE%\x` and `$env:USERPROFILE\x` in the PowerShell
  tool. One is `curl "$HUB_URL"@evil.example` (E7).
- **Every other row keeps its answer.** That includes all sixteen escapes R2 found in R1's reader,
  which stay refused.

R1's version of this list counted 12 refused-to-allowed and 16 in total. That was an arithmetic
slip: its own rows W1–W5 are five, not four, so it was 13, and 16 in total.

## Non-goals

- **Containing network access.** The verdict says so, and this change claims nothing more. After
  it, `curl example.com`, `pip install x`, `git push`, `WebFetch`, and a `python -c` that writes no
  path are all still allowed. The reason text says *"a shell command may name only"*, and does not
  say that the network is off.
- **Codex.** On Codex, "Workspace only" decides a command approval by its working directory alone
  (`codex_appserver.py:280-283`). A Codex command reaching `pypi.org` from inside the workspace is
  accepted, and after this change the same command on Claude is refused. That asymmetry is
  **recorded as F322** and not fixed here. Every Codex statement in this change is **unverified**,
  because Codex is undrivable.
- **The notice.** `access_path_notice`'s text is unchanged. Its instructed `curl "$HUB_URL/…"` shape
  becomes a command `_decide` allows. Rewriting the notice is `DIRECTION.md` 2026-09-11 position 4,
  and point 3 above bears on it.
- **Escapes that never passed through the regex.** `cd .. && echo hi > stray.txt`,
  `git -C .. status`, and a `cd` in an earlier call are allowed today and after. The docstring
  already says *"a boundary, not a sandbox"*. They are recorded as pinned rows so nobody reads this
  change as tightening the boundary.

## Capabilities

### Modified Capabilities

- `agent-run-sandboxing`: three ADDED requirements. A network address in a shell command is decided
  as a network address. A path in a shell command is judged by where it resolves, as the shell will
  read it. A refusal's reason fits the record that carries it.
- `agent-capability-plane`: *"A run whose harness cannot use MCP is told how to reach the plane"* is
  MODIFIED, in its F300 clause only.

## Impact

- **Code:** `hub/hub/mcp_server.py`, `_decide` and one new reader beside it. Standard library plus
  fastmcp only, as the module requires. `approve_tool_call` is untouched and keeps **no return
  annotation**.
- **Tests:** `hub/tests/test_permission_approver.py` gains D2's table as pinned `_decide` cases, written **before** the reader changes (tasks §1), a wire-shape case for a network refusal,
  and an agreement test for the reason bound.
- **Docs:** `docs/reference/permission-postures.md`, the *"A shell command declares no path"*
  paragraph.
- **No** migration, no API or schema change, no UI change, no change to `runner_commands.py` or
  `agent_trigger.py`. `HUB_URL` already reaches the approver: `agent_trigger.py:1140-1164` sets it
  in the run's environment, and F300's own drive saw the spawned `mcp_server.py` use it
  (`FINDINGS.md`, F300, *"Confirmed by the same session"*).
- **Findings:** closes F300, F312, F321 and F323 when built and driven. F323 was filed by R2: a
  quoted Windows traversal escapes today, measured live. Leaves F301, F299 and F322 open, and names
  each.
