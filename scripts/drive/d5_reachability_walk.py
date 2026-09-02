"""Which of the UI's files does the app actually load? The reachability walk N-10 and N-11 named.

Both night-window scripts end on the same paragraph: their passes are **depth-1**, so
`n10_route_reachability.py`'s *35 routes with no client* and *reached from hub/ui/src: 110* are a
floor and a ceiling rather than totals, and `n11_query_error_surface.py`'s *101 unhandled call
sites* is an upper bound. The case that defeats depth-1 is F260 — `useMessages` **is** imported, by
`MessagesFeed`, which nothing imports and which is absent from the shipped bundle. Asking "does any
file name this symbol" cannot see a whole dead subtree; only a walk from the entry module can.

    py -3.11 scripts/drive/d5_reachability_walk.py            # the walk and the three re-counts
    py -3.11 scripts/drive/d5_reachability_walk.py --files    # every unreachable file, with why

It changes no product code, starts no Hub and reads no database. It imports the two night scripts
rather than reimplementing them, so every number below differs from theirs by the module filter and
by nothing else.

Method:

1. **The root is `main.tsx`, not `App.tsx`.** `index.html` names `/src/main.tsx`, which mounts
   `App` inside an `ErrorBoundary` — so a walk from `App.tsx` alone would call `ErrorBoundary`
   unreachable. Both roots are reported; the difference between them is the honest measure of how
   much that choice matters.

2. **Edges are static imports, re-exports and dynamic `import()`.** `src/` has no barrel file and
   no dynamic import outside `__tests__/`, so the graph is plain. Every specifier that resolves to
   nothing is printed as `UNRESOLVED` rather than dropped: a silent resolution failure would
   manufacture unreachable files.

3. **Type-only edges are counted separately.** `import type { X } from './Y'` is erased by the
   compiler, so a file reached only that way ships no code. The walk is run both ways and both
   counts are printed; if they agree, the distinction did not matter on this tree.

4. **The walk is checked against the shipped bundle, not trusted.** Every file the walk calls
   unreachable donates the string literals that occur nowhere else under `src/`, and each is
   probed in `hub/hub/static/ui/assets/index-*.js` — all expected absent. A dozen reachable files
   are probed the same way and expected present, so a broken probe fails a control instead of
   inventing a result. Both halves of that rule were forced by a failure: uniqueness by *substring*
   rather than by equality, because `'whitespace-pre-wrap'` is written once in `src/` and ships
   inside another module's class chain; and comment/type/import stripping, because prose in a `//`
   line is not a literal and a string inside a `type` union never reaches the output.

5. **The ranking, which is the point.** F271 (severity A, filed 2026-09-02) is one of N-11's
   unhandled sites that reached the operator destructively: `InstructionsPage` seeds a textarea
   from the query, the failed load leaves it empty, and Save writes the empty string over the
   stored instructions. So the interesting question is not *how many* sites there are but *which
   ones can be written back*. Three tests, in order: does the query's data seed component state
   (`useState(data…)`, or `setX(…)` in a `useEffect` that names it); does the same file write; and
   is there an early return naming that data, which would mean the write never renders while the
   fetch is failing. Rank 1 is the unguarded case — F271's shape — and rank 1G the guarded one,
   which is F197's terminal skeleton and not a destructive write.

   **The mechanical pass proposes; a hand read decides, and on this tree it corrected both ranks.**
   `AccountingPanel` and `ProjectSettingsPanel` moved to 1G only once the guard test existed. The
   surviving `AgentOutputPanel.tsx:207` is in rank 1 for the wrong reason — the writes the script
   matched are the question mutations, while the write that actually carries the seeded state is
   `postTrigger` (`:886`), which is not a `useMutation` hook and so is invisible to it.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_SRC = REPO / "hub" / "ui" / "src"
BUNDLE_DIR = REPO / "hub" / "hub" / "static" / "ui" / "assets"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import n10_route_reachability as n10  # noqa: E402
import n11_query_error_surface as n11  # noqa: E402

SUFFIXES = ("", ".ts", ".tsx", ".d.ts", "/index.ts", "/index.tsx")

STATIC_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*import\s+(?!\()(?:(type)\s+)?(?:[^'"();]*?\sfrom\s+)?['"]([^'"]+)['"]""",
    re.S,
)
REEXPORT_RE = re.compile(
    r"""(?:^|\n)\s*export\s+(?:(type)\s+)?(?:\*|\{[^}]*\})\s*from\s*['"]([^'"]+)['"]""", re.S
)
DYNAMIC_RE = re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]\s*\)""")


def rel(p: Path) -> str:
    return p.resolve().relative_to(REPO).as_posix()


def all_source_files() -> list[Path]:
    return sorted(
        p
        for p in UI_SRC.rglob("*")
        if p.is_file()
        and p.suffix in (".ts", ".tsx")
        and "/__tests__/" not in p.as_posix()
        and ".test." not in p.name
    )


def resolve(spec: str, origin: Path):
    """A specifier -> a file under src/, or None for an external package or an asset."""
    if spec.startswith("@/"):
        base = UI_SRC / spec[2:]
    elif spec.startswith("."):
        base = (origin.parent / spec).resolve()
    else:
        return None  # bare package
    if base.suffix in (".css", ".svg", ".png", ".json", ".ico"):
        return None
    stem = str(base)
    if stem.endswith(".js"):
        stem = stem[:-3]
    for suffix in SUFFIXES:
        cand = Path(stem + suffix)
        if cand.is_file() and cand.suffix in (".ts", ".tsx"):
            return cand.resolve()
    return "UNRESOLVED"


def edges(path: Path) -> list[tuple[str, bool]]:
    """(specifier, type_only) for every import/re-export/dynamic import in the file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    spans = n11.comment_spans(text)
    out = []
    for rx in (STATIC_IMPORT_RE, REEXPORT_RE):
        for m in rx.finditer(text):
            if n11.in_comment(spans, m.start()):
                continue
            out.append((m.group(2), bool(m.group(1))))
    for m in DYNAMIC_RE.finditer(text):
        if not n11.in_comment(spans, m.start()):
            out.append((m.group(1), False))
    return out


