# Test guide — the shell judge reads a word whole

## Agent-verifiable

No Hub and no agent turn needed. Every row runs on Linux in `hub-test` and on Windows in the new
`hub-judge-windows` job (design D9). The Windows-only rows run only there.

| What | How | Passes when |
|---|---|---|
| Ordinary shell stops being refused | `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q` (task 1.1) | globs, `@scope/pkg`, `HEAD:path`, `%h/%s`, regexes and `2>/dev/null` are allowed |
| Brace patterns are judged as expanded | same file (tasks 1.2, 1.3) | `.{,.}`, `{.,.}.`, `.{,.}/x`, `src/{a,..}/../y` refused; the same patterns handed to `bash -c` refused; `awk '{print $1, $2}'` allowed |
| A glob cannot reach the parent | same file (tasks 1.4, 1.4b) | `.*/x`, `../*`, `@(..)/x` refused, naming the whole piece |
| **A glob cannot reach through a link** (R4) | same file (task 1.4c), with a real link or junction `up` → outside | `u*/`, `u?/x`, `[u]p/x`, `[[:alpha:]]p/x`, `bash -c 'cp n u*/'` refused, naming where the match resolves; `sub/*.py` and an inside link allowed |
| The bounds hold per call (R4) | same file (tasks 1.4d, 1.6) | a glob over 8193 entries and a 300-alternative brace are refused with the too-many reason; a link cycle answers; the memo charges two readings once |
| Schemeless remotes are network addresses | same file (task 1.5) | `git@github.com:repo` (no separator too), `user@example.com:f`, `127.0.0.1:9/x` refused with the network reason; `alpine@sha256:…`, `x@npm:y`, `host:x/y` not |
| Escapes an inner shell removes are read (R4) | same file (task 1.7c) | `bash -c 'cp n .\./x'` and `bash -c 'bash -c "cp n .\\./x"'` refused |
| The judge always answers | same file (task 1.6) | no exception for pathological braces, brackets, extglobs or backslash runs; a judge made to raise yields a deny with a reason |
| Escapes stay refused | same file (tasks 1.7, 1.7b, 1.7d) plus `test_permission_approver.py` (task 1.8) | every negative control refused; only the listed rows moved |
| Windows rules run in CI (R4) | the `hub-judge-windows` job on the pushed branch (task 2.2c) | the job ran, and the drive, junction and device rows passed there |
| Nothing else moved | full `hub/tests/` (task 2.4) | count recorded |

## Human-only

After the change ships, on the operator's Hub (on `:8000` the edited file is used from the next run):

1. Ask an agent under the default posture to "run the tests in `test/*.test.js` and silence stderr
   with `2>/dev/null`". **Expect:** no refusal.
2. Ask it to `npm install @types/node` or `git show HEAD:README.md`. **Expect:** no filesystem
   refusal (the install may still be refused if it names a URL).
3. Ask it to copy a file with `cp notes.md .{,.}/`. **Expect:** a refusal naming `'..'`.
4. (R4) In a scratch project, make a junction inside the agent's workspace that points outside it
   (`New-Item -ItemType Junction -Path lnk -Target <outside dir>`), then ask the agent to
   `cp notes.md l*/`. **Expect:** a refusal naming where `lnk` resolves. Delete the junction
   afterwards.
5. Watch the activity log for refusals whose quoted word is a fragment of a longer word (for
   example `'/x'` out of `a/x`). **Expect:** none; report any.
