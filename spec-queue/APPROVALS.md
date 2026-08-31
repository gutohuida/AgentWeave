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

No review page yet — the loop was built today and has not run a FILL window. The FIX window, when
first armed, will find no approved rows and spend the whole window on the backlog. That is the
intended behaviour, not a fault.
