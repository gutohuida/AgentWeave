import pathlib
from playwright.sync_api import sync_playwright
PAGE = pathlib.Path("index.html").resolve().as_uri()
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); cdp = pg.context.new_cdp_session(pg)
    for mode in ("native","hybrid"):
        pg.goto(PAGE+"?mode="+mode)
        pg.evaluate("s=>spike.load(s)", "see [[SPEC-1]]|now")
        cdp.send("Input.imeSetComposition", {"text":"n","selectionStart":1,"selectionEnd":1})
        cdp.send("Input.imeSetComposition", {"text":"","selectionStart":0,"selectionEnd":0})
        print(mode, "immediately:", pg.evaluate("()=>spike.serialise()"), pg.evaluate("()=>{const s=getSelection();return [s.anchorNode.nodeName, s.anchorNode.parentNode.className, s.anchorOffset]}"))
        pg.wait_for_timeout(100)
        print(mode, "after a tick:", pg.evaluate("()=>spike.serialise()"))
        pg.keyboard.type("x")
        print(mode, "then type x:", pg.evaluate("()=>spike.serialise()"), pg.evaluate("()=>JSON.stringify(ed.innerHTML)"))
    b.close()
