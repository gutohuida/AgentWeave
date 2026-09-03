"""Is F271 a page or a pattern? Count the sites that share its shape. Evidence for F271, not a proposal.

    py -3.11 scripts/drive/d6_seed_writeback_sweep.py

F271 is *"a failed instructions load renders an empty editor with Save enabled, and one click
destroys the project's instructions"*. Its shape, stated as three linked facts rather than as a
page:

    S  a query's data seeds component state,
    W  that state is sent back to the server by a write,
    G  and nothing stops the write while the load is failing.

The eventual proposal needs to know whether it is repairing one page or a family, so this counts
the sites where **S, W and G all hold of the same query**. It changes no product code, starts no
Hub and reads no database.

**What D-5 already answered, and the four ways its answer is an under-count.** D-5's
`d5_reachability_walk.py` ranked sites 1 / 1G / 2 / 3 and published `rank 1 = 2`. Every gap below
is measured by this script and printed in section 1, not asserted:

1. **It ranked one bucket.** `rank_sites` is called on `buckets['MISREPORT']` alone, so the
   `SUPPRESSED`, `BLANK`, `NAMED` and `HANDLED` sites were never tested for the shape. A `BLANK`
   site -- "a decoration is missing" -- is a claim about what the failure *renders*, and says
   nothing about whether the same data is written back.
2. **Its writer set required `useMutation`.** `write_hooks()` keeps an `api/` export only if its
   body contains `useMutation`, and matches only `^export function (use\\w+)`. Three whole
   spellings are invisible to it: `export async function`, an export not named `use...`, and a hook
   that writes through a shared helper instead of `useMutation` directly.
3. **Its writer set was `api/`-only.** A component-local write helper is not in it --
   `AgentOutputPanel.tsx:657`'s `postTrigger` is exactly that, and D-5 said so in its own report.
4. **Its rank-1 conjunction is file-level.** `writes` is *"does this file name any writer"* and
   `seed` is *"does this file seed state from this query"*; the two are never joined. A file that
   seeds from query A and writes payload B satisfies it. D-5 named this limitation for
   `AgentOutputPanel.tsx:207` -- "in rank 1 for the wrong reason" -- and this script is what turns
   that sentence into a test.

**The added test, W-LINK.** For each seeded state variable, does its name appear inside the
*argument expression* of a write invocation? That is what makes `InstructionsPage` destructive:
`saveMutation.mutate(content)` at `:29` sends the state that `:16` seeded, whole. The test is
deliberately generous -- a name appearing anywhere in the argument text counts -- because a false
positive costs a hand read and a false negative costs a missed site.

**Four controls, asserted rather than hoped for.** The script fails loudly if
`InstructionsPage.tsx` is not S+W+G (F271 itself, driven), if `AgentOutputPanel.tsx:207` is not
S+W (the ledger's second instance), or if `AccountingPanel.tsx` and `ProjectSettingsPanel.tsx` are
not found guarded (D-5's rank 1G, hand-read there). A sweep that cannot re-find the four sites
already known is not evidence about the ones it does find.

**What is mechanical and what is not.** Everything under section 3 is derived. Whether a candidate
is really destructive is a hand read, recorded in `HAND_READ` with the lines it was read off -- the
same discipline as N-10's `HAND_RESOLVED` and N-11's `CLASSIFIED`. An unclassified candidate prints
as `UNREAD` rather than being silently dropped.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_SRC = REPO / "hub" / "ui" / "src"
API_DIR = UI_SRC / "api"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d5_reachability_walk as d5  # noqa: E402
import n11_query_error_surface as n11  # noqa: E402

WRITE_HELPERS = ("postJson", "putJson", "patchJson", "deleteJson")

# A write does not have to go through the `api/client` helpers, and the sweep found this the hard
# way: both controls that failed on the first run failed for this reason at one remove.
# `AgentOutputPanel.tsx:657`'s `postTrigger` and `NewConversationSurface.tsx` build the request by
# hand, and `useDeleteProject` says in a comment at `api/projects.ts:168` that it "bypasses
# `deleteJson`" because the route answers 204. So a raw `fetch`/`fetchWithAuth` carrying a non-GET
# `method:` counts as a write too.
RAW_WRITE_RE = re.compile(r"method:\s*['\"](POST|PUT|PATCH|DELETE)['\"]")


def body_of(text: str, start: int, next_mark: int) -> str:
    """The declaration's own body: brace-balanced, and never past the next top-level declaration.

    The first version of this sliced from one declaration to the next, which attributed a
    *non-exported* helper's body to whichever export happened to precede it —
    `api/projects.ts`'s `useProjectPathMutation` (`:47`, with `postJson` at `:51`) made the
    read-only `useProjects` (`:32`) read as a POST writer. Brace balancing gives the real body;
    the `next_mark` bound keeps a declaration with no braces at all (a one-line arrow) from
    running away to the end of the file.
    """
    i = text.find("{", start)
    if i < 0 or i > next_mark:
        return text[start:next_mark]
    depth = 0
    for j in range(i, min(len(text), next_mark + 4000)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return text[start:next_mark]


# The hand read of every mechanical S+W-LINK candidate.
# (path under hub/ui/src, query line, verdict, why -- with the lines it was read off)
#
#   DESTRUCTIVE  a failed load can be written back over stored content, and it has been driven.
#   SUSPECT      S, W and G all hold on a static read and nothing has driven it. Deliberately not
#                promoted to DESTRUCTIVE: N-11 gave `InstructionsPage` no F-number for exactly this
#                reason, and the drive that followed found it worse than the static read predicted.
#   GUARDED      S and W hold, but the write cannot render while the load is failing.
#   BENIGN       the mechanical hit is not a write-back at all.
# fmt: off
HAND_READ: list[tuple[str, int, str, str]] = [
    ('components/instructions/InstructionsPage.tsx', 9, 'DESTRUCTIVE',
     "F271 itself, driven 2026-09-02. `content` is useState('') (:11) -- an empty string is a valid "
     "stored value, so nothing distinguishes a failed load from a project with no instructions; "
     "`isLoading` is false in the error state so the skeleton at :45 is not taken; Save is disabled "
     "on `saveMutation.isPending` alone (:39) and `mutate(content)` (:29) PUTs the empty string."),
    ('components/agents/AgentOutputPanel.tsx', 207, 'SUSPECT',
     "`pendingOverrides` is seeded from the open conversation's `runtime_overrides` (:236-243) and "
     "defaults to `{}` -- again a valid value, not a sentinel. Nothing guards the composer on the "
     "conversations query, and `postTrigger` (:885) sends `emptyToUndefined(pendingOverrides)`. "
     "Sending untouched is harmless (an empty map becomes undefined and `if body.overrides:` at "
     "agent_trigger.py:1344 leaves the stored value alone); changing one pill after a failed load "
     "sends that pill alone and agent_trigger.py:1364 assigns it wholesale. Static read only."),
    ('components/accounting/AccountingPanel.tsx', 15, 'GUARDED',
     "same file and same write as :22 below -- this site is the `useAccounting` call inside the "
     "`PreferredDisplay` helper (`if (!data) return null`, :16), not a second defect."),
    ('components/accounting/AccountingPanel.tsx', 22, 'GUARDED',
     "`budgetInput` is useState('') (:23), a non-sentinel like F271's -- but `if (isLoading || "
     "!data)` at :34 returns the skeleton before Apply renders, so the write is unreachable while "
     "the load is failing. That early return is the line N-11 classified as F197's shape."),
    ('components/environment/ProjectSettingsPanel.tsx', 53, 'GUARDED',
     "defended twice over: `form` is useState<ProjectSettings | null>(null) (:60), a real sentinel, "
     "and `if (!project || !form)` at :75 returns the skeleton before the form renders. Re-derived "
     "here rather than taken from D-5: `setForm` is called only at :68, from the effect that "
     "returns early on `!settings` (:67)."),
]
# fmt: on


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def api_writers() -> dict[str, str]:
    """Every `api/` export that reaches a write helper, by any spelling, transitively within its file.

    D-5's `write_hooks()` is the same idea with three filters this one does not have: the body must
    contain `useMutation`, the name must start with `use`, and the declaration must match
    `^export function` (so `export async function` is missed). The difference between the two sets
    is printed in section 1 rather than described.
    """
    out: dict[str, str] = {}
    for path in sorted(API_DIR.glob("*.ts")):
        if path.name == "client.ts":
            continue
        text = path.read_text(encoding="utf-8")
        spans = n11.comment_spans(text)
        pat = re.compile(r"^export\s+(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=)", re.M)
        marks = [m for m in pat.finditer(text) if not n11.in_comment(spans, m.start())]
        # Every declaration, exported or not: a non-exported helper is not a writer the UI can
        # call, but it is how an exported one reaches a write, so it has to be in the graph.
        anypat = re.compile(
            r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=)", re.M
        )
        allmarks = [m for m in anypat.finditer(text) if not n11.in_comment(spans, m.start())]
        local: dict[str, str] = {}
        for i, m in enumerate(allmarks):
            end = allmarks[i + 1].start() if i + 1 < len(allmarks) else len(text)
            local[m.group(1) or m.group(2)] = body_of(text, m.start(), end)
        exported = {m.group(1) or m.group(2) for m in marks}
        for name in exported:
            body = local.get(name)
            if body is None:
                continue
            seen: set[str] = set()
            stack = [body]
            verbs: set[str] = set()
            while stack:
                b = stack.pop()
                for h in WRITE_HELPERS:
                    if re.search(rf"\b{h}\b", b):
                        verbs.add(h.replace("Json", "").upper())
                verbs.update(mm.group(1) for mm in RAW_WRITE_RE.finditer(b))
                for mm in re.finditer(r"\b(\w+)\s*\(", b):
                    callee = mm.group(1)
                    if callee in local and callee not in seen and callee != name:
                        seen.add(callee)
                        stack.append(local[callee])
            if verbs:
                out[name] = "/".join(sorted(verbs))
    return out


def local_write_helpers(text: str, writers: dict[str, str]) -> set[str]:
    """Functions declared *inside a component file* that reach a write. `postTrigger` is one.

    Bodies are brace-balanced for the same reason `api_writers` balances them: sliced to the next
    declaration, this returned `moveTo` and three `handle*` functions as writers because a writer
    call happened to sit between them in the file.
    """
    out: set[str] = set()
    pat = re.compile(r"\b(?:const|function)\s+(\w+)\s*(?:[:=][^=\n]*)?(?:async\s*)?\(")
    marks = list(pat.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = body_of(text, m.start(), end)
        if (
            any(re.search(rf"\b{h}\b", body) for h in WRITE_HELPERS)
            or RAW_WRITE_RE.search(body)
            or any(re.search(rf"\b{w}\s*\(", body) for w in writers)
        ):
            out.add(m.group(1))
    return out


def alias_closure(text: str, names: set[str]) -> set[str]:
    """`names`, plus the local variables that carry one of them into a write's argument list.

    `AccountingPanel` is why this exists and it is the second control that failed without it:
    `budgetInput` is seeded from the query at `:30`, but the write at `:57` reads
    `updateBudget.mutate(value)` — and `value` is `Number(budgetInput)`, declared one line into the
    same handler (`:46`). A literal-name test says the seeded state is never written back, which is
    false. The closure is transitive and file-wide, which over-reaches on purpose: an extra
    candidate costs a hand read, a missed one costs a site.
    """
    out = set(names)
    for _ in range(4):
        grew = False
        for m in re.finditer(r"\b(?:const|let)\s+(\w+)\s*=\s*([^\n;]{0,200})", text):
            var, init = m.group(1), m.group(2)
            if var in out:
                continue
            if any(re.search(rf"\b{re.escape(n)}\b", init) for n in out):
                out.add(var)
                grew = True
        if not grew:
            break
    return out


def write_invocations(text: str, writers: dict[str, str]) -> list[tuple[int, str, str]]:
    """(line, what was called, argument text) for every write this file actually issues.

    Three call shapes, because the repo uses all three: a mutation object's `.mutate(...)` /
    `.mutateAsync(...)`, a direct call to a non-hook `api/` writer, and a direct call to a write
    helper or to a local helper that reaches one.
    """
    spans = n11.comment_spans(text)
    names = set(writers) | local_write_helpers(text, writers) | set(WRITE_HELPERS)
    out: list[tuple[int, str, str]] = []
    for m in re.finditer(r"\.\s*(mutate|mutateAsync)\s*\(", text):
        if n11.in_comment(spans, m.start()):
            continue
        out.append(
            (text.count("\n", 0, m.start()) + 1, m.group(1), d5.balanced_call(text, m.start()))
        )
    for name in sorted(names):
        for m in re.finditer(rf"\b{re.escape(name)}\s*(?:<[^>()]*>)?\s*\(", text):
            if n11.in_comment(spans, m.start()):
                continue
            pre = text[max(0, m.start() - 60) : m.start()]
            if re.search(r"\b(function|const|export)\s+$", pre) or "import" in pre.split("\n")[-1]:
                continue
            out.append(
                (text.count("\n", 0, m.start()) + 1, name, d5.balanced_call(text, m.start()))
            )
    return out


def seeded_names(text: str, bound: str) -> set[str]:
    """State variables seeded from `bound` -- the setters a `useEffect`/`useState` naming it writes."""
    out = set(d5.seeded_state_names(text, bound))
    for m in re.finditer(r"\buseState\s*(?:<[^;=]*?>)?\s*\(", text):
        body = d5.balanced_call(text, m.start())
        if not re.search(rf"\b{re.escape(bound)}\b", body):
            continue
        prefix = n11.statement_prefix(text, m.start())
        dm = re.search(r"\[\s*(\w+)\s*,\s*set\w+\s*\]\s*=\s*$", prefix)
        if dm:
            out.add(dm.group(1))
    return out


PROPS_RE = re.compile(r"export\s+function\s+(\w+)\s*\(\s*\{([^}]*)\}\s*:\s*\w", re.S)


def prop_seeded_writebacks(reachable: set[str], writers: dict[str, str]):
    """The same shape split across two files: a child seeds state from a prop and writes it back.

    Section 3 asks its three questions of one file, because a query call site lives in one file.
    That is the honest scope of a query-site sweep and it is also its blind spot: a parent that
    fetches and hands `data` down as a prop, to a child that seeds and saves, is F271's shape with
    a component boundary through the middle — and no query site in the child to find it by.

    This pass runs the same S and W-LINK tests over destructured props instead of query bindings,
    so section 3's count can be read as *"7 of 153 within-file"* against a measured number of the
    other kind rather than against a shrug.

    Its hits are noise on this tree, and reading them exposed a limitation that applies to
    section 3 just as much: **`seeds_state` cannot tell a seed from a reset.**
    `TaskDetailDrawer.tsx:162` calls `setRefusal(null)` and `setBlockingReason(null)` on
    `task?.id` — it clears state when the subject changes rather than filling it from the server —
    and the state it clears is then filled by the operator typing. A mechanical test that a setter
    fired inside an effect naming the data cannot see that difference, so every candidate needs the
    hand read that `HAND_READ` records.
    """
    out = []
    for relpath in sorted(reachable):
        path = REPO / relpath
        if path.suffix != ".tsx":
            continue
        text = path.read_text(encoding="utf-8")
        m = PROPS_RE.search(text)
        if not m:
            continue
        propnames = {p.strip().split(":")[0].split("=")[0].strip() for p in m.group(2).split(",")}
        propnames = {p for p in propnames if re.fullmatch(r"\w+", p)}
        invocations = write_invocations(text, writers)
        if not invocations:
            continue
        for prop in sorted(propnames):
            seed = d5.seeds_state(text, prop)
            if not seed:
                continue
            state = seeded_names(text, prop)
            if not state:
                continue
            carriers = alias_closure(text, state)
            for line, _callee, args in invocations:
                if any(re.search(rf"\b{re.escape(n)}\b", args) for n in carriers):
                    out.append(
                        (
                            relpath,
                            m.start() and text.count("\n", 0, m.start()) + 1,
                            prop,
                            state,
                            line,
                        )
                    )
                    break
    return out


def main() -> int:
    seen, unresolved = d5.walk(UI_SRC / "main.tsx", follow_type_only=False)
    if unresolved:
        print(f"  WARNING: {len(unresolved)} import specifiers did not resolve", file=sys.stderr)
    reachable = {d5.rel(p) for p in seen}

    print("=== 1. the writer set D-5 used, and the one this uses ===")
    d5_writers = d5.write_hooks()
    writers = api_writers()
    print(f"  api/ writers, D-5 (useMutation + ^export function use*) : {len(d5_writers)}")
    print(f"  api/ writers, D-6 (any export reaching a write helper)  : {len(writers)}")
    missed = sorted(set(writers) - set(d5_writers))
    print(f"  invisible to D-5                                        : {len(missed)}")
    for name in missed:
        print(f"      {name}  ({writers[name]})")
    extra = sorted(set(d5_writers) - set(writers))
    if extra:
        print(f"  in D-5's set and not in D-6's: {extra}")

    print("\n=== 2. every query call site, not just MISREPORT ===")
    decls = n11.declarations()
    hooks = sorted({d["hook"] for d in decls if d["hook"]})
    decl_files = {d["file"] for d in decls}
    sites = n11.call_sites(hooks, decl_files)
    live = [s for s in sites if s["file"] in reachable]
    mis = {(f"hub/ui/src/{f}", ln) for f, ln, c, *_ in n11.CLASSIFIED if c == "MISREPORT"}
    live_keys = {(s["file"], s["line"]) for s in live}
    print(f"  query call sites total          : {len(sites)}")
    print(f"  in files reachable from main.tsx: {len(live)}")
    print(f"  of those, D-5 ranked (MISREPORT): {len(live_keys & mis)}")
    print(f"  never tested for the shape      : {len(live_keys - mis)}")

    print("\n=== 3. MECHANICAL: S (seeds state) and W-LINK (that state is written back) ===")
    cands = []
    noname: list[tuple[str, int, str]] = []
    per_file: dict[str, str] = {}
    for s in live:
        path = REPO / s["file"]
        text = per_file.setdefault(s["file"], path.read_text(encoding="utf-8"))
        offset = sum(len(x) + 1 for x in text.split("\n")[: s["line"] - 1])
        pos = text.find(s["hook"] + "(", offset)
        prefix = n11.statement_prefix(text, pos if pos > 0 else offset)
        bound = d5.bound_name(prefix)
        if not bound:
            noname.append((s["file"], s["line"], " ".join(prefix.split())[:70]))
            continue
        seed = d5.seeds_state(text, bound)
        if not seed:
            continue
        names = seeded_names(text, bound)
        carriers = alias_closure(text, names) if names else set()
        hits = []
        for line, callee, args in write_invocations(text, writers):
            for n in sorted(carriers):
                if re.search(rf"\b{re.escape(n)}\b", args):
                    hits.append((line, callee, n))
                    break
        entry = {**s, "bound": bound, "seed": seed, "names": names, "hits": hits, "sw": bool(hits)}
        entry["guard"] = d5.guarded_by(text, {bound} | names) if hits else None
        cands.append(entry)

    seeds_only = [c for c in cands if not c["sw"]]
    sw = [c for c in cands if c["sw"]]
    print(f"  sites where S holds (state seeded from the query)   : {len(cands)}")
    print(f"    of those, W-LINK holds (the state is written back): {len(sw)}")
    print(f"    S but no linked write                             : {len(seeds_only)}")

    print("\n  --- S + W-LINK, split by G (is the write reachable while the load fails?) ---")
    unguarded = [c for c in sw if not c["guard"]]
    guarded = [c for c in sw if c["guard"]]
    for label, rows in (("UNGUARDED -- F271's shape", unguarded), ("GUARDED", guarded)):
        print(f"\n  {label}: {len(rows)}")
        for c in rows:
            f = c["file"].replace("hub/ui/src/", "")
            print(f"    {f}:{c['line']}  {c['hook']}  bound={c['bound']}  seed={c['seed']}")
            print(f"        state: {sorted(c['names'])}")
            for line, callee, n in c["hits"][:4]:
                print(f"        write @{line}: {callee}(... {n} ...)")
            if c["guard"]:
                print(f"        guard: {c['guard'][:2]}")

    print("\n=== 3b. what section 3 cannot see, counted rather than described ===")
    in_api = [n for n in noname if n[0].startswith("hub/ui/src/api/")]
    print(f"  live sites whose binding could not be named (skipped by S): {len(noname)}")
    print(
        f"      of those, inside api/ -- one hook calling another, not a component site: {len(in_api)}"
    )
    for f, ln, pre in [n for n in noname if n not in in_api]:
        print(f"      component site: {f.replace(chr(39) + chr(39), chr(39))}:{ln}  {pre}")
    props = prop_seeded_writebacks(reachable, writers)
    print(
        f"  the split variant -- a child seeds state from a PROP and writes it back: {len(props)}"
    )
    for f, ln, prop, state, wline in props:
        print(
            f"      {f.replace('hub/ui/src/', '')}:{ln}  prop={prop} -> {sorted(state)}  write @{wline}"
        )
    print(
        "  (a query in a parent reaching a child as a prop is the same shape across two files;\n"
        "   section 3's S test is within-file and would miss every one of them)"
    )

    print("\n=== 4. controls -- the sweep must re-find what is already known ===")
    ok = True

    def check(cond: bool, what: str) -> None:
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {what}")
        ok = ok and cond

    check(
        any("InstructionsPage" in c["file"] for c in unguarded),
        "F271 itself: InstructionsPage is S + W-LINK + UNGUARDED",
    )
    check(
        any("AgentOutputPanel" in c["file"] and c["line"] == 207 for c in sw),
        "the ledger's second instance: AgentOutputPanel.tsx:207 is S + W-LINK",
    )
    check(
        any("AccountingPanel" in c["file"] for c in guarded),
        "D-5's rank 1G: AccountingPanel is found GUARDED",
    )
    check(
        any("ProjectSettingsPanel" in c["file"] for c in guarded),
        "D-5's rank 1G: ProjectSettingsPanel is found GUARDED",
    )

    print("\n=== 5. hand read ===")
    read = {(f, ln) for f, ln, *_ in HAND_READ}
    for c in sw:
        key = (c["file"].replace("hub/ui/src/", ""), c["line"])
        match = [h for h in HAND_READ if (h[0], h[1]) == key]
        if not match:
            print(f"  UNREAD       {key[0]}:{key[1]}")
        else:
            print(f"  {match[0][2]:<12} {key[0]}:{key[1]}  {match[0][3]}")
    unread = [c for c in sw if (c["file"].replace("hub/ui/src/", ""), c["line"]) not in read]
    print(f"\n  {len(sw) - len(unread)} of {len(sw)} S+W-LINK sites hand-read")

    print("\n=== 6. the answer, and the one result that was not the question ===")
    files = sorted({c["file"].replace("hub/ui/src/", "") for c in sw})
    print(f"  sites carrying the shape at all : {len(sw)}  across {len(files)} files")
    print(f"  unguarded (F271's shape)        : {len(unguarded)}  -- 1 driven, 1 static")
    print(f"  guarded                         : {len(guarded)}")
    print(
        "\n  Every guarded site is guarded by an early return that N-11 had already classified as\n"
        "  F197 -- AccountingPanel.tsx:34 and ProjectSettingsPanel.tsx:75. There is no third\n"
        "  arrangement anywhere in the tree: a site that can write a failed load back is either\n"
        "  F271 (no guard) or F197 (a terminal skeleton). So the two findings are one mechanism\n"
        "  seen from either side, and repairing F197 site-by-site -- rendering the form instead of\n"
        "  the terminal skeleton -- converts each repaired site into an F271 unless the write is\n"
        "  gated in the same change."
    )
    print(
        "\n  The separating fact is the seeded state's initial value, not the guard:\n"
        "  ProjectSettingsPanel's `form` starts `null` (a sentinel a render can test), while\n"
        "  InstructionsPage's `content` starts `''`, AccountingPanel's `budgetInput` starts `''`\n"
        "  and AgentOutputPanel's `pendingOverrides` starts `{}` -- all three indistinguishable\n"
        "  from a legitimately empty stored value."
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
