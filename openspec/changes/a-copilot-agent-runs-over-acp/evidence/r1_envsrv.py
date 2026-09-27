import sys, json, os
log = open(os.path.join(os.environ["TEMP"], "ghcp-r1s2-envsrv.log"), "a")
log.write("ENV AW_EXPANDED=%r AW_INHERITED=%r PATH_SET=%r\n" % (os.environ.get("AW_EXPANDED"), os.environ.get("AW_INHERITED"), "PATH" in os.environ)); log.flush()
for line in sys.stdin:
    try: m = json.loads(line)
    except Exception: continue
    if "id" not in m: continue
    meth = m.get("method")
    r = {}
    if meth == "initialize":
        r = {"protocolVersion": m["params"].get("protocolVersion"), "capabilities": {"tools": {}}, "serverInfo": {"name": "envprobe", "version": "0"}}
    elif meth == "tools/list":
        r = {"tools": []}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}) + "\n"); sys.stdout.flush()
