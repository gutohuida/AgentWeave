// Drive Copilot through its own SDK (`copilot --headless --stdio`), the integration surface GitHub
// ships for programmatic hosts, and compare it with the ACP surface `hub/hub/copilot_acp.py` uses
// (probe: d1027_copilot_bg_ctx_probe.py). Usage:
//   node d1027_copilot_sdk_probe.mjs ctx <model> <default|long_context> <out.jsonl>
//   node d1027_copilot_sdk_probe.mjs bg  <model> <out.jsonl>
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const root = join(process.env.APPDATA, "npm", "node_modules", "@github", "copilot", "node_modules",
  "@github", "copilot-win32-x64");
const sdk = await import(pathToFileURL(join(root, "copilot-sdk", "index.js")).href);
const { CopilotClient, RuntimeConnection, approveAll } = sdk;

const [mode, model, a3, a4] = process.argv.slice(2);
const out = mode === "ctx" ? a4 : a3;
writeFileSync(out, "");
const t0 = Date.now();
const log = (kind, data) => appendFileSync(out, JSON.stringify({ t: (Date.now() - t0) / 1000, kind, data }) + "\n");

const ws = join(process.env.TEMP, "copilot_sdk_probe_ws");
mkdirSync(ws, { recursive: true });
const client = new CopilotClient({
  connection: RuntimeConnection.forStdio({ path: join(root, "copilot.exe") }),
  workingDirectory: ws,
  useLoggedInUser: true,
});
await client.start();

const cfg = { model, onPermissionRequest: approveAll, workingDirectory: ws };
if (mode === "ctx" && a3 !== "default") cfg.contextTier = a3;
const session = await client.createSession(cfg);
log("created", { sessionId: session.sessionId, contextTier: cfg.contextTier ?? null });

const noisy = new Set(["assistant.message_delta", "assistant.reasoning_delta", "assistant.streaming_delta",
  "assistant.tool_call_delta", "tool.execution_partial_result", "tool.execution_progress"]);
let idleResolve;
const idle = new Promise((r) => (idleResolve = r));
session.on((ev) => {
  if (noisy.has(ev.type)) return;
  log("event", { type: ev.type, agentId: ev.agentId ?? null, data: ev.data });
  if (ev.type === "session.idle" && !ev.agentId) idleResolve(ev);
});

const prompt = mode === "ctx"
  ? "Reply with the single word OK."
  : "Use your task tool to launch ONE sub-agent in background mode (agent_type task) whose job is: " +
    "run the shell command `powershell -c Start-Sleep 45; echo slept` and report its output. " +
    "Immediately after launching it, reply with the single word LAUNCHED and end your turn. " +
    "Do not wait for it and do not read its result.";
const sendStart = Date.now();
await session.send({ prompt });
log("send_returned", { after_s: (Date.now() - sendStart) / 1000 });
const ev = await Promise.race([idle, new Promise((r) => setTimeout(() => r(null), 300_000))]);
log("idle_or_timeout", { idle: !!ev, after_s: (Date.now() - sendStart) / 1000 });
await session.disconnect?.();
await client.stop();
process.exit(0);
