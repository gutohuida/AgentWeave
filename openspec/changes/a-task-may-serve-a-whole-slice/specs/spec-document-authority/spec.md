## REMOVED Requirements

### Requirement: A declared task's requirement span is capped, and the Hub enforces it

**Reason**: The operator removed the ceiling (2026-10-05, Q15) so that a slice of about a dozen
requirements can be built as a few tasks. The incident it guarded against, a rejected
requirement hidden inside a task read as done, is now refused at approval at every rigor
(`task-lifecycle-governance`, "Approval is refused while a gated requirement is unverified"),
and the task card shows each requirement's state.

**Migration**: None. Documents that were refused for a task naming more than three requirements
become proposable. A requirement served by no task is still refused.
