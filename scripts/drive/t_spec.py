"""T-SPEC: drive the whole specification flow as the operator."""

from aw import api, show

P = "proj-18e5d4e0"
DOC = "spec/changes/indigo-wyvern/spec.html"

payload = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "Correct money parsing, empty entries and account ordering",
    "summary": (
        "The ledger library has three defects that make its output untrustworthy: decimal "
        "parsing loses a factor of ten on single-digit fractions, an entry with no postings "
        "reports itself balanced, and the account report's ordering is not stable between runs."
    ),
    "problem": (
        "A ledger whose totals depend on how a string was written, and whose reports cannot be "
        "diffed between runs, cannot be reconciled against a bank statement. All three defects "
        "are silent: nothing raises, the numbers are simply wrong."
    ),
    "scope": {
        "in_scope": [
            "Money.parse decimal handling",
            "Entry.balances for the empty-postings case",
            "Book.accounts iteration order",
        ],
        "non_goals": [
            "Multi-currency conversion",
            "Persistence or file formats",
            "Any change to the public API's shape",
        ],
    },
    "requirements": [
        {
            "key": "fr-parse",
            "statement": (
                "Money.parse MUST interpret the fractional part positionally: '1.5' is 150 minor "
                "units and '1.05' is 105, and a fractional part longer than two digits is refused."
            ),
            "modal": "MUST",
            "rationale": "Reading '1.5' as 15 cents understates by a factor of ten, silently.",
        },
        {
            "key": "fr-balance",
            "statement": "An Entry with no postings MUST NOT report itself as balanced.",
            "modal": "MUST",
            "rationale": "An empty entry carries no information and posting one corrupts the journal.",
        },
        {
            "key": "fr-order",
            "statement": "Book.accounts MUST return accounts in a stable, sorted order.",
            "modal": "MUST",
            "rationale": "A report that cannot be diffed between runs cannot be reviewed.",
        },
    ],
    "acceptance_criteria": [
        {
            "key": "ac-parse-single",
            "requirement": "fr-parse",
            "given": "a fresh Money class",
            "when": "Money.parse('1.5') is called",
            "then": "the result's minor value is 150",
        },
        {
            "key": "ac-parse-long",
            "requirement": "fr-parse",
            "given": "a fresh Money class",
            "when": "Money.parse('1.234') is called",
            "then": "a ValueError is raised naming the fractional part",
        },
        {
            "key": "ac-balance-empty",
            "requirement": "fr-balance",
            "given": "an Entry with an empty postings list",
            "when": "balances() is called",
            "then": "it returns False, and Book.post raises ValueError",
        },
        {
            "key": "ac-order-stable",
            "requirement": "fr-order",
            "given": "a book with postings to three accounts",
            "when": "accounts() is called twice",
            "then": "both calls return the same key order, sorted ascending",
        },
    ],
    "tasks": [
        {
            "key": "t-parse",
            "title": "Fix decimal parsing",
            "description": (
                "Rewrite Money.parse so the fractional part is read positionally. Pad a "
                "single-digit fraction, refuse more than two digits with a ValueError. Add tests "
                "covering ac-parse-single and ac-parse-long."
            ),
            "requirements": ["fr-parse"],
            "reviewer": "critic",
        },
        {
            "key": "t-balance",
            "title": "Refuse the empty entry",
            "description": (
                "Entry.balances() must return False when postings is empty. Add a test covering "
                "ac-balance-empty, including that Book.post raises."
            ),
            "requirements": ["fr-balance"],
            "reviewer": "critic",
        },
        {
            "key": "t-order",
            "title": "Make account ordering stable",
            "description": (
                "Book.accounts() must return a mapping in sorted key order. Add a test covering "
                "ac-order-stable."
            ),
            "requirements": ["fr-order"],
            "depends_on": ["t-balance"],
            "reviewer": "critic",
        },
        {
            "key": "t-report",
            "title": "Add a trial-balance report",
            "description": (
                "Add Book.trial_balance() returning a formatted, stable, sorted report string. "
                "It depends on both corrected parsing and stable ordering."
            ),
            "requirements": ["fr-order", "fr-parse"],
            "depends_on": ["t-parse", "t-order"],
            "reviewer": "critic",
        },
    ],
    "design": (
        "All three fixes are local to their own function. Money.parse gains a two-branch pad/"
        "refuse on the fractional string. Entry.balances gains an explicit empty check rather "
        "than relying on sum([]) == 0. Book.accounts sorts its collected names before building "
        "the mapping. trial_balance is new and built on top of the other two."
    ),
    "evidence": {
        "checked": [
            "tests/test_ledger.py — seven passing tests, none of which cover any of the three defects",
        ],
        "limits": [
            "No test covers a fractional part longer than two digits",
            "No test constructs an Entry with empty postings",
        ],
    },
    "lifecycle": "One-off change. Reconciled back into the library's README once implemented.",
    "open_questions": [],
}

c, b = api("PUT", f"/projects/{P}/project/documents/{DOC}/content", {"document": payload})
show("write document content", c, b, 1400)
