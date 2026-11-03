"""Records, from outside, what each thread of one process is doing: run as
`python -I _thread_observer.py <pid> <out file>`, it samples every few milliseconds until its stdin
closes, and prints `ready` once it has its first sample. The lag probe starts it for its window, because inside the process a sample needs the GIL,
so a gap in the probe's own samples cannot say whether a thread held the GIL or the machine stopped
the process (F1119, AW-25). Windows only: elsewhere it exits at once.

Each line is `<perf_counter> <hard faults> <tid>:<state>:<wait reason>:<cpu 100ns>,...`.
`time.perf_counter` is the machine's performance counter on Windows, so the probe can line these
up with its own windows.
"""

from __future__ import annotations

import ctypes
import struct
import sys
import threading
import time

INTERVAL = 0.004


def main() -> int:
    if sys.platform != "win32":
        return 0
    pid, out = int(sys.argv[1]), sys.argv[2]
    ntdll = ctypes.WinDLL("ntdll")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentThread.restype = ctypes.c_void_p
    kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x80)  # HIGH
    kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 2)  # HIGHEST
    done = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.read(), done.set()), daemon=True).start()
    size = 1 << 21
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_ulong()
    lines = []
    while not done.is_set():
        status = ntdll.NtQuerySystemInformation(5, buf, size, ctypes.byref(got))
        now = time.perf_counter()
        if status != 0:
            size = max(size * 2, got.value + (1 << 16))
            buf = ctypes.create_string_buffer(size)
            continue
        at = 0
        while True:
            following, count = struct.unpack_from("<II", buf, at)
            if struct.unpack_from("<Q", buf, at + 0x50)[0] == pid:
                faults = struct.unpack_from("<I", buf, at + 0x10)[0]
                threads = []
                for i in range(count):
                    thread = at + 0x100 + 80 * i
                    kernel, user = struct.unpack_from("<qq", buf, thread)
                    tid = struct.unpack_from("<Q", buf, thread + 0x30)[0]
                    state, reason = struct.unpack_from("<II", buf, thread + 0x44)
                    threads.append(f"{tid}:{state}:{reason}:{kernel + user}")
                lines.append(f"{now:.6f} {faults} {','.join(threads)}")
                if len(lines) == 1:
                    print("ready", flush=True)
                break
            if not following:
                if not lines:
                    print("ready", flush=True)  # nothing to wait for
                done.set()  # the process is gone
                break
            at += following
        time.sleep(INTERVAL)
    with open(out, "w", encoding="ascii") as handle:
        handle.write("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
