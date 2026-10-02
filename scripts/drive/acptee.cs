// A pass-through `copilot.exe` that records the ACP stream, for driving
// openspec/changes/a-copilot-run-shows-its-credits group 7. 2026-10-02.
//
// Copilot does not persist its ephemeral `assistant.usage` notifications in
// session-state/<id>/events.jsonl, so a run's per-call sum cannot be checked from Copilot's own
// files. This stub spawns the real native copilot.exe (path in <Dir>\real.txt) with its own raw
// command line and copies stdin, stdout and stderr byte for byte, while appending each direction to
// <Dir>\logs\<yyyyMMdd-HHmmss>-<pid>.{in,out}.jsonl. Nothing is changed or reordered, except:
//
// Task 7.7's replay seam. While <Dir>\refuse.flag exists, a `session/prompt` request is not
// forwarded (so no model call is made). The stub answers it itself with task 1.15(a)'s sequence: a
// `github.com/copilot/sessionEvent` `session.error {errorType: "quota", errorCode:
// "quota_exceeded"}` for the prompt's session, then the prompt's result `{stopReason: "end_turn"}`.
// Everything before the prompt (initialize, session/new or session/load) reaches the real Copilot.
//
// Build (no SDK needed):
//   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe -nologo -out:<Dir>\acptee.exe this.cs
// then pin it as the agent's `config.cli` (PATCH /agents/{name} {"config": {"cli": ...}}): a pinned
// Copilot CLI must be a native executable, not a script (copilot_probe.resolve_copilot_executable).
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

class AcpTee
{
    static readonly object StdoutLock = new object();
    static Stream Stdout;

    static string RawArgs()
    {
        string line = Environment.CommandLine;
        int i = 0;
        if (line.Length > 0 && line[0] == '"')
        {
            i = line.IndexOf('"', 1);
            i = i < 0 ? line.Length : i + 1;
        }
        else
        {
            while (i < line.Length && line[i] != ' ' && line[i] != '\t') i++;
        }
        return line.Substring(i).TrimStart();
    }

    static Thread Pump(Stream from, Stream to, Stream log, object writeLock)
    {
        var t = new Thread(() =>
        {
            var buf = new byte[65536];
            try
            {
                int n;
                while ((n = from.Read(buf, 0, buf.Length)) > 0)
                {
                    lock (writeLock) { to.Write(buf, 0, n); to.Flush(); }
                    if (log != null)
                    {
                        lock (log) { log.Write(buf, 0, n); log.Flush(); }
                    }
                }
            }
            catch (IOException) { }
            catch (ObjectDisposedException) { }
        });
        t.IsBackground = true;
        t.Start();
        return t;
    }

    // Requests, line by line: ACP is newline-delimited JSON-RPC.
    static Thread PumpRequests(Stream from, Stream to, Stream log, string flag)
    {
        var t = new Thread(() =>
        {
            var line = new MemoryStream();
            int b;
            try
            {
                while ((b = from.ReadByte()) >= 0)
                {
                    line.WriteByte((byte)b);
                    if (b != '\n') continue;
                    byte[] bytes = line.ToArray();
                    line.SetLength(0);
                    lock (log) { log.Write(bytes, 0, bytes.Length); log.Flush(); }
                    string text = Encoding.UTF8.GetString(bytes);
                    if (File.Exists(flag) && text.Contains("\"session/prompt\""))
                    {
                        Refuse(text, log);
                        continue;
                    }
                    to.Write(bytes, 0, bytes.Length);
                    to.Flush();
                }
            }
            catch (IOException) { }
            catch (ObjectDisposedException) { }
            try { to.Close(); } catch (Exception) { }
        });
        t.IsBackground = true;
        t.Start();
        return t;
    }

    static void Refuse(string request, Stream log)
    {
        string id = Regex.Match(request, @"""id""\s*:\s*(""[^""]*""|\d+)").Groups[1].Value;
        string session = Regex.Match(request, @"""sessionId""\s*:\s*""([^""]*)""").Groups[1].Value;
        string stamp = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ");
        string error =
            "{\"jsonrpc\":\"2.0\",\"method\":\"github.com/copilot/sessionEvent\",\"params\":{" +
            "\"sessionId\":\"" + session + "\",\"type\":\"session.error\",\"timestamp\":\"" + stamp +
            "\",\"data\":{\"errorType\":\"quota\",\"errorCode\":\"quota_exceeded\"," +
            "\"message\":\"You have exceeded your quota (acptee replay, task 7.7)\"}}}\n";
        string result =
            "{\"jsonrpc\":\"2.0\",\"id\":" + id + ",\"result\":{\"stopReason\":\"end_turn\"}}\n";
        foreach (string message in new[] { error, result })
        {
            byte[] bytes = Encoding.UTF8.GetBytes(message);
            lock (StdoutLock) { Stdout.Write(bytes, 0, bytes.Length); Stdout.Flush(); }
            byte[] marked = Encoding.UTF8.GetBytes("//acptee-out " + message);
            lock (log) { log.Write(marked, 0, marked.Length); log.Flush(); }
        }
    }

    static int Main()
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string real = File.ReadAllText(Path.Combine(dir, "real.txt")).Trim();
        string logs = Path.Combine(dir, "logs");
        Directory.CreateDirectory(logs);
        string stem = Path.Combine(
            logs, DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Process.GetCurrentProcess().Id);
        string args = RawArgs();
        File.WriteAllText(stem + ".argv.txt", args);

        var psi = new ProcessStartInfo(real, args)
        {
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        var child = Process.Start(psi);
        var inLog = new FileStream(stem + ".in.jsonl", FileMode.Create, FileAccess.Write, FileShare.Read);
        var outLog = new FileStream(stem + ".out.jsonl", FileMode.Create, FileAccess.Write, FileShare.Read);

        Stdout = Console.OpenStandardOutput();
        PumpRequests(Console.OpenStandardInput(), child.StandardInput.BaseStream, inLog,
            Path.Combine(dir, "refuse.flag"));
        var o = Pump(child.StandardOutput.BaseStream, Stdout, outLog, StdoutLock);
        var e = Pump(child.StandardError.BaseStream, Console.OpenStandardError(), null, new object());
        child.WaitForExit();
        o.Join(5000);
        e.Join(5000);
        lock (inLog) inLog.Close();
        lock (outLog) outLog.Close();
        return child.ExitCode;
    }
}
