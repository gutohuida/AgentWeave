"""Machine-check a review page's own claims: self-contained, well-formed, no stray CR.

    py -3.11 scripts/drive/check_review_page.py [path]

Written on 2026-09-01 during row 13, after the same set of checks had been re-typed by hand for
every edit to that day's page and one of them (a Windows path whose `\r` collapsed into a real
line break) had already slipped through once. The review page is handed to the operator and must
render from a file:// URL with no network, so "no external references" is a contract, not a style
preference.

The finding-id check is scoped to section 3's table on purpose. `class="fid"` is also used for
cross-references in later sections, and counting those as duplicate rows was this script being
wrong rather than the page.
"""
import io
import re
from html.parser import HTMLParser

import sys

P = sys.argv[1] if len(sys.argv) > 1 else "spec-queue/review/review-2026-09-01.html"
s = io.open(P, encoding="utf-8", newline="").read()
fail = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fail.append(label)


check("no stray CR anywhere in the file", "\r" not in s, repr(s[max(0, s.find("\r") - 40):s.find("\r") + 40]))
check("full document wrapper", all(t in s for t in ("<!DOCTYPE", "<html", "<head", "<body", "</html>")))
check("bare :root", ":root" in s)
check("dark scheme", "prefers-color-scheme: dark" in s)
check("body background", re.search(r"body\s*\{[^}]*background:\s*var\(--bg\)", s) is not None)

external = []
for pattern, what in (
    (r"<link[^>]+href=", "link"),
    (r"<script[^>]+src=", "script src"),
    (r"@import", "@import"),
    (r'src="https?://', "http src"),
    (r"url\(https?://", "remote url()"),
    (r"fonts\.googleapis|fonts\.gstatic", "webfont"),
):
    external += [f"{what}: {m.group(0)}" for m in re.finditer(pattern, s)]
check("zero external references", not external, str(external)[:300])

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}


class Walk(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.problems.append(f"</{tag}> with nothing open")
        elif self.stack[-1] != tag:
            self.problems.append(f"</{tag}> closes <{self.stack[-1]}>")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


w = Walk()
w.feed(s)
check("tag-balance walk clean", not w.problems, str(w.problems)[:300])
check("nothing left unclosed", not w.stack, str(w.stack)[:200])

# Scoped to section 3's table. `class="fid"` is also used for cross-references in sections 4
# and 5 (F173, F188, F190 ...), and counting those as duplicate ROWS was this check being
# wrong, not the page.
section3 = s[s.index("What today's drive found"):s.index("What was specced")]
ids = re.findall(r'class="fid">(F\d+)<', section3)
check("every finding row carries an id", len(ids) == len(set(ids)), f"duplicates in {ids}")
print(f"  ..   findings on the page: {len(ids)} -> {ids}")

total = re.search(r"Running total: <strong>(\d+) findings", s)
print(f"  ..   running total stated: {total.group(1) if total else '<none>'}")
print(f"  ..   bytes: {len(s.encode('utf-8'))}")
print("\nFAILED" if fail else "\nALL CHECKS PASSED")
