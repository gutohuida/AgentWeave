from s1018_B_lib import *  # noqa
import re
RM = "spec/changes/coral-griffin/spec.json"
c, html = req("GET", f"/projects/{P}/project/spec?path={RM}", show=False)
t = html["content"]
t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
t = re.sub(r"<script.*?</script>", "", t, flags=re.S)
print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:2500])
