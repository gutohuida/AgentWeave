"""Sweep A (2026-10-18): a scripted Anthropic Messages stand-in for a Copilot provider runner
(after testbed/drive1005-*/stub_provider.py). Each request answers the next scripted tool call,
counted by the tool results already in the conversation; then it ends the turn with text. Requests
that offer no `powershell` tool (side calls) end at once. Logs every request, with each tool result
the CLI sent back, to the file named by argv[2].

    py -3.11 scripts/drive/s1018_A_copilot_stub.py <port> <log.jsonl>
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(sys.argv[1])
LOG = Path(sys.argv[2])
STEPS = [
    ("create", {"path": ".mcp.json", "file_text": "{}"}),
    ("powershell", {"command": "Get-Content no-such-list.txt | Remove-Item", "description": "probe", "initial_wait": 10}),
    ("powershell", {"command": "git log --oneline | Select-Object -First 3", "description": "log", "initial_wait": 10}),
    ("create", {"path": "copilot-ok.txt", "file_text": "ok"}),
]


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        payload = json.dumps({"data": [{"id": "claude-haiku-4-5-20251001", "type": "model",
                                        "display_name": "Claude Haiku 4.5"}], "has_more": False}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {}
        tools = {t.get("name"): t for t in body.get("tools") or []}
        results = []
        for m in body.get("messages") or []:
            if isinstance(m.get("content"), list):
                for c in m["content"]:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        results.append(c)
        step = len(results)
        entry = {"path": self.path, "ntools": len(tools), "step": step,
                 "last_result": json.dumps(results[-1])[:700] if results else None}
        if "powershell" in tools and step == 0:
            entry["schemas"] = {k: tools[k].get("input_schema") for k in ("create", "powershell") if k in tools}
        if "powershell" in tools and step < len(STEPS):
            name, inp = STEPS[step]
            blocks = [{"type": "tool_use", "id": f"toolu_sweepA{step}", "name": name, "input": inp}]
            stop = "tool_use"
            entry["sent"] = [name, inp]
        else:
            blocks = [{"type": "text", "text": "done: " + str(step)}]
            stop = "end_turn"
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        message = {"id": f"msg_sweepA{step}", "type": "message", "role": "assistant",
                   "model": body.get("model", "claude-haiku-4-5-20251001"), "content": [],
                   "stop_reason": None, "stop_sequence": None,
                   "usage": {"input_tokens": 10, "output_tokens": 1}}
        if not body.get("stream"):
            payload = json.dumps({**message, "content": blocks, "stop_reason": stop}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        out = [sse("message_start", {"type": "message_start", "message": message})]
        for i, b in enumerate(blocks):
            if b["type"] == "text":
                out.append(sse("content_block_start", {"type": "content_block_start", "index": i,
                                                       "content_block": {"type": "text", "text": ""}}))
                out.append(sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                                       "delta": {"type": "text_delta", "text": b["text"]}}))
            else:
                out.append(sse("content_block_start", {"type": "content_block_start", "index": i,
                                                       "content_block": {"type": "tool_use", "id": b["id"],
                                                                         "name": b["name"], "input": {}}}))
                out.append(sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                                       "delta": {"type": "input_json_delta",
                                                                 "partial_json": json.dumps(b["input"])}}))
            out.append(sse("content_block_stop", {"type": "content_block_stop", "index": i}))
        out.append(sse("message_delta", {"type": "message_delta",
                                         "delta": {"stop_reason": stop, "stop_sequence": None},
                                         "usage": {"output_tokens": 5}}))
        out.append(sse("message_stop", {"type": "message_stop"}))
        payload = b"".join(out)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Stub).serve_forever()
