"""Provoke `stream_gap` on a project SSE stream: a reader with a 4 KiB receive buffer stops reading
while 900 large tasks are created, then reads what arrived (2026-10-20: one gap frame, dropped 152).
State from s1020_traces.py (project P2) on the scratch Hub it names.
"""
import sys, socket, time
sys.argv=['x','none'];sys.path.insert(0,'scripts/drive')
import s1020_traces as T, e2e
P2=T.S["P2"]
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096); s.connect(("127.0.0.1",8141))
s.sendall(f"GET /api/v1/projects/{P2}/events HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {e2e.key()}\r\nAccept: text/event-stream\r\n\r\n".encode())
time.sleep(1); first=s.recv(4096).decode(errors="replace"); print("FIRST:", first[:300].replace("\r\n"," | "))
t0=time.time(); ok=0
for i in range(900):
    st,_=e2e.request("POST",f"/projects/{P2}/tasks",{"title":f"flood {i} "+"x"*200,"description":"y"*4000})
    ok+= st==201
print("created",ok,"in",round(time.time()-t0),"s")
s.settimeout(3); buf=b""
try:
    while True:
        d=s.recv(65536)
        if not d: break
        buf+=d
except socket.timeout: pass
text=buf.decode(errors="replace")
print("bytes",len(buf),"task events",text.count("event: task_created"), "gap frames", text.count("event: stream_gap"))
i=text.find("stream_gap"); print(text[i-20:i+120] if i>=0 else "no gap")
s.close()
st,h=e2e.request("GET",f"/projects/{P2}/events/history?limit=500"); print("history",st,len(h), h[0] if h else None)
print("history limit=501",e2e.request("GET",f"/projects/{P2}/events/history?limit=501")[0])
print("history severity=warn",e2e.request("GET",f"/projects/{P2}/events/history?severity=warn")[1][:2])
print("history severity=bogus",e2e.request("GET",f"/projects/{P2}/events/history?severity=bogus"))
