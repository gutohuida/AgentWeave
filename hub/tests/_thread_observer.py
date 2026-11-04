"""Records, from outside, what each thread of one process is doing: run as
`python -I _thread_observer.py <pid> <out file> [<GIL address> <thread id offset>]`, it samples
every few milliseconds until its stdin closes, and prints `ready` once it has its first sample. The
lag probe starts it for its window, because inside the process a sample needs the GIL, so a gap in
the probe's own samples cannot say whether a thread held the GIL or the machine stopped the process
(F1119, AW-25). Given where the process keeps its GIL, it also reads who holds it (AW-27). Windows
only: elsewhere it exits at once.

Each line is `<perf_counter> <hard faults> <GIL> <tid>:<state>:<wait reason>:<cpu 100ns>,...`, where
`<GIL>` is the id of the thread holding it, 0 when nobody does, or -1 when it could not be read.
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


def _gil_reader(kernel32, pid: int, where: "list[str]"):  # noqa: ANN001, ANN202
    """A callable answering which thread of process `pid` holds its GIL: its id, 0 when nobody
    does, -1 when it cannot be read. `where` is the address of the GIL's `last_holder`, which
    `locked` follows, and the offset of a thread state's thread id, both as the probe found them."""
    if len(where) != 2:
        return lambda: -1
    gil, tid_offset = int(where[0]), int(where[1])
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.ReadProcessMemory.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
    ]
    process = kernel32.OpenProcess(0x0010, False, pid)  # PROCESS_VM_READ
    if not process:
        return lambda: -1
    state = ctypes.create_string_buffer(16)
    tid = ctypes.c_uint32()

    def holder() -> int:
        if not kernel32.ReadProcessMemory(process, gil, state, 16, None):
            return -1
        last_holder, locked = struct.unpack_from("<Qi", state.raw)
        if not locked:
            return 0
        if not kernel32.ReadProcessMemory(
            process, last_holder + tid_offset, ctypes.byref(tid), 4, None
        ):
            return -1
        return tid.value

    return holder


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
    gil_holder = _gil_reader(kernel32, pid, sys.argv[3:5])
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
                lines.append(f"{now:.6f} {faults} {gil_holder()} {','.join(threads)}")
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
