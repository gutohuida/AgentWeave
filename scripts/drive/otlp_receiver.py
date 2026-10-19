"""A tiny OTLP/HTTP receiver for drives: records every POST it is sent, one JSON line each.

Accepts `/v1/traces`, `/v1/logs` and `/v1/metrics` (any path, really) in OTLP/HTTP JSON. A body
that is not JSON (OTLP protobuf) is recorded by size and content type only, so a sender that ignores
`http/json` is still visible. Answers 200 with an empty JSON object, which OTLP reads as full
success.

Usage:
  py -3.11 scripts/drive/otlp_receiver.py <port> <out.jsonl>
  py -3.11 scripts/drive/otlp_receiver.py 4319 C:/Users/me/AppData/Local/Temp/otlp.jsonl

Then point a sender at `http://127.0.0.1:<port>` (the Hub's OTLP endpoint setting, or
`OTEL_EXPORTER_OTLP_ENDPOINT` for a runner CLI). Stop with Ctrl+C.
"""

from __future__ import annotations

import datetime
import gzip
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main(port: int, out_path: str) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            if (self.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
            kind = self.headers.get("Content-Type") or ""
            record = {
                "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "path": self.path,
                "content_type": kind,
                "bytes": len(raw),
                "headers": {k: v for k, v in self.headers.items() if k.lower() != "authorization"},
                "authorization_present": "authorization" in {k.lower() for k in self.headers},
            }
            try:
                record["body"] = json.loads(raw)
            except ValueError:
                record["body"] = None
            with open(out_path, "a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # quiet
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"OTLP receiver on http://127.0.0.1:{port}, writing {out_path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
