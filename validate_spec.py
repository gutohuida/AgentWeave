"""Validator for spec/agentweave-1.0-spec.html (rev. 5).

Checks:
1. Tag balance (html.parser), no unclosed tags at EOF
2. Every href="#..." resolves to a real id
3. No duplicate ids
4. FR traceability: FR-IDs defined in body == FR-IDs in the §14 index
5. RFC keyword/class mismatches (class says must-not but text says must, or inverse)
6. Section numbering: h2 sequence 0..17
7. Counts: task IDs, Q rows
"""

import io
import re
import sys
from html.parser import HTMLParser

PATH = "spec/agentweave-1.0-spec.html"
VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}

src = io.open(PATH, encoding="utf-8").read()
errors = []


class Chk(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.ids = {}
        self.hrefs = []
        self.h2nums = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d:
            self.ids.setdefault(d["id"], 0)
            self.ids[d["id"]] += 1
        if tag == "a" and d.get("href", "").startswith("#"):
            self.hrefs.append(d["href"][1:])
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            errors.append("end tag </%s> with empty stack at %s" % (tag, self.getpos()))
            return
        open_tag, pos = self.stack.pop()
        if open_tag != tag:
            errors.append("mismatch: <%s> opened at %s closed by </%s> at %s" % (open_tag, pos, tag, self.getpos()))


c = Chk()
c.feed(src)
c.close()

if c.stack:
    errors.append("unclosed tags at EOF: %s" % [t for t, _ in c.stack])

dup = [i for i, n in c.ids.items() if n > 1]
if dup:
    errors.append("duplicate ids: %s" % dup)

missing = sorted(set(h for h in c.hrefs if h and h not in c.ids))
if missing:
    errors.append("broken anchors: %s" % missing)

# h2 numbering
h2nums = [int(m.group(1)) for m in re.finditer(r'<h2><span class="sec-num">(\d+)\.</span>', src)]
if h2nums != list(range(0, 18)):
    errors.append("h2 sequence wrong: %s" % h2nums)

# FR traceability: body = whole doc minus the §14 index table
idx_start = src.index('id="requirements-index"')
idx_end = src.index("</table>", idx_start)
idx_text = src[idx_start:idx_end]
body_text = src[:idx_start] + src[idx_end:]
body_defined = sorted(set(re.findall(r'<span class="req-id">(FR-[A-Z]+-\d+)</span>', body_text)) - {"FR-XXX-000"})
indexed = sorted(set(re.findall(r'<span class="req-id">(FR-[A-Z]+-\d+)</span>', idx_text)))
if body_defined != indexed:
    errors.append("FR mismatch: only-in-body=%s only-in-index=%s"
                  % (sorted(set(body_defined) - set(indexed)), sorted(set(indexed) - set(body_defined))))

# RFC keyword/class mismatch
rfc_bad = []
for m in re.finditer(r'<span class="rfc (must not|must|should|should not|may)">(.*?)</span>', src):
    cls, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
    if cls == "must not" and text.lower() == "must":
        rfc_bad.append(("class must not / text must", src[:m.start()].count("\n") + 1))
    if cls == "must" and text.lower() == "must not":
        rfc_bad.append(("class must / text must not", src[:m.start()].count("\n") + 1))
# exclude the RFC-2119 legend in §0.2 (first ~400 lines)
rfc_bad = [b for b in rfc_bad if b[1] > 400]
if rfc_bad:
    errors.append("RFC class/text mismatches: %s" % rfc_bad)

# counts
tasks = sorted(set(re.findall(r"\bT-\d{3}\b", src)))
qrows = len(re.findall(r"<tr><td>Q-\d+</td>", src))
knobs = len(re.findall(r"<tr><td><code>[a-z_]+</code></td><td>(?:float|int|bool|list|string|enum|object)", src))

if errors:
    print("FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print("OK")
print("  tags balanced, 0 unclosed; anchors resolve; ids unique")
print("  FRs: body=%d index=%d (match)" % (len(body_defined), len(indexed)))
print("  h2 sections: %s" % h2nums)
print("  tasks: %d unique (%s..%s); Q rows: %d; knob-like rows: %d" % (len(tasks), tasks[0], tasks[-1], qrows, knobs))
