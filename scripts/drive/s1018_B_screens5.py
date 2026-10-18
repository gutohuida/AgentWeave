from s1018_B_lib import e2e, P, OUT, rows  # noqa
from s1018_B_screens import note, safe, notes, text  # noqa
from uiharness import Judge
with Judge("s1018-sweepB5", hub="http://127.0.0.1:8032", key=e2e.key()) as j:
    page = j.page(P, mode="light", query="tab=spec")
    page.get_by_test_id("spec-page").wait_for(timeout=30000); page.wait_for_timeout(1500)
    page.get_by_text("Interval roadmap", exact=True).first.click(); page.wait_for_timeout(1500)
    j.shot(page, "50_picker_open", full_page=True)
    note("strip: " + text(page, "spec-corpus-strip")[:1500])
    def adopt_all():
        page.get_by_test_id("spec-corpus-adopt-all").click(); page.wait_for_timeout(2500)
        j.shot(page, "51_after_adopt_all", full_page=True)
        note("adopt result: " + text(page, "spec-corpus-adopt-result")[:1500])
    safe("adopt all", adopt_all)
    def rebuild():
        page.get_by_test_id("spec-corpus-rebuild").click(); page.wait_for_timeout(2500)
        j.shot(page, "52_after_rebuild", full_page=True)
        note("after rebuild strip: " + text(page, "spec-corpus-strip")[:1500])
    safe("rebuild", rebuild)
    page.context.close()
(OUT / "screens5.txt").write_text("\n".join(notes), encoding="utf-8")
