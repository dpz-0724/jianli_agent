# -*- coding: utf-8 -*-
"""Attach to running target, dump memory, extract strings with correct UTF-16LE alignment."""
import ctypes, ctypes.wintypes as wt, sys, os, re

pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
OUT = r"E:\终身学习\云只智联_reverse\runtime"
os.makedirs(OUT, exist_ok=True)

k32 = ctypes.windll.kernel32
k32.OpenProcess.restype = ctypes.c_void_p
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.ReadProcessMemory.restype = wt.BOOL
k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
k32.CloseHandle.argtypes = [ctypes.c_void_p]

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD),
                ("__a1", ctypes.c_uint32),
                ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD),
                ("Protect", wt.DWORD),
                ("Type", wt.DWORD),
                ("__a2", ctypes.c_uint32)]

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
readable = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}

h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not h:
    print("OpenProcess failed"); sys.exit(1)

mbi = MBI()
addr = 0
regions = []
while True:
    rr = k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.cast(ctypes.byref(mbi), ctypes.c_void_p), ctypes.sizeof(mbi))
    if rr == 0:
        break
    base = int(mbi.BaseAddress or 0); size = int(mbi.RegionSize or 0)
    if mbi.State == MEM_COMMIT and (int(mbi.Protect) & 0xFF) in readable and size > 0:
        regions.append((base, size, int(mbi.Protect) & 0xFF))
    addr = base + size
print("regions:", len(regions))

ascii_re = re.compile(rb"[\x20-\x7e]{8,}")
cjk_run_re = re.compile(r"[\u4e00-\u9fff]{2}[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u0020-\u007e]{0,48}")
wide_run_re = re.compile(r"[\u0020-\u007e]{6,}")

found = {"ascii": set(), "u16": set(), "cjk": set()}
CHUNK = 4 * 1024 * 1024
buf = ctypes.create_string_buffer(CHUNK)

for base, size, prot in regions:
    off = 0
    while off < size:
        chunk = min(size - off, CHUNK)
        read = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(h, ctypes.c_void_p(base + off), buf, chunk, ctypes.byref(read))
        if not ok or read.value == 0:
            break
        raw = buf.raw[:read.value]
        for m in ascii_re.findall(raw):
            found["ascii"].add(m.decode("ascii", "ignore"))
        # aligned UTF-16LE decode from two possible alignments
        for align in (0, 1):
            seg = raw[align:]
            try:
                txt = seg.decode("utf-16le", "ignore")
            except Exception:
                continue
            for m in cjk_run_re.finditer(txt):
                s = m.group()
                cjk = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
                if cjk >= 2 and cjk / len(s) >= 0.5:
                    found["cjk"].add(s.strip())
            for m in wide_run_re.finditer(txt):
                found["u16"].add(m.group())
        off += chunk

for name, items in found.items():
    items = sorted(items, key=lambda x: -len(x))
    p = os.path.join(OUT, "pid%d_" % pid + name + ".txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(items))
    print(name, len(items), "->", os.path.basename(p))

k32.CloseHandle(h)
print("ALLDONE")