def walk(root: Path, follow_type_only: bool):
    seen, unresolved, queue = {root.resolve()}, [], [root.resolve()]
    while queue:
        cur = queue.pop()
        for spec, type_only in edges(cur):
            if type_only and not follow_type_only:
                continue
            target = resolve(spec, cur)
            if target is None:
                continue
            if target == "UNRESOLVED":
                unresolved.append((rel(cur), spec))
                continue
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen, unresolved


TYPE_DECL_RE = re.compile(r"^(?:export\s+)?(?:type|interface)\s+\w", re.M)


def scan_strings(text: str) -> list[str]:
    """Every string literal in `text`, by walking it rather than by pairing quotes.

    A regex that pairs quote characters matches the *gap between* two unrelated strings on one
    line, which is where `', projectId, '` and `' && typeof data.limit_tokens === '` came from —
    six of thirteen controls failed on artefacts like those before this existed.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            j, buf = i + 1, []
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == ch:
                    break
                if ch != "`" and text[j] == "\n":
                    break
                buf.append(text[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
        else:
            i += 1
    return out


def candidate_literals(path: Path) -> set[str]:
    """The literals of one file that could survive into the bundle.

    Comments, import specifiers and type declarations are removed first: all three are erased by
    the compiler, so probing for them says nothing about whether the module shipped.
    `api/accounting.ts` declares `label: 'Rate-limit allowance'` inside a type union — a string in
    the source that can never be in the output.
    """
    text = n11.COMMENT_RE.sub("", path.read_text(encoding="utf-8", errors="replace"))
    for rx in (STATIC_IMPORT_RE, REEXPORT_RE):
        text = rx.sub("\n", text)
    lines = text.splitlines()
    kept, depth, in_type = [], 0, False
    for line in lines:
        if not in_type and TYPE_DECL_RE.match(line):
            in_type, depth = True, 0
        if in_type:
            depth += line.count("{") + line.count("(") - line.count("}") - line.count(")")
            if depth <= 0 and not line.rstrip().endswith(("|", "=", ",")):
                in_type = False
            continue
        kept.append(line)
    out = set()
    for s in scan_strings("\n".join(kept)):
        if s.startswith(("@/", "./", "../")):
            continue
        for chunk in re.split(r"\$\{[^}]*\}", s):
            if any(c in chunk for c in "${}"):
                continue  # a nested template the splitter could not cut cleanly
            if len(chunk) >= 10 and re.search(r"[A-Za-z]{4}", chunk):
                out.add(chunk)
    return out


def distinctive_literals(files: list[Path]) -> dict[str, list[str]]:
    """Per file, the literals that occur nowhere else under src/ — as SUBSTRINGS, not as equals.

    Without uniqueness, `MessageCard.tsx` looks present in the bundle because
    `'shrink-0 flex items-center justify-center rounded-full'` is written elsewhere too. And
    uniqueness by string *equality* is not enough either: `'whitespace-pre-wrap'` is written once
    in `src/`, as a whole literal, but ships inside a longer class chain from another module, so
    `SharedStreamRenderer.tsx` read as contradicted when it is dead. Occurrence counting over the
    concatenated sources is what settles both.
    """
    texts = {rel(p): p.read_text(encoding="utf-8", errors="replace") for p in files}
    joined = "\n".join(texts.values())
    per = {rel(p): candidate_literals(p) for p in files}
    out = {}
    for name, lits in per.items():
        keep = [s for s in lits if joined.count(s) == texts[name].count(s)]
        out[name] = sorted(keep, key=lambda s: -len(s))[:6]
    return out


# ---------------------------------------------------------------- write-back ranking


def write_hooks() -> dict[str, str]:
    """Exported api/ hooks that wrap `useMutation` -> the write verb they issue."""
    verbs = {
        "postJson": "POST",
        "putJson": "PUT",
        "patchJson": "PATCH",
        "deleteJson": "DELETE",
    }
    out = {}
    for path in sorted((UI_SRC / "api").glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^export function (use\w+)", text, re.M):
            nxt = text.find("\nexport ", m.end())
            body = text[m.start() : nxt if nxt > 0 else len(text)]
            if "useMutation" not in body:
                continue
            found = [v for helper, v in verbs.items() if helper in body]
            if not found:
                found = [
                    mm.group(1).upper()
                    for mm in re.finditer(r"method:\s*'(\w+)'", body)
                    if mm.group(1).upper() != "GET"
                ]
            if found:
                out[m.group(1)] = "/".join(sorted(set(found)))
    return out


def balanced_call(text: str, start: int) -> str:
    """The argument list of the call whose `(` is at or after `start`."""
    i = text.index("(", start)
    depth = 0
    for j in range(i, len(text)):
        if text[j] in "([{":
            depth += 1
        elif text[j] in ")]}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return text[i:]


def bound_name(prefix: str) -> str | None:
    """What the call site called the query's payload: `data`, `data: alias`, or `const obj =`."""
    m = re.search(r"data\s*:\s*(\w+)", prefix)
    if m:
        return m.group(1)
    if re.search(r"\bdata\b", prefix):
        return "data"
    m = re.match(r"^\s*const\s+(\w+)\s*=\s*$", prefix)
    return m.group(1) if m else None


