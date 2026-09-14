// A `claude` that refuses like a spent provider allowance, for driving
// openspec/changes/a-spent-allowance-holds-the-queue (F355) on a drive Hub. 2026-09-14.
//
// The provider's allowance cannot be spent on demand, so the refusal comes from here. While
// <Dir>\refuse.flag exists and the spawning agent (AW_AGENT_IDENTITY) is not "peer", it prints the
// four lines the harness emits on a refusal - init (session id echoing --resume, so the conversation
// stays resumable), rate_limit_event (status rejected, resetsAt 120 s ahead), assistant, result
// is_error - and exits 1. Otherwise it hands its raw command line to the real claude.exe.
// Every spawn is logged to <Dir>\argv.log.
//
// Build (no SDK needed):
//   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe -nologo -out:<bin>\claudestub.exe this.cs
// and put beside it a claude.cmd of the npm shim shape, whose one payload line is
//   "%dp0%\claudestub.exe"   %*
// The Hub unwraps that shape to the .exe (pty_runner._unwrap_cmd_shim), so no cmd.exe sits between
// the Hub and the stub to cut the multi-line prompt at its first newline. Put <bin> first on the
// drive Hub's PATH.
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

class ClaudeStub {
    const string Dir = @"C:\Users\huida\AppData\Local\Temp\f355drive";
    const string Real = @"C:\Users\huida\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe";

    static string Raw() {
        string cl = Environment.CommandLine;
        int i = 0;
        if (cl.StartsWith("\"")) { i = cl.IndexOf('"', 1); i = i < 0 ? cl.Length : i + 1; }
        else { i = cl.IndexOf(' '); if (i < 0) i = cl.Length; }
        return cl.Substring(i).TrimStart();
    }

    static void W(string s) { Console.Out.Write(s + "\n"); Console.Out.Flush(); }

    static int Main(string[] args) {
        string resume = null;
        for (int k = 0; k + 1 < args.Length; k++) if (args[k] == "--resume") resume = args[k + 1];
        string who = Environment.GetEnvironmentVariable("AW_AGENT_IDENTITY") ?? "<unset>";
        bool refuse = File.Exists(Path.Combine(Dir, "refuse.flag")) && who != "peer";
        string stamp = DateTime.UtcNow.ToString("o");
        File.AppendAllText(Path.Combine(Dir, "argv.log"),
            "=== " + stamp + " pid=" + Process.GetCurrentProcess().Id + " agent=" + who + " refuse=" + refuse +
            " resume=" + (resume ?? "<none>") + " argc=" + args.Length + "\n" +
            string.Join("\n", Array.ConvertAll(args, a => "  [" + a.Replace("\r", "\r").Replace("\n", "\n") + "]")) + "\n");
        if (refuse) {
            string sid = resume ?? Guid.NewGuid().ToString();
            long resets = DateTimeOffset.UtcNow.ToUnixTimeSeconds() + 120;
            string notice = "You've hit your limit - resets soon (STUB)";
            string reading = "{\"status\":\"rejected\",\"resetsAt\":" + resets + ",\"rateLimitType\":\"five_hour\",\"overageStatus\":\"rejected\",\"overageDisabledReason\":\"out_of_credits\",\"isUsingOverage\":false,\"unifiedWindows\":{\"five_hour\":{\"utilization\":1.02,\"resetsAt\":" + resets + "}}}";
            W("{\"type\":\"system\",\"subtype\":\"init\",\"session_id\":\"" + sid + "\"}");
            W("{\"type\":\"rate_limit_event\",\"rate_limit_info\":" + reading + ",\"session_id\":\"" + sid + "\"}");
            W("{\"type\":\"assistant\",\"message\":{\"content\":[{\"type\":\"text\",\"text\":\"" + notice + "\"}]},\"session_id\":\"" + sid + "\"}");
            W("{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":true,\"result\":\"" + notice + "\",\"session_id\":\"" + sid + "\"}");
            File.AppendAllText(Path.Combine(Dir, "argv.log"), "  -> REFUSED sid=" + sid + " resetsAt=" + resets + "\n");
            Thread.Sleep(2000);
            return 1;
        }
        var psi = new ProcessStartInfo(Real, Raw());
        psi.UseShellExecute = false;
        var p = Process.Start(psi);
        p.WaitForExit();
        File.AppendAllText(Path.Combine(Dir, "argv.log"), "  -> PASSTHROUGH exit=" + p.ExitCode + "\n");
        return p.ExitCode;
    }
}
