# Exploration — The theme does not survive a restart (2026-08-20)

**Status:** Stub. One of eight explore pages opened 2026-08-20 covering the open backlog. Nothing
decided. **This one is a bug, not a feature — and it was investigated once and not solved.**

**Origin:** item 3 of the operator's twelve:

> *"Dark/light mode not saved; always reopens in light."*

---

## What was already checked, and came back clean

From handoff 0063's dead ends — the source path reads correct, which is why this is still open:

- `hub/ui/src/store/configStore.ts` writes `mode` to `localStorage`.
- `hub/ui/src/App.tsx:114-116` reapplies it on mount.
- `SetupModal` seeds from the store and only writes on change.

Nothing in that chain drops the value. So either the write is landing somewhere the read does not
look, or the value is being read from a different storage partition than the one it was written to.

## The leading hypothesis — unconfirmed, and cheap to confirm

**The operator may be opening `localhost:8000` sometimes and `127.0.0.1:8000` other times.** Those
are separate origins to the browser, and therefore separate `localStorage` partitions. A theme set
on one is genuinely absent on the other.

This would explain **two** reported symptoms with one cause: the theme resetting, *and* item 12's
"asking for API key and project id" on reopen — the session key lives in the same partition.

Item 12 turned out to have a second, far more serious cause (the test suite emptying the database,
finding 18). That does not rule this out as an additional contributor; it means the evidence for it
was masked.

**This needs the operator's browser, not the codebase.** The question is one line: what does the URL
bar say between sessions? It has been asked twice and not yet answered.

## Open questions

1. **`localhost` versus `127.0.0.1` — which does the operator actually type?** Answer this before
   any code is written; it may make the rest of this document moot.
2. **If it is the origin split, is the fix a redirect or a canonical host?** Serving a 301 from one
   to the other makes the partitions one, but hard-codes a host choice into the Hub.
3. **Should the theme live in `localStorage` at all?** It is per-operator, per-instance state, and
   the Hub has a database. Storing it server-side survives origin changes, browsers, and machines —
   at the cost of a round trip before first paint, which is exactly the flash-of-wrong-theme problem
   the current design avoids.
4. **Is `prefers-color-scheme` respected as the default?** If the operator's OS is light, "always
   reopens in light" is indistinguishable from "correctly falling back to the system default" — and
   would mean the stored value is simply never found.
5. **Does the same partition hold anything else whose loss would be worse than a wrong theme?** The
   session key, at minimum. Worth enumerating before deciding this is cosmetic.

## Size

Question 1 is a single message to the operator. If the answer is the origin split, the fix is small
and closes two symptoms. If not, this needs a real reproduction in the operator's browser, because
the source path has already been read and is not obviously wrong.
