"""Acceptance drive for the knowledge vault roadmap's `images-and-pdfs` slice, 2026-10-12.

The slice's `drive` criterion (spec/changes/images-and-pdfs-are-vault-sources-too/). It starts its
own Hub on a free port in 8110-8139 with a fresh database (never :8000 or :8010), serving the
bundle built into hub/hub/static/ui. It opens a scratch git repository as the project, with a
Haiku Claude runner and vault distillation enabled, generates a two-page PDF (reportlab) and a PNG
screenshot (PIL), and checks, in order:

  1. POST /vault/files takes the PDF as the raw body and answers 201 with media_type
     application/pdf;
  2. the same for the PNG, with image/png;
  3. the map lists each with its media_type;
  4. GET /vault/sources/{id}/file answers each file's bytes, unchanged, with its media type;
  5. within three minutes the PDF has a transcription (GET /vault/entries/{id}) holding 450, and a
     fact naming 450 whose every citation quote is found in that transcription;
  6. the same for the PNG, with 75;
  7. in Chromium, selecting the PDF in the Vault tab shows an embedded viewer
     ([data-testid=vault-file-pdf], an iframe, object or embed whose source is a blob: URL) above
     its transcription (shot_pdf.png);
  8. selecting the PNG shows [data-testid=vault-file-image], an img from a blob: URL with a
     natural width above zero (shot_image.png).

It fails on today's Hub at check 1 (POST /vault/files answers 404). It stops at the first failure,
so a red run spends no model call. Run from anywhere:

    py -3.11 scripts/drive/d1026_images_pdfs.py
"""

import json
import os
import pathlib
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1026-images-pdfs" / STAMP
DB = TMP / "hub.db"
HAIKU = "claude-haiku-4-5-20251001"
JOB = "vault-distillation"
DISTIL_WAIT = 3 * 60
PDF_PAGES = (
    ("Acme Retail - customer policy, 2026", "Page 1 of 2. Returns are handled in store."),
    ("Refunds up to 450 euros need no manager approval.", "Page 2 of 2."),
)
PNG_LINES = ("Shop settings", "Free shipping threshold: 75 euros")
results = []


def free_port():
    for port in range(8110, 8140):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit("no free port in 8110-8139")


PORT = free_port()
HUB = f"http://127.0.0.1:{PORT}"


class Stop(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=True):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def call(method, path, data=None, content_type="application/json", timeout=60):
    """(status, headers, raw bytes) for one request; status 0 when the Hub cannot be reached."""
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": content_type}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except urllib.error.URLError as exc:
        return 0, {}, str(exc).encode()


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    code, _, raw = call(method, path, data, timeout=timeout)
    try:
        return code, json.loads(raw or b"null")
    except ValueError:
        return code, raw.decode(errors="replace")[:2000]


def upload(base, data, media_type, name):
    query = urllib.parse.urlencode({"name": name, "type": "document"})
    code, _, raw = call("POST", f"{base}/vault/files?{query}", data, content_type=media_type)
    try:
        return code, json.loads(raw or b"null")
    except ValueError:
        return code, raw.decode(errors="replace")[:500]


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render or a file mid-write
            pass
        time.sleep(every)
    return False


def start_hub():
    TMP.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 90):
        proc.kill()
        sys.exit(f"hub did not come up; see {TMP / 'hub.log'}")
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def main():
    proc = start_hub()
    try:
        drive()
    except Stop:
        pass
    finally:
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP}, port {PORT})")
    sys.exit(1 if bad else 0)


def make_pdf(path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=A4)
    for first, second in PDF_PAGES:
        pdf.setFont("Helvetica", 18)
        pdf.drawString(72, 760, first)
        pdf.drawString(72, 730, second)
        pdf.showPage()
    pdf.save()
    return path.read_bytes()


def make_png(path):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 260), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    draw.rectangle([0, 0, 900, 70], fill=(230, 236, 245))
    draw.text((30, 12), PNG_LINES[0], fill="black", font=font)
    draw.text((30, 140), PNG_LINES[1], fill="black", font=font)
    image.save(path)
    return path.read_bytes()


def facts_in(folder, source_id):
    """The fact records under *folder* that cite *source_id*."""
    found = []
    for path in sorted(folder.glob("fct-*.json")) if folder.is_dir() else []:
        record = json.loads(path.read_text(encoding="utf-8"))
        if source_id in [c.get("source") for c in record.get("citations") or []]:
            found.append(record)
    return found


def squash(text):
    return re.sub(r"\s+", " ", text or "").strip()


def transcription(base, source_id):
    code, entry = api("GET", f"{base}/vault/entries/{source_id}")
    return entry.get("content") if code == 200 and isinstance(entry, dict) else None