def seeds_state(text: str, name: str) -> str | None:
    """Does `name` seed component state that survives the render? Returns the seeding line."""
    for m in re.finditer(r"\buseEffect\s*\(", text):
        body = balanced_call(text, m.start())
        if re.search(rf"\b{re.escape(name)}\b", body) and re.search(r"\bset[A-Z]\w*\s*\(", body):
            return "useEffect@" + str(text.count("\n", 0, m.start()) + 1)
    for m in re.finditer(r"\buseState\s*(?:<[^>]*>)?\s*\(", text):
        body = balanced_call(text, m.start())
        if re.search(rf"\b{re.escape(name)}\b", body):
            return "useState@" + str(text.count("\n", 0, m.start()) + 1)
    return None


SETTER_RE = re.compile(r"\bset([A-Z]\w*)\s*\(")


def seeded_state_names(text: str, name: str) -> set[str]:
    """The state variables a `useEffect` naming `name` writes — `setContent` -> `content`."""
    out = set()
    for m in re.finditer(r"\buseEffect\s*\(", text):
        body = balanced_call(text, m.start())
        if not re.search(rf"\b{re.escape(name)}\b", body):
            continue
        for s in SETTER_RE.finditer(body):
            out.add(s.group(1)[0].lower() + s.group(1)[1:])
    return out


