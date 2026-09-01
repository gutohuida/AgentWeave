# Approvals

The only file the FIX window (23:00-07:00) reads to learn what the operator said. Written by the
DECIDE session, not by hand and not by either scheduled window. Format and semantics: `README.md`
in this directory.

```
- APPROVED  <change-name>   optional note
- REVISING  <change-name>   what needs to change
- REJECTED  <change-name>   why
ORDER: <change-name>, <change-name>, F156      (optional, that night only)
NOTHING TONIGHT                                 (optional, stops the window)
```

Newest day first. Days below the newest are history and are not read.

---

## 2026-09-01

Review page: `review/review-2026-09-01.html`. One change proposed, taken through all three rounds.
Write its row below in the contract's form — the status token goes between the `-` and the change
name. Leaving the row out entirely is undecided, not rejection. **No real token is written here:**
the day window proposed this change and must not appear to have approved its own work, so the line
below is a blank to fill, not a row.

```
- <APPROVED|REVISING|REJECTED>  runner-model-is-chosen-from-the-catalog
```

`runner-model-is-chosen-from-the-catalog` — F173 (A). The runner screen free-types the model against
a shipped requirement that says it must offer the catalog's, and swallows the backend's refusal
entirely. 29 tasks across the API, the picker, the error surface, tests and a drive; retires F173
(A), F219 (C) and F220 (C). Round 2 and round 3 each changed it — the argument in section 4 of the
review page.

If you approve nothing, the FIX window falls to the default queue and lands on open findings, A
first — which is F173 again, by the finding route and without this design. `ORDER:` and
`NOTHING TONIGHT` are both available.

Two decisions on the page are **not** work and want no row here: ratifying the `fastmcp<4` ceiling,
and leaving F188/F190 unproposed as direct repairs.
