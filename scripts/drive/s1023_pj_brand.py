"""Projects sweep 2026-10-23 -- the brand identity (e23cbc6) in real Chromium against the served
bundle: the rail's loop mark (BrandLoop) in light and dark, at the minimum rail width, compact,
and in a narrow window; and the favicon (link, fetch, type, content).

    py -3.11 scripts/drive/s1023_pj_brand.py
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s1023_pj_lib import PA, hub_and_key  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB, KEY = hub_and_key()

MARK_JS = """() => {
  const m = document.querySelector('[data-testid=rail-brand-loop]');
  if (!m) return null;
  const r = m.getBoundingClientRect();
  const cs = getComputedStyle(m);
  const g = m.querySelector('g');
  const stroke = g ? getComputedStyle(g).stroke : null;
  const head = m.closest('.aw-rail-head');
  const hr = head ? head.getBoundingClientRect() : null;
  const name = document.querySelector('.aw-wordmark-name');
  const nr = name ? name.getBoundingClientRect() : null;
  const bg = head ? getComputedStyle(head).backgroundColor : null;
  const rail = document.querySelector('[data-testid=sidebar]');
  const railBg = rail ? getComputedStyle(rail).backgroundColor : null;
  const maskId = (m.querySelector('mask') || {}).id;
  const dupIds = maskId ? document.querySelectorAll('[id="' + maskId + '"]').length : 0;
  return {rect: [r.x, r.y, r.width, r.height], display: cs.display, visibility: cs.visibility,
          ariaHidden: m.getAttribute('aria-hidden'), stroke, madder: getComputedStyle(document.documentElement).getPropertyValue('--brand-madder').trim(),
          head: hr && [hr.x, hr.y, hr.width, hr.height], name: nr && [nr.x, nr.width, nr.right],
          nameText: name && name.textContent, nameOverflow: name && (name.scrollWidth > name.clientWidth),
          railBg, headBg: bg, maskId, dupIds, mode: document.documentElement.dataset.mode};
}"""


def contrast(c1, c2):
    def lum(rgb):
        out = []
        for v in rgb:
            v = v / 255
            out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

    a, b = lum(c1), lum(c2)
    hi, lo = max(a, b), min(a, b)
    return round((hi + 0.05) / (lo + 0.05), 2)


def parse_rgb(s):
    if not s or not s.startswith("rgb"):
        return None
    nums = s[s.index("(") + 1 : s.index(")")].replace("/", ",").split(",")
    return [float(x) for x in nums[:3]]


def favicon(page):
    links = page.evaluate(
        "() => [...document.querySelectorAll('link[rel~=icon], link[rel=apple-touch-icon], link[rel=manifest]')]"
        ".map(l => ({rel: l.rel, type: l.type, href: l.href, sizes: l.sizes && l.sizes.value}))"
    )
    print("icon links:", json.dumps(links))
    for link in links:
        with urllib.request.urlopen(link["href"]) as r:
            body = r.read()
            print(f"  {link['href']} -> {r.status} {r.headers.get('content-type')} {len(body)} bytes")
            print("   ", body[:400].decode("utf-8", "replace"))
    for path in ("/favicon.ico", "/favicon.svg", "/apple-touch-icon.png"):
        try:
            with urllib.request.urlopen(HUB + path) as r:
                body = r.read()
                print(f"  {path} -> {r.status} {r.headers.get('content-type')} {len(body)} bytes; head {body[:15]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {path} -> {exc}")


def main():
    with Judge("s1023-pj", hub=HUB, key=KEY) as j:
        for mode in ("dark", "light"):
            page = j.page(PA, mode=mode, width=1440, height=900)
            page.wait_for_timeout(3000)
            if mode == "dark":
                favicon(page)
            info = page.evaluate(MARK_JS)
            print(mode, "wide:", json.dumps(info))
            if info:
                fg, bg = parse_rgb(info["stroke"]), parse_rgb(info["railBg"])
                if fg and bg:
                    print(f"  stroke vs rail contrast {contrast(fg, bg)}")
            j.shot(page, f"01_rail_{mode}")
            j.shot(page, f"01_head_{mode}", locator=page.locator(".aw-rail-head").first)
            # zoomed look at the mark itself
            page.evaluate("() => { const m = document.querySelector('[data-testid=rail-brand-loop]'); if (m) { m.style.width='96px'; m.style.height='96px'; } }")
            j.shot(page, f"02_mark_zoom_{mode}", locator=page.locator("[data-testid=rail-brand-loop]").first)
            page.context.close()

            # minimum rail width
            ctx_page = j.page(PA, mode=mode, width=1440, height=900)
            ctx_page.evaluate("() => localStorage.setItem('aw.sidebarWidth', '180')")
            ctx_page.reload(wait_until="domcontentloaded")
            ctx_page.wait_for_timeout(3000)
            mn = ctx_page.evaluate("() => { const s = document.querySelector('[data-testid=sidebar]'); return s && s.getBoundingClientRect().width }")
            # find the slider bounds the app applies
            slider = ctx_page.locator("[role=separator], [data-testid*=resize]").first
            print(mode, "rail width", mn, "separator present", slider.count())
            info = ctx_page.evaluate(MARK_JS)
            print(mode, "min rail:", json.dumps(info))
            j.shot(ctx_page, f"03_head_minrail_{mode}", locator=ctx_page.locator(".aw-rail-head").first)

            # compact rail
            toggle = ctx_page.get_by_test_id("rail-collapse-toggle")
            if toggle.count():
                toggle.click()
                ctx_page.wait_for_timeout(800)
            compact = ctx_page.evaluate(
                "() => { const s = document.querySelector('[data-testid=sidebar]'); const h = s && s.querySelector('.aw-rail-head');"
                " return {compact: s && s.dataset.compact, width: s && s.getBoundingClientRect().width,"
                " loop: !!document.querySelector('[data-testid=rail-brand-loop]'), headHtml: h && h.innerHTML.slice(0, 600)} }"
            )
            print(mode, "compact:", json.dumps(compact))
            j.shot(ctx_page, f"04_compact_{mode}")
            if toggle.count():
                ctx_page.get_by_test_id("rail-collapse-toggle").click()
                ctx_page.wait_for_timeout(500)
            ctx_page.context.close()

            # narrow window
            np = j.page(PA, mode=mode, width=640, height=800)
            np.wait_for_timeout(3000)
            info = np.evaluate(MARK_JS)
            sb = np.evaluate("() => { const s = document.querySelector('[data-testid=sidebar]'); return s && {compact: s.dataset.compact, w: s.getBoundingClientRect().width} }")
            print(mode, "narrow 640:", json.dumps(info), json.dumps(sb))
            j.shot(np, f"05_narrow_{mode}")
            np.context.close()
        print("errors:", j.errors[:5])


if __name__ == "__main__":
    main()
