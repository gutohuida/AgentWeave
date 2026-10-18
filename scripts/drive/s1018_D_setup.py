"""Sweep D setup: subject matter, a Haiku runner, agent alpha, vault inputs (PDF/PNG/long text)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from s1018_D_common import SCRATCH, save, say, sc  # noqa: E402

PID = sys.argv[1]
ROOT = pathlib.Path(sys.argv[2])
base = f"/projects/{PID}"

# --- subject matter: a tiny library with a test suite and a seeded defect
(ROOT / "ratelimit").mkdir(exist_ok=True)
(ROOT / "ratelimit" / "__init__.py").write_text(
    '"""Token bucket rate limiter."""\n\n\n'
    "class Bucket:\n"
    "    def __init__(self, per_minute):\n"
    "        self.per_minute = per_minute\n"
    "        self.used = 0\n\n"
    "    def take(self):\n"
    "        # seeded defect: allows one request too many\n"
    "        if self.used > self.per_minute:\n"
    "            return False\n"
    "        self.used += 1\n"
    "        return True\n",
    encoding="utf-8",
)
(ROOT / "tests").mkdir(exist_ok=True)
(ROOT / "tests" / "test_bucket.py").write_text(
    "from ratelimit import Bucket\n\n\n"
    "def test_limit():\n"
    "    b = Bucket(2)\n"
    "    assert [b.take() for _ in range(3)] == [True, True, False]\n",
    encoding="utf-8",
)
(ROOT / "NOTES-café.md").write_text("Non-ASCII: naïve façade — 東京\n", encoding="utf-8")
sc.git(ROOT, "add", "-A")
sc.git(ROOT, "commit", "-q", "-m", "ratelimit library with a seeded defect")

code, runner = sc.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": sc.HAIKU})
say("runner", (code, runner))
code, agent = sc.api("POST", f"{base}/agents", {"name": "alpha", "runner_id": runner["id"]})
say("agent alpha", (code, str(agent)[:300]))
code, agent2 = sc.api("POST", f"{base}/agents", {"name": "beta", "runner_id": runner["id"]})
say("agent beta", (code, str(agent2)[:300]))
save({"pid": PID, "root": str(ROOT), "base": base, "runner": runner["id"]})

# --- vault inputs
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

pdf = canvas.Canvas(str(SCRATCH / "backoff.pdf"), pagesize=A4)
for first, second in (
    ("Platform client guide - retries, 2026-03-01", "Page 1 of 2. Applies to all API clients."),
    ("Retry backoff starts at 2 seconds and doubles to 64.", "Page 2 of 2."),
):
    pdf.setFont("Helvetica", 18)
    pdf.drawString(72, 760, first)
    pdf.drawString(72, 730, second)
    pdf.showPage()
pdf.save()

image = Image.new("RGB", (900, 260), "white")
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=40)
draw.text((30, 12), "Gateway settings", fill="black", font=font)
draw.text((30, 140), "Max upload size: 25 MB", fill="black", font=font)
image.save(SCRATCH / "gateway.png")

FILLER = (
    "This document records background context for the platform team. It covers the history of the "
    "gateway, who owns which dashboards, the naming of environments, and a long digression about "
    "how the staging cluster was migrated twice in one quarter because of disk pressure. None of "
    "this paragraph is a decision; it is here so that the decision below sits past the opening. "
)
(SCRATCH / "rl_old.txt").write_text(
    "Ops runbook, rate limits, February review.\n" + FILLER + "\n"
    "Decision: the public API rate limit is 100 requests per minute per key.\n", encoding="utf-8")
(SCRATCH / "rl_new.txt").write_text(
    "Platform review, rate limits, June.\n" + FILLER + "\n"
    "Decision: the public API rate limit is 250 requests per minute per key.\n", encoding="utf-8")
long_text = "On-call handbook.\n" + (FILLER * 150) + "\nThe on-call escalation code word is HERON.\n"
(SCRATCH / "oncall_long.txt").write_text(long_text, encoding="utf-8")
print("long chars", len(long_text))
big = SCRATCH / "big.pdf"
data = (SCRATCH / "backoff.pdf").read_bytes()
big.write_bytes(data + b"%" + b"0" * (10 * 1_048_576 + 1 - len(data) - 1))
exact = SCRATCH / "exact.pdf"
exact.write_bytes(data + b"%" + b"0" * (10 * 1_048_576 - len(data) - 1))
(SCRATCH / "fake.pdf").write_bytes(b"this is not a pdf at all")
(SCRATCH / "note.gif").write_bytes(b"GIF89a" + b"\0" * 20)
print("sizes", big.stat().st_size, exact.stat().st_size)
