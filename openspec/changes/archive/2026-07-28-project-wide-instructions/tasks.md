## 1. Hub DB

- [x] 1.1 Add `ProjectInstructions` model to `hub/hub/db/models.py` (`project_id` PK, `content` Text, `updated_at` DateTime)
- [x] 1.2 Ensure table is created in `hub/hub/db/engine.py` (add to metadata / create_all)

## 2. Hub API

- [x] 2.1 Create `hub/hub/api/v1/instructions.py` with `GET /api/v1/project/instructions` (returns `{ "content": "" }` if no row)
- [x] 2.2 Add `PUT /api/v1/project/instructions` endpoint in same file (upsert `ProjectInstructions` row)
- [x] 2.3 Register instructions router in `hub/hub/main.py`
- [x] 2.4 Modify `_load_role_content` in `hub/hub/api/v1/agents.py` to accept `project_id` and fetch + prepend `ProjectInstructions` content before role guide (separator: `\n\n---\n\n`)
- [x] 2.5 Update `get_agent_context` endpoint to pass `project_id` to `_load_role_content`
- [x] 2.6 Update `register_agent` / `register_session` context loading path to also pass `project_id`

## 3. Hub UI

- [x] 3.1 Create `hub/ui/src/api/instructions.ts` with `useInstructions` (GET) and `useSaveInstructions` (PUT) React Query hooks
- [x] 3.2 Create `hub/ui/src/components/instructions/InstructionsPage.tsx` — textarea, Save button, disclaimer, loading/saving states
- [x] 3.3 Add "Instructions" entry to sidebar navigation in `hub/ui/src/components/layout/Sidebar.tsx`
- [x] 3.4 Add route for Instructions page in `hub/ui/src/App.tsx`

## 4. CLI

- [x] 4.1 In `src/agentweave/cli.py` `cmd_init()`, create `.agentweave/project_instructions.md` placeholder if it does not already exist (empty file with brief comment)
- [x] 4.2 Add `project_instructions.md` to `.gitignore` template (it should not be committed)

## 5. aw-collab-start Skill

- [x] 5.1 Edit `src/agentweave/templates/skills/aw-collab-start.md` — add step 1 to read `.agentweave/project_instructions.md` if it exists and is non-empty (existing steps shift to 2–7)

## 6. Tests

- [x] 6.1 Add Hub API tests for `GET /api/v1/project/instructions` (empty and non-empty cases)
- [x] 6.2 Add Hub API tests for `PUT /api/v1/project/instructions`
- [x] 6.3 Add test for `_load_role_content` prepend behavior (instructions + separator + role guide)
- [x] 6.4 Add CLI test verifying `project_instructions.md` is created on init and not overwritten on re-init
