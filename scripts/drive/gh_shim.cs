// The drive's gh shim (pr_landing_drive.py compiles it to gh.exe): logs each call's arguments
// as one JSON line to the file named by GH_SHIM_LOG, then runs the real gh named by GH_SHIM_REAL.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class Shim
{
    static string Json(string v)
    {
        var b = new StringBuilder("\"");
        foreach (char c in v)
        {
            if (c == '\\' || c == '"') b.Append('\\').Append(c);
            else if (c < 32) b.Append("\\u" + ((int)c).ToString("x4"));
            else b.Append(c);
        }
        return b.Append('"').ToString();
    }

    static string Quote(string a)
    {
        if (a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0) return a;
        var b = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in a)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') b.Append('\\', slashes * 2 + 1).Append('"');
            else b.Append('\\', slashes).Append(c);
            slashes = 0;
        }
        return b.Append('\\', slashes * 2).Append('"').ToString();
    }

    static int Main(string[] args)
    {
        var items = new string[args.Length];
        for (int i = 0; i < args.Length; i++) items[i] = Json(args[i]);
        double t = (DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds;
        File.AppendAllText(Environment.GetEnvironmentVariable("GH_SHIM_LOG"),
            "{\"t\": " + t.ToString(System.Globalization.CultureInfo.InvariantCulture)
            + ", \"argv\": [" + string.Join(", ", items) + "]}\n", new UTF8Encoding(false));
        var info = new ProcessStartInfo(Environment.GetEnvironmentVariable("GH_SHIM_REAL"),
            string.Join(" ", Array.ConvertAll(args, Quote)));
        info.UseShellExecute = false;
        using (var p = Process.Start(info)) { p.WaitForExit(); return p.ExitCode; }
    }
}