def cited_fact(base, folder, source_id, number):
    """A fact naming *number* whose every citation quote is in the source's transcription."""
    text = transcription(base, source_id)
    if not text or number not in text:
        return None
    for fact in facts_in(folder, source_id):
        quotes = [c.get("quote", "") for c in fact.get("citations") or [] if c.get("source") == source_id]
        if number in fact.get("claim", "") and quotes and all(
            q and squash(q) in squash(text) for q in quotes
        ):
            return fact
    return None


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the images-and-pdfs drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    facts_dir = root / "knowledge" / "facts"
    pdf_bytes = make_pdf(TMP / "policy.pdf")
    png_bytes = make_png(TMP / "screenshot.png")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "filesdrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, job = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": haiku["id"]})
    assert code == 200 and job.get("enabled") is True, (code, job)

    # 1 and 2: the uploads.
    code, pdf = upload(base, pdf_bytes, "application/pdf", "Customer policy")
    pdf_id = pdf.get("id") if isinstance(pdf, dict) else None
    check("1 POST /vault/files takes the PDF and answers 201 with media_type application/pdf",
          code == 201 and pdf_id and pdf.get("media_type") == "application/pdf", f"{code} {str(pdf)[:300]}")
    code, png = upload(base, png_bytes, "image/png", "Shop settings screenshot")
    png_id = png.get("id") if isinstance(png, dict) else None
    check("2 POST /vault/files takes the PNG and answers 201 with media_type image/png",
          code == 201 and png_id and png.get("media_type") == "image/png", f"{code} {str(png)[:300]}")

    # 3: the map.
    code, vault_map = api("GET", f"{base}/vault/map")
    listed = {e.get("id"): e for e in (vault_map.get("entries", []) if isinstance(vault_map, dict) else [])}
    check("3 the map lists each file source with its media_type",
          code == 200 and listed.get(pdf_id, {}).get("media_type") == "application/pdf"
          and listed.get(png_id, {}).get("media_type") == "image/png",
          f"{code} {[(i, e.get('kind'), e.get('media_type')) for i, e in listed.items()]}")

    # 4: the file route.
    served = {}
    for sid, raw, media in ((pdf_id, pdf_bytes, "application/pdf"), (png_id, png_bytes, "image/png")):
        code, headers, body = call("GET", f"{base}/vault/sources/{sid}/file")
        kind = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
        served[sid] = (code, kind, len(body), body == raw)
    check("4 GET /vault/sources/{id}/file answers each file's bytes with its media type",
          all(code == 200 and same and kind.startswith(media) for (code, kind, _, same), media
              in zip(served.values(), ("application/pdf", "image/png"))), str(served))

    # 5 and 6: transcribed, then distilled into cited facts.
    for number, sid, label in (("450", pdf_id, "5 the PDF"), ("75", png_id, "6 the PNG")):
        got = poll(lambda: cited_fact(base, facts_dir, sid, number) is not None, DISTIL_WAIT, every=3)
        text = transcription(base, sid)
        facts = facts_in(facts_dir, sid)
        (TMP / f"{sid}_transcription.txt").write_text(text or "", encoding="utf-8")
        (TMP / f"{sid}_facts.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
        check(f"{label} is transcribed and yields a fact naming {number} quoting its transcription",
              got, f"text={str(text)[:300]!r} facts={[(f.get('claim'), [c.get('quote') for c in f.get('citations', [])]) for f in facts]}")

    # 7 and 8: the Vault tab.
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=vault", wait_until="domcontentloaded")

        listed = poll(lambda: page.locator(f"[data-testid=vault-entry-{pdf_id}]").count() == 1, 20)
        viewer = False
        if listed:
            page.locator(f"[data-testid=vault-entry-{pdf_id}]").click()
            viewer = poll(lambda: page.evaluate(
                """() => {
                  const root = document.querySelector('[data-testid=vault-file-pdf]');
                  if (!root) return false;
                  const el = root.matches('iframe,object,embed') ? root : root.querySelector('iframe,object,embed');
                  const src = el && (el.getAttribute('src') || el.getAttribute('data') || '');
                  const text = document.querySelector('[data-testid=vault-entry-text]');
                  return src.startsWith('blob:') && !!text && text.innerText.includes('450');
                }"""), 20)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(TMP / "shot_pdf.png"), full_page=True)
        check("7 the Vault tab shows the PDF in an embedded viewer from a blob URL above its transcription",
              viewer, f"listed={listed} viewer={viewer}", fatal=False)

        picked = poll(lambda: page.locator(f"[data-testid=vault-entry-{png_id}]").count() == 1, 10)
        drawn = False
        if picked:
            page.locator(f"[data-testid=vault-entry-{png_id}]").click()
            drawn = poll(lambda: page.evaluate(
                """() => {
                  const img = document.querySelector('[data-testid=vault-file-image]');
                  return !!img && (img.getAttribute('src') || '').startsWith('blob:')
                    && img.complete && img.naturalWidth > 0;
                }"""), 20)
        page.screenshot(path=str(TMP / "shot_image.png"), full_page=True)
        browser.close()
    check("8 the Vault tab shows the PNG as an image from a blob URL with a natural width above zero",
          drawn, f"listed={picked} drawn={drawn}")


if __name__ == "__main__":
    main()
