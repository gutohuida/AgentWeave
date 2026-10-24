# Rule: which developer builds a change

Decided by the operator, 2026-10-24.

| How the change is built | Builder |
|---|---|
| Unattended, by a flow (a change document whose `delivery` is a flow) | `Developer` (Sonnet) |
| With the operator close to the solution and driving it themselves, turn by turn | `DeveloperOpus` (Opus) |

## How to apply it

- When a change document is written, ask how the operator will build it. A flow names `Developer`
  as its agent. A change the operator will drive is not a flow: its delivery is `none`, and its
  tasks go to `DeveloperOpus` and are started by the operator.
- The rule picks the builder. It does not pick the reviewer: QA still reviews either way.
- First applied to "Checks wait less" (`spec/changes/checks-wait-less-fresh-results-after-master-moves-and-checks-scoped-to-the-paths-they-cover`),
  which `DeveloperOpus` builds.
