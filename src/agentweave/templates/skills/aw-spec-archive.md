---
name: aw-spec-archive
description: Archive a completed spec change. Reads the authoritative spec.html, verifies every task is done and the spec was approved, then moves the change (including spec.html and decision docs) to spec/changes/archive/ with a timestamp.
---

Archive a completed spec change. The authoritative artifact is a single self-contained
`spec.html` (it replaced the old markdown artifacts).

**Project:** {project_name}
**Principal:** {principal}
**Agents:** {agents_list}

**Machine-readable contract:** the metadata and task attributes this skill checks are
defined in `html-spec-conventions.md` (bundled beside this skill).

---

## Steps

### 1. Select the change

If $ARGUMENTS specifies a change name, use it. Otherwise:
- Scan `spec/changes/` for active changes (directories with a `spec.html`, not under `archive/`)
- Auto-select if only one exists
- If multiple exist, list them and use **AskUserQuestion** to choose

### 2. Verify it's done

Read `spec/changes/<name>/spec.html` and check:

1. **Approval:** `aw-spec-status` must be `approved`. If it is still `draft`, warn:
   ```
   ## Not Approved

   spec/changes/<name>/spec.html is still "draft". A change that was never approved
   should normally not be archived as completed work.
   ```
   Use **AskUserQuestion**: "Archive an unapproved spec anyway?"

2. **Tasks:** every `<li class="task">` must have `data-status="done"`. Count incomplete
   tasks (`data-status="pending"`):
   ```bash
   grep -o 'class="task"[^>]*data-status="pending"' spec/changes/<name>/spec.html | wc -l
   ```
   If any remain:
   ```
   ## Not Ready to Archive

   Change '<name>' has N incomplete tasks:
   - [ ] (T3) ...
   - [ ] (T4) ...

   Complete all tasks before archiving, or confirm to archive anyway.
   ```
   Use **AskUserQuestion**: "Archive anyway, or return to finish these tasks?"

Also check AgentWeave task status for pending reviews:
```bash
agentweave task list --status under_review
agentweave task list --status revision_needed
```
If any tasks for this change are `under_review` or `revision_needed`, warn strongly and
ask before archiving — tasks under review are not done.

### 3. Merge specs into the project library (optional)

If `spec/changes/<name>/specs/` exists and contains spec files, ask:
> "Merge spec files into the project spec library at `spec/specs/`?"

If yes, for each file: copy if absent, or ask whether to merge/overwrite/skip if it exists.

### 3b. Decision docs move with the change

Any decision docs produced during apply (under `<docs_path>/` or `.agentweave/code-docs/`
that belong to this change) move automatically with the change directory in the next step
if they live inside it. If they live in a shared docs path, note their location in the
summary rather than moving shared files.

### 4. Archive the change

```bash
date +%Y-%m-%d
mkdir -p spec/changes/archive
mv spec/changes/<name> spec/changes/archive/YYYY-MM-DD-<name>
```

The moved directory includes `spec.html` (the full, approved, completed specification) and
any change-local decision docs.

### 5. Show completion summary

```
## Archived: <name>

**Location:** spec/changes/archive/YYYY-MM-DD-<name>/spec.html
**Status:** approved

**What was built:**
[1-2 sentence summary from the spec's Summary section]

**Tasks completed:** N/N
**Requirements delivered:** FR-1 … FR-N

**Contributors:**
- <agent-a> (tech_lead, backend_dev): X tasks
- <agent-b> (frontend_dev): Y tasks

**Specs merged:** [files merged to spec/specs/, or "none"]

Change archived successfully.
```

---

## Guardrails

- Verify approval status and task completion before archiving; warn clearly on either gap.
- Never delete the change directory — always move it (history is preserved).
- Do not edit `spec.html` during archive except to record archive metadata if needed.
- Only merge spec files with explicit user confirmation.
- If the archive directory already has a folder with the same name, append `-2` (or ask).
