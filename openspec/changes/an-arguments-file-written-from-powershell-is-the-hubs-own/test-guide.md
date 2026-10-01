# Test guide — an arguments file written from PowerShell is the Hub's own

## Agent-verifiable

1. **The 9.10 form has standing.** Task 1.1's `_decide` assertion fails before the fix
   (`'/x.html' is outside your workspace`) and passes after it, in every posture, with no card under "Ask me".
2. **The literal is data.** Task 1.2 passes. Separately, run each of its rows in real PowerShell 5.1 in a
   scratch workspace (task 3.1) and confirm the file holds the literal verbatim. If a row executes anything,
   such as a `$(…)` that runs, the grammar is wrong.
3. **The smart-quote trap is closed.** Task 1.3 passes. Then, as a mutation, delete the U+2018–U+201B exclusion
   from the literal pattern and confirm 1.3 fails. Restore it.
4. **Near misses are unchanged.** Task 1.4 passes. Each row's `_decide` answer equals the answer with the new
   predicate patched off. (R3) As a mutation, drop the "space or end after the closing quote" requirement and
   confirm that 1.4's `-Value 'a'(Write-Output x)` row fails. On 5.1 that form runs its subexpression.
5. **Only PowerShell.** Task 1.5 passes.
6. **9.10 is met.** Task 3.2: a Copilot spec turn told `shim` writes its arguments file from PowerShell or with
   `create`, runs `aw-tool`, and the submission is recorded. If Copilot's form misses the grammar, that is
   recorded as a finding, not fixed in the drive.

## Human-only

1. On the work PC (managed Copilot, PowerShell, `shim`), under "Ask me", start a specification turn on a
   document and ask the agent to submit it unchanged. If the agent writes the arguments file from PowerShell,
   no card appears for that write or for the `aw-tool` call, and the submission shows on the document. If a
   card does appear, copy the command text it shows into the finding.
2. Same machine, under "Workspace only": a PowerShell write whose JSON value holds a URL (for example, ask the
   agent to send a message containing a link) succeeds, and the message arrives with the link intact.
