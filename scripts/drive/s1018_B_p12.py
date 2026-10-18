from s1018_B_lib import *  # noqa
import urllib.parse
WS = "spec/changes/with space/spec.json"; q = urllib.parse.quote(WS)
req("POST", f"{SPEC}/documents/{q}/rigor", {"rigor": "contract", "reason": "agents propose"}, cut=300)
req("POST", f"{SPEC}/documents/close-exploration?path={q}", cut=200)
req("POST", f"{SPEC}/documents/propose?path={q}", cut=800)
save()
