# Exploration — Who implements this spec (2026-08-20)

**Status:** Stub. One of eight explore pages opened 2026-08-20 covering the open backlog. Nothing
decided.

**Origin:** item 11 of the operator's twelve:

> *"The spec should have a field for which agent will implement it, so approval auto-assigns."*

---

## What exists today

`SpecDocument` (`hub/hub/db/models.py:1618-1653`) has: `id`, `project_id`, `path`, `title`, `kind`,
`phase`, `content_digest`, `requirement_digests`, `rigor`, `explore_closed_at`, `created_at`,
`updated_at`.

**There is no implementer, assignee or owner field.** So this needs a column, a migration, and a
place in the payload — the mechanical part is the well-trodden path in `CLAUDE.md`'s *"Adding a
database column"*.

The interesting part is the second half of the sentence: **"so approval auto-assigns."**

## The two halves are different sizes

1. **A field.** One nullable column, exposed on the schema, editable in the UI. Small, and useful on
   its own — even as pure documentation, "this one is Developer's" is worth recording.
2. **Approval auto-assigns.** This wires the spec lifecycle to the task system: on
   `approved`, create tasks and assign them. That is a behavioural coupling between two subsystems
   that are currently independent, and it is where the real design is.

Worth deciding whether to ship 1 first. It is independently valuable and it lets the operator use
the field before the automation exists, which is also the cheapest way to learn what the automation
should do.

## Open questions

1. **What does approval create — one task, or one per requirement/task in the document?** The payload
   already carries a `tasks` list (`submit_spec_document`'s `tasks` parameter), so the document may
   already say. If so, auto-assign means "create those, assigned to the named agent".
2. **Is the field on the document or on each task?** A document may reasonably be implemented by
   several agents. A single field forces one; a per-task field is more honest but more to fill in.
3. **What if the named agent no longer exists** when the document is approved? Agents are roster
   identities that can be deleted. Refuse the approval, or approve and leave the tasks unassigned?
4. **Should the *agent* be allowed to set it,** or only the operator? An agent nominating itself as
   implementer is close to self-delegation. Compare `decide_evidence`, which explicitly refuses to
   let an agent decide evidence it produced itself (`mcp_server.py:1127`) — there is an established
   principle here worth applying.
5. **Does auto-assign also trigger a run?** Assigning is not the same as starting. Starting work the
   moment the operator approves may be exactly what they want, or may be alarming.
6. **Is "implementer" a binding to an agent, or to a charter/runner?** Agents are bound to at most one
   runner and one charter. Naming an agent names all three; naming a charter says *what kind of*
   agent should do this and survives roster changes.

## Size

Half 1 is small and follows an established recipe. Half 2 is a genuine design question about how the
spec lifecycle and the task lifecycle meet — and that seam is where the loop explorations
(`2026-08-14-loop7`, `2026-08-13-loop5`) have historically found the failures.
