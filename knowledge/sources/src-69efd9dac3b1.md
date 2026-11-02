# Idea: a generic dashboard screen that agents build on request

Status: idea from the operator, 2026-10-31. Not decided, not specified.

## The idea, as the operator put it

A dashboard screen, but very generic: a dashboard product where you ask AI to create a dashboard
with data from AgentWeave, from the project, and the agent creates the dashboards in it. Tons of
different dashboards can exist, over all the data from the project, and we just ask AI to do it.

## Architect's first reaction (opinion, not agreed)

- The idea fits: the Hub already holds tasks, runs, evidence, requirements, and agents, and an
  operator's questions about them are hard to predict, so fixed screens never cover them.
- Open design question: what an agent produces. Recommended: a declarative dashboard definition
  (panels, each a named read-only query plus a chart type) that the Hub validates and renders.
  Rejected for now: agent-written HTML or JavaScript, which needs a sandbox and can drift out of
  the app's look.
- Open design question: how the agent reads data. A curated read-only set of datasets gives a
  stable contract; raw SQL reaches everything but ties dashboards to the schema, which migrations
  change.
- The first slice should prove one loop: ask, get one dashboard with live data, ask for a change,
  reopen it later, and see it still working.
