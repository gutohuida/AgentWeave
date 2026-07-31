# Future directions — parking lot

Ideas raised during the `2026-07-30-hub-native-experience` design work that are **deliberately out
of scope** for that change, captured so they are not lost and can be deep-dived later.

Nothing here is committed. Each entry records the idea, why it came up, what it would change, and
what would have to be true before it is worth starting.

---

## 1. AgentWeave Colab — the Hub as a shared, remote collaboration surface

**Where it came from.** Deciding that the *local* MCP server should die once the Hub owns execution
directly. If agents run on your machine and the Hub is on your machine, MCP is indirection for its
own sake. But that raised the inverse: MCP is exactly the right protocol when the thing you are
talking to is **not** on your machine.

**The idea.** A hosted (or self-hosted, remote) AgentWeave that groups of agents — and groups of
*people* — connect to over MCP. Not a remote variant of the local Hub, but a genuinely different
product: a place where separate machines, each running their own local AgentWeave, federate.

**Why it becomes easier after this change, not harder.** Once the local Hub owns a hardened
execution environment, that machine can expose a *narrow, explicit set of endpoints* to the remote
Colab surface — "these are the things you may ask my machine to do." Execution stays local and
sandboxed; coordination goes remote. That is a much safer shape than a remote service holding
credentials and spawning processes, and it only becomes available because the local runtime work
happens first.

**What would need to be true first.** The local experience is good enough that someone wants a
second person in it. Federation is worthless without a first party who is happy.

---

## 2. Non-development agents — domain personas, directives, and packages

**Where it came from.** Everything in the current change assumes software development. But the
coordination substrate is not development-specific: a document-reading agent that emits structured
data to an underwriting agent that produces a decision file is the same machinery with different
content.

**Why the charter model already generalises.** The change retires *job-title personas for
developers* (`tech_lead`, `backend_dev`) because they were personality without boundary. It replaces
them with a charter — **purpose · scope · default skills**. A domain agent is not an exception to
that model; it is the model working as intended:

- purpose — "underwrite submissions against the current rule set"
- scope — reads structured submissions, writes decision files, touches nothing else
- skills — the invocable capability for the actual work

So a domain agent needs no new concept. What it needs is **distribution**.

**The idea: packages.** A portable bundle of charter + skills + any schemas or templates, which a
user can customise, export, and import. Someone builds an underwriting pack; someone else installs
it and adapts it. This is the "roles you can play with" experience, done as artifacts rather than as
a fixed enum in `constants.py`.

**Constraint this places on the current change.** If packages are on the horizon, the charter must
be designed as a **portable artifact** from the start — a file with a stable shape, not an internal
configuration blob. That costs almost nothing now and is expensive to retrofit. *This is the one
item here that should influence Phase 7 even though packages themselves are out of scope.*

**What would need to be true first.** Developer use is genuinely good, and at least one real
non-development workflow has been run by hand to prove the shape.

---

## 3. AgentWeave as sandbox → provisioning platform

**Where it came from.** If agent structures become exportable packages, the local app becomes the
place you *design and test* a configuration of agents — and something else becomes the place you
*run it at scale*.

**The idea.** Local AgentWeave is the sandbox: compose agents, charters, skills, and gates; watch
them work; iterate. Then export that structure to a platform that provisions the agents on
infrastructure, on a schedule, or against a queue of real work.

**Relationship to the other two.** This is the natural end of (1) and (2) together: packages give
you a portable unit, Colab gives you a shared surface, and provisioning gives you scale. They should
be evaluated as one direction, not three.

**What would need to be true first.** A package that someone other than its author has run
successfully, and demand for running it somewhere other than a laptop.

---

## Note on sequencing

All three depend on the same precondition: **the local, single-user, development-focused experience
being genuinely good.** That is what `2026-07-30-hub-native-experience` is for. None of these should
start before it lands, and the strongest argument for each of them is that it becomes *cheaper*
once it does.