def guarded_by(text: str, names: set[str]) -> list[str]:
    """Early returns that fire while the data is absent, so the write cannot be reached.

    This is what separates F271 from F197. `AccountingPanel` and `ProjectSettingsPanel` seed state
    from a query and write it back, exactly as `InstructionsPage` does — but both open with
    `if (isLoading || !data)` / `if (!project || !form)` and return a skeleton, so a failed load
    renders no Save at all. `InstructionsPage` guards on `isLoading` alone, which is false once the
    query has failed, and hands the operator an enabled Save over an empty textarea.

    **Every** match is returned, not the first, because the first is often not the render guard:
    in `AccountingPanel` it is `if (!data) return null` inside the little `PreferredDisplay`
    helper, and in `ProjectSettingsPanel` it is `if (!settings) return` inside the seeding effect.
    Both files really are guarded — `AccountingPanel.tsx:33` and `ProjectSettingsPanel.tsx:75`,
    read by hand — but a script that printed only its first hit would have said so for the wrong
    reason, which is the failure this repository keeps finding in its own arguments.
    """
    out = []
    for m in re.finditer(r"\bif\s*\(", text):
        cond = balanced_call(text, m.start())
        if not any(re.search(rf"!\s*{re.escape(n)}\b", cond) for n in names):
            continue
        tail = text[m.start() + len(cond) : m.start() + len(cond) + 800]
        if re.search(r"^\s*\{?\s*return\b", tail) or "return" in tail[:400]:
            out.append(f"if{cond.strip()} @{text.count(chr(10), 0, m.start()) + 1}")
    return out


def rank_sites(sites, reachable_rel, writers):
    ranked = []
    for s in sites:
        path = REPO / s["file"]
        text = path.read_text(encoding="utf-8")
        prefix = n11.statement_prefix(
            text, sum(len(x) + 1 for x in text.split("\n")[: s["line"] - 1])
        )
        pos = text.find(s["hook"] + "(", sum(len(x) + 1 for x in text.split("\n")[: s["line"] - 1]))
        if pos > 0:
            prefix = n11.statement_prefix(text, pos)
        name = bound_name(prefix)
        seed = seeds_state(text, name) if name else None
        writes = sorted({h: v for h, v in writers.items() if re.search(rf"\b{h}\b", text)}.items())
        guard = None
        if seed and writes:
            guard = guarded_by(text, {name} | seeded_state_names(text, name))
            rank = "1G" if guard else 1
        elif writes:
            rank = 2
        else:
            rank = 3
        ranked.append(
            {**s, "bound": name, "seed": seed, "writes": writes, "rank": rank, "guard": guard}
        )
    return ranked


