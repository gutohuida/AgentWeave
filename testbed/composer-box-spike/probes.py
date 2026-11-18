import pathlib
from playwright.sync_api import sync_playwright
PAGE = pathlib.Path("index.html").resolve().as_uri()
with sync_playwright() as p:
    b = p.chromium.launch(); ctx=b.new_context(permissions=["clipboard-read","clipboard-write"]); pg = ctx.new_page()
    cdp = ctx.new_cdp_session(pg)
    for mode in ("native","hybrid"):
        pg.goto(PAGE+"?mode="+mode)
        # copy a box, paste it at the end
        pg.evaluate("s=>spike.load(s)", "see |[[SPEC-1]]now")
        pg.keyboard.press("Shift+ArrowRight"); pg.keyboard.press("Control+c"); pg.keyboard.press("End"); pg.keyboard.press("Control+v")
        print(mode, "copy+paste box:", pg.evaluate("()=>spike.serialise()"))
        # IME composition directly after a box
        pg.evaluate("s=>spike.load(s)", "see [[SPEC-1]]|now")
        cdp.send("Input.imeSetComposition", {"text":"ni","selectionStart":2,"selectionEnd":2})
        cdp.send("Input.imeSetComposition", {"text":"nih","selectionStart":3,"selectionEnd":3})
        cdp.send("Input.insertText", {"text":"你好"})
        print(mode, "IME after box:", pg.evaluate("()=>spike.serialise()"))
        # Backspace during an active composition must not take the box
        pg.evaluate("s=>spike.load(s)", "see [[SPEC-1]]|now")
        cdp.send("Input.imeSetComposition", {"text":"n","selectionStart":1,"selectionEnd":1})
        cdp.send("Input.imeSetComposition", {"text":"","selectionStart":0,"selectionEnd":0})
        print(mode, "IME cancelled:", pg.evaluate("()=>spike.serialise()"))
        # auto-growth
        pg.evaluate("s=>spike.load(s)", "a [[SPEC-1]]|")
        h0=pg.evaluate("()=>ed.offsetHeight"); pg.keyboard.press("Shift+Enter"); pg.keyboard.type("line2"); pg.keyboard.press("Shift+Enter"); pg.keyboard.type("line3")
        print(mode, "height", h0, "->", pg.evaluate("()=>ed.offsetHeight"), pg.evaluate("()=>JSON.stringify(ed.innerHTML)"))
    b.close()
