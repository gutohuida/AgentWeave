"""Drive index.html in Chromium with real key presses (CDP input events), both modes.

py -3.11 testbed/composer-box-spike/drive.py
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

PAGE = pathlib.Path(__file__).with_name("index.html").resolve().as_uri()
B = "[[SPEC-1]]"

# (name, start state, actions, expected state). Action: ("press", key) | ("type", text)
# | ("paste", text) | ("click_box",) | ("insert_box", id)
SCENARIOS = [
    ("backspace after box removes it", f"see {B}|now", [("press", "Backspace")], "see |now"),
    ("second backspace then eats text", f"see {B}|now", [("press", "Backspace")] * 2, "see|now"),
    ("delete before box removes it", f"see |{B}now", [("press", "Delete")], "see |now"),
    ("arrowleft crosses box in one press", f"see {B}|now", [("press", "ArrowLeft")], f"see |{B}now"),
    ("arrowright crosses box in one press", f"see |{B}now", [("press", "ArrowRight")], f"see {B}|now"),
    (
        "spec criterion: backspace, reinsert, arrowleft",
        f"see {B}|now",
        [("press", "Backspace"), ("insert_box", "SPEC-1"), ("press", "ArrowLeft")],
        f"see |{B}now",
    ),
    ("click on box never leaves caret inside", f"see {B}now|", [("click_box",)], "NOT_INSIDE"),
    ("trailing box: arrowright then type", f"see {B}|", [("press", "ArrowRight"), ("type", "x")], f"see {B}x|"),
    ("leading box: arrowleft from after", f"{B}| go", [("press", "ArrowLeft")], f"|{B} go"),
    ("two boxes: two arrowlefts", f"a {B}{B}|", [("press", "ArrowLeft")] * 2, f"a |{B}{B}"),
    ("typing after box lands after it", f"see {B}|now", [("type", " ok ")], f"see {B} ok |now"),
    ("@ trigger next to box (after a space)", f"see {B}|now", [("type", " @sp")], "TRIGGER:@sp"),
    ("@ trigger directly after box", f"see {B}|", [("type", "@sp")], "TRIGGER:@sp"),
    ("paste plain text after box", f"see {B}|now", [("paste", "<b>pasted</b> ")], f"see {B}<b>pasted</b> |now"),
    (
        "shift-select across box then backspace",
        f"see {B}n|ow",
        [("press", "Shift+ArrowLeft")] * 3 + [("press", "Backspace")],
        "see|ow",
    ),
    ("undo after box backspace restores box", f"see {B}|now", [("press", "Backspace"), ("press", "Control+z")], f"see {B}|now"),
    ("undo after box delete restores box", f"see |{B}now", [("press", "Delete"), ("press", "Control+z")], f"see |{B}now"),
    ("undo after paste", f"see {B}|now", [("paste", "xy"), ("press", "Control+z")], f"see {B}|now"),
]


def run(page, mode):
    page.goto(f"{PAGE}?mode={mode}")
    results = []
    for name, start, actions, want in SCENARIOS:
        page.evaluate("s => window.spike.load(s)", start)
        for act in actions:
            if act[0] == "press":
                page.keyboard.press(act[1])
            elif act[0] == "type":
                page.keyboard.type(act[1])
            elif act[0] == "paste":
                # Put both text/plain and text/html on the real clipboard, then a real Ctrl+V.
                page.evaluate(
                    """t => navigator.clipboard.write([new ClipboardItem({
                         'text/plain': new Blob([t], {type: 'text/plain'}),
                         'text/html': new Blob([t], {type: 'text/html'})})])""",
                    act[1],
                )
                page.keyboard.press("Control+v")
            elif act[0] == "click_box":
                page.click("#ed .box")
            elif act[0] == "insert_box":
                page.evaluate("id => window.spike.insertBox(id)", act[1])
        got = page.evaluate("() => window.spike.serialise()")
        html_ok = page.evaluate("() => !document.querySelector('#ed b')")
        if want == "NOT_INSIDE":
            ok = "<INSIDE>" not in got
        elif want.startswith("TRIGGER:"):
            menu = page.inner_text("#menu")
            ok = menu == "trigger:" + want[len("TRIGGER:") :]
            got = f"{got}  menu={menu!r}"
        else:
            ok = got == want and html_ok
        results.append((ok, name, got, want))
    return results


def main():
    failed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless="--headed" not in sys.argv)
        ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        for mode in ("native", "guarded", "hybrid"):
            print(f"== mode={mode} ({browser.version})")
            for ok, name, got, want in run(page, mode):
                failed += mode == "hybrid" and not ok
                print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {got!r}" + ("" if ok else f" want {want!r}"))
        browser.close()
    print(f"hybrid failures: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