def main() -> int:
    root_main = UI_SRC / "main.tsx"
    root_app = UI_SRC / "App.tsx"
    all_files = all_source_files()

    runtime, unresolved = walk(root_main, follow_type_only=False)
    with_types, _ = walk(root_main, follow_type_only=True)
    from_app, _ = walk(root_app, follow_type_only=False)

    print("=== 1. the walk ===")
    print(f"source files under hub/ui/src (tests excluded)   {len(all_files)}")
    print(f"reachable from main.tsx, runtime imports only    {len(runtime)}")
    print(f"reachable from main.tsx, type-only edges too     {len(with_types)}")
    print(f"reachable from App.tsx alone                     {len(from_app)}")
    print(f"UNREACHABLE from main.tsx                        {len(all_files) - len(runtime)}")
    if unresolved:
        print(f"  UNRESOLVED specifiers ({len(unresolved)}) — the walk is only as good as these:")
        for where, spec in sorted(set(unresolved)):
            print(f"    {where}  ->  {spec}")
    else:
        print("  UNRESOLVED specifiers: none")
    extra_types = sorted(rel(p) for p in with_types - runtime)
    if extra_types:
        print(f"  reached ONLY by a type-only import ({len(extra_types)}): {extra_types}")
    only_main = sorted(rel(p) for p in runtime - from_app)
    print(f"  reached from main.tsx but not from App.tsx: {only_main}")

    dead = sorted(set(all_files) - runtime)
    print(f"\n=== 2. the {len(dead)} unreachable files, checked against the shipped bundle ===")
    bundle_file = sorted(BUNDLE_DIR.glob("index-*.js"))[0]
    bundle = bundle_file.read_text(encoding="utf-8", errors="replace")
    print(f"bundle: {rel(bundle_file)}")
    # A dozen reachable files spread across the tree, not a hand-picked few: the probe rule is
    # only trustworthy if it survives files it was not tuned on.
    live_sorted = sorted(runtime)
    step = max(1, len(live_sorted) // 12)
    controls = live_sorted[::step]
    lit_index = distinctive_literals(all_files)
    bad_controls: list[tuple] = []
    no_literal_controls: list[str] = []
    for p in controls:
        lits = lit_index[rel(p)]
        if not lits:
            no_literal_controls.append(rel(p))
            continue
        present = sum(1 for lit in lits if bundle.count(lit) > 0)
        if present < len(lits):
            bad_controls.append(
                (rel(p), present, len(lits), [x for x in lits if bundle.count(x) == 0][:2])
            )
    print(
        f"controls (reachable files, EVERY distinctive literal expected present): "
        f"{len(controls) - len(bad_controls) - len(no_literal_controls)}/"
        f"{len(controls) - len(no_literal_controls)} ok"
    )
    for row in bad_controls:
        print(f"  CONTROL FAILED {row}")
    if no_literal_controls:
        print(f"  controls with no distinctive literal (undecidable): {no_literal_controls}")
    confirmed, contradicted, unprobeable = [], [], []
    for p in dead:
        lits = lit_index[rel(p)]
        if not lits:
            unprobeable.append(rel(p))
            continue
        present = [lit for lit in lits if bundle.count(lit) > 0]
        if not present:
            confirmed.append((rel(p), len(lits), len(lits)))
        else:
            contradicted.append((rel(p), present))
    print(f"  every distinctive literal absent (confirmed):  {len(confirmed)}")
    print(f"  some literal present (walk contradicted):      {len(contradicted)}")
    for row in contradicted:
        print(f"    {row[0]}  all of {row[1]}")
    print(f"  no probeable literal (undecided):              {len(unprobeable)} {unprobeable}")
    if "--files" in sys.argv:
        for name, absent, total in confirmed:
            print(f"    dead: {name}  ({absent}/{total} distinctive literals absent)")

    reachable_rel = {rel(p) for p in runtime}

    print("\n=== 3. N-10 re-counted over reachable files only ===")
    src_all = n10.ui_sources()
    src_live = {
        k: v
        for k, v in src_all.items()
        if Path(k).resolve().relative_to(REPO).as_posix() in reachable_rel
    }
    routes = n10.declared_routes()
    operator = [r for r in routes if not r[1].startswith("/api/v1/agent-actions")]

    def reached(calls):
        hit = set()
        for method, path in operator:
            for (verb, url), _ in calls.items():
                if verb != "?" and verb != method:
                    continue
                if n10.match(path, url) == "exact":
                    hit.add((method, path))
                    break
            if (method, path) in n10.HELPER_CALLED or n10.HAND_RESOLVED.get((method, path)):
                hit.add((method, path))
        return hit

    hit_all, hit_live = reached(n10.ui_calls(src_all)), reached(n10.ui_calls(src_live))
    print(f"operator route+method pairs                  {len(operator)}")
    print(f"  reached, depth-1 (N-10's 110)              {len(hit_all)}")
    print(f"  reached from a file the app loads          {len(hit_live)}")
    lost = sorted(hit_all - hit_live)
    print(f"  reached only from dead code                {len(lost)}")
    for method, path in lost:
        print(f"    {method:6} {path}")
    print(
        f"  no client anywhere, corrected total        {len(operator) - len(hit_live)} "
        f"(N-10 reported 35 with no client + 10 CLI-only)"
    )

    print("\n=== 4. N-11 re-counted over reachable files only ===")
    decls = n11.declarations()
    hooks = sorted({d["hook"] for d in decls if d["hook"]})
    decl_files = {d["file"] for d in decls}
    sites = [s for s in n11.call_sites(hooks, decl_files) if s["file"] not in decl_files]
    live = [s for s in sites if s["file"] in reachable_rel]
    dead_sites = [s for s in sites if s["file"] not in reachable_rel]
    unhandled_all = [s for s in sites if not (s["binds_error"] and s["error_used"])]
    unhandled_live = [s for s in live if not (s["binds_error"] and s["error_used"])]
    print(f"call sites outside api/, depth-1 (N-11's 107)      {len(sites)}")
    print(f"  in a file the app loads                          {len(live)}")
    print(f"  in dead code                                     {len(dead_sites)}")
    for s in sorted(dead_sites, key=lambda s: (s["file"], s["line"])):
        print(f"    {s['file']}:{s['line']}  {s['hook']}")
    print(f"unhandled sites, depth-1 (N-11's 101)              {len(unhandled_all)}")
    print(f"unhandled sites the app can actually reach         {len(unhandled_live)}")

    buckets = {}
    for s in unhandled_live:
        cls = n11.RENDERS.get((s["file"], s["line"]), ("UNCLASSIFIED", "", ""))[0]
        buckets.setdefault(cls, []).append(s)
    for cls in ("MISREPORT", "SUPPRESSED", "BLANK", "NAMED", "UNCLASSIFIED"):
        print(f"  {cls:14s} {len(buckets.get(cls, [])):3d}")

    print("\n=== 5. the ranking: which failed loads can be written back ===")
    writers = write_hooks()
    print(f"api/ hooks wrapping useMutation with a write verb: {len(writers)}")
    ranked = rank_sites(buckets.get("MISREPORT", []), reachable_rel, writers)
    for rank, label in (
        (1, "seeds state, writes it back, NO guard — F271's shape"),
        ("1G", "same, but an early return hides the write — F197's terminal skeleton"),
        (2, "the file writes, no state seeding      — an empty control, not an overwrite"),
        (3, "no write in the file                   — read-only misreport"),
    ):
        rows = [r for r in ranked if r["rank"] == rank]
        print(f"\n  RANK {rank}  {len(rows):3d}  {label}")
        for r in sorted(rows, key=lambda r: (r["file"], r["line"])):
            short = r["file"].replace("hub/ui/src/", "")
            if rank in (1, "1G"):
                w = ",".join(h for h, _ in r["writes"][:3])
                print(
                    f"    {short}:{r['line']:<5} {r['hook']:24} bound={r['bound']:16} "
                    f"{r['seed']:14} writes={w}"
                )
                for g in r["guard"] or []:
                    print(f"        guard: {g}")
            elif rank == 2:
                print(f"    {short}:{r['line']:<5} {r['hook']}")
            else:
                print(f"    {short}:{r['line']:<5} {r['hook']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
