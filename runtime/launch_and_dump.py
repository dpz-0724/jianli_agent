# -*- coding: utf-8 -*-
"""Launch target, enumerate windows, dump readable memory, scan plaintext strings."""
import ctypes, ctypes.wintypes as wt, subprocess, time, os, re

EXE = r"C:\Users\Administrator\Desktop\云只_智联 4.3.8.exe"
OUT = r"E:\终身学习\云只智联_reverse\runtime"
os.makedirs(OUT, exist_ok=True)
log = open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8")
def w(s):
    log.write(s + "\n"); log.flush(); print(s)

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32

# ---------- launch ----------
proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
pid = proc.pid
w(f"PID={pid}")

# wait, sampling liveness
alive = []
for i in range(6):
    time.sleep(2)
    alive.append(proc.poll() is None)
w(f"liveness samples (every 2s): {alive}")

# ---------- enumerate windows of pid ----------
wins = []
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

def get_text(hwnd):
    n = u32.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, b, n + 1)
    return b.value

def get_cls(hwnd):
    b = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, b, 256)
    return b.value

def enum_win(hwnd, lp):
    t = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(t))
    if t.value == pid:
        wins.append([hwnd, get_cls(hwnd), get_text(hwnd), []])
    return True

u32.EnumWindows(WNDENUMPROC(enum_win), 0)

# child controls
def enum_child(hwnd, lp):
    wins[-1][3].append([hwnd, get_cls(hwnd), get_text(hwnd)])
    return True

CHILDENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
for entry in wins:
    u32.EnumChildWindows(entry[0], CHILDENUM(enum_child), 0)

w(f"\n=== WINDOWS: {len(wins)} top-level ===")
for h, cls, txt, children in wins:
    w(f"[0x{h:X}] class={cls!r} text={txt!r} children={len(children)}")
    for ch, ccls, ctxt in children:
        w(f"    [0x{ch:X}] {ccls!r} {ctxt!r}")

# ---------- memory dump + string scan ----------
class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD),
                ("__a1", wt.DWORD),
                ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD),
                ("Protect", wt.DWORD),
                ("Type", wt.DWORD),
                ("__a2", wt.DWORD)]

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not h:
    w("OpenProcess FAILED (process likely exited or protected)")
else:
    MEM_COMMIT = 0x1000
    readable = (0x02, 0x04, 0x08, 0x20, 0x40, 0x80)
    mbi = MBI()
    addr = 0
    regions = []
    while True:
        rr = k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not rr:
            break
        if mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in readable:
            regions.append((mbi.BaseAddress, mbi.RegionSize, mbi.Protect & 0xFF))
        addr = mbi.BaseAddress + mbi.RegionSize

    w(f"\n=== MEMORY: {len(regions)} readable committed regions ===")
    total = sum(sz for _, sz, _ in regions)
    w(f"total readable bytes: {total/1024/1024:.1f} MB")

    ascii_re = re.compile(rb"[\x20-\x7e]{8,}")
    u16_ascii_re = re.compile(rb"(?:[\x20-\x7e]\x00){6,}")
    u16_cjk_re = re.compile(rb"(?:[\x00-\xff][\x4e-\x9f]){3,}")

    found = {"ascii": set(), "u16": set(), "cjk": set()}
    buf = ctypes.create_string_buffer(1024*1024*4)
    for base, sz, prot in regions:
        off = 0
        while off < sz:
            chunk = min(sz - off, len(buf) - 1)
            read = ctypes.c_size_t()
            ok = k32.ReadProcessMemory(h, ctypes.c_void_p(base + off), buf, chunk, ctypes.byref(read))
            if not ok or read.value == 0:
                break
            raw = buf.raw[:read.value]
            for m in ascii_re.findall(raw):
                found["ascii"].add(m.decode("ascii", "ignore"))
            for m in u16_ascii_re.findall(raw):
                found["u16"].add(m.decode("utf-16le", "ignore"))
            for m in u16_cjk_re.findall(raw):
                s = m.decode("utf-16le", "ignore")
                if re.search(r"[\u4e00-\u9fff]", s):
                    found["cjk"].add(s)
            off += chunk

    def dump(name, items):
        items = sorted(items, key=len, reverse=True)
        p = os.path.join(OUT, name + ".txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(items))
        w(f"{name}: {len(items)} strings -> {p}")

    dump("mem_ascii", found["ascii"])
    dump("mem_u16", found["u16"])
    dump("mem_cjk", found["cjk"])
    k32.CloseHandle(h)

log.close()
print("ALLDONE")