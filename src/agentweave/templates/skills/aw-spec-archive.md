---
name: aw-spec-archive
description: Archive a completed spec change — moves it to spec/changes/archive/ with a timestamp, merges specs into the project spec library, and produces a completion summary.
---

Archive a completed spec change.

**Project:** {project_name}
**Principal:** {principal}
**Agents:** {agents_list}

---

## Steps

### 1. Select the change

If $ARGUMENTS specifies a change name, use it. Otherwise:
- Scan `spec/changes/` for active changes (not in `archive/`)
- Auto-select if only one exists
- If multiple exist, list them and use **AskUserQuestion** to choose

### 2. Verify it's done

Read `spec/changes/<name>/tasks.md` and check for any unchecked tasks (`- [ ]`).

If incomplete tasks exist:
```
## Not Ready to Archive

Change '<name>' has N incomplete tasks:
- [ ] Task A
- [ ] Task B

Complete all tasks before archiving, or confirm to archive anyway.
```

Use **AskUserQuestion**: "Archive anyway, or return to finish these tasks?"

### 3. Merge specs into project library (optional)

If `spec/changes/<name>/specs/` exists and contains spec files, ask:
> "Merge spec files into the project spec library at `spec/specs/`?"

If yes:
- For each file in `spec/changes/<name>/specs/`:
  - If the file doesn't exist in `spec/specs/`, copy it there
  - If it does exist, ask the user whether to merge, overwrite, or skip

### 4. Archive the change

Determine the archive timestamp:

```bash
date +%Y-%m-%d
```

Move the change to archive:

```bash
mkdir -p spec/changes/archive
mv spec/changes/<name> spec/changes/archive/YYYY-MM-DD-<name>
```

### 5. Show completion summary

```
## Archived: <name>

**Location:** spec/changes/archive/YYYY-MM-DD-<name>/

**What was built:**
[1-2 sentence summary from proposal.md]

**Tasks completed:** N/N

**Contributors:**
- <agent-a> (tech_lead, backend_dev): X tasks
- <agent-b> (frontend_dev): Y tasks

**Specs merged:** [list of files merged to spec/specs/, or "none"]

Change archived successfully.
```

---

## Guardrails

- Always check for incomplete tasks and warn the user before archiving
- Never delete the change directory — always move it (history is preserved)
- Only merge spec files with explicit user confirmation
- If the archive directory already has a folder with the same name, append `-2` (or ask the user)
