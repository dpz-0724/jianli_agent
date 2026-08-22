# -*- coding: utf-8 -*-
"""完整动态 dump：在 VMProtect 解包完成后，抓取进程主模块的完整内存映像，
并解析 PE 节表把每节明文内容落盘，供 IDA/Ghidra 静态分析。

用法: python dump_image.py <PID>
"""
import ctypes
import ctypes.wintypes as wt
import sys
import os
import struct

pid = int(sys.argv[1])
OUT = r"E:\终身学习\云只智联_reverse\dumped"
os.makedirs(OUT, exist_ok=True)

k32 = ctypes.windll.kernel32

# ---- 打开进程 ----
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
k32.OpenProcess.restype = ctypes.c_void_p
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.ReadProcessMemory.restype = wt.BOOL
k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.CloseHandle.argtypes = [ctypes.c_void_p]

hproc = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not hproc:
    print("OpenProcess failed"); sys.exit(1)

def rmem(addr, size):
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(hproc, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
    return buf.raw[:read.value] if ok else b""

# ---- 枚举主模块 ----
TH32CS_SNAPMODULE = 0x00000008
class MODULEENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD),
                ("th32ProcessID", wt.DWORD), ("GlblcntUsage", wt.DWORD),
                ("ProccntUsage", wt.DWORD), ("modBaseAddr", ctypes.c_void_p),
                ("modBaseSize", wt.DWORD), ("hModule", ctypes.c_void_p),
                ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]

h = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
me = MODULEENTRY32()
me.dwSize = ctypes.sizeof(MODULEENTRY32)
k32.Module32First(h, ctypes.byref(me))
base = int(me.modBaseAddr or 0)
size = int(me.modBaseSize or 0)
name = me.szModule.decode("gbk", "ignore") if me.szModule else ("pid_%d" % pid)
print(f"module={name} base=0x{base:X} size=0x{size:X} ({size/1024/1024:.1f} MB)")

# ---- dump 完整映像 ----
print("dumping full image ...")
full = b""
CHUNK = 4 * 1024 * 1024
off = 0
while off < size:
    chunk = min(size - off, CHUNK)
    data = rmem(base + off, chunk)
    if not data:
        data = b"\x00" * chunk  # 未映射页补零
    full += data
    off += chunk
full_path = os.path.join(OUT, f"{name}_fullimage.bin")
open(full_path, "wb").write(full)
print(f"full image -> {full_path} ({len(full)/1024/1024:.1f} MB)")

# ---- 解析节表，落盘各节明文 ----
e_lfanew = struct.unpack_from("<I", full, 0x3C)[0]
nsec = struct.unpack_from("<H", full, e_lfanew + 6)[0]
opt_off = e_lfanew + 24
magic = struct.unpack_from("<H", full, opt_off)[0]
opt_hdr_size = struct.unpack_from("<H", full, e_lfanew + 20)[0]
sec_off = opt_off + opt_hdr_size

manifest = [f"module={name} base=0x{base:X} size=0x{size:X} magic=0x{magic:X} nsec={nsec}"]
for i in range(nsec):
    o = sec_off + i * 40
    sname = full[o:o+8].rstrip(b"\x00").decode("utf-8", "replace") or f"sec{i}"
    vsz, va, rsz, raddr = struct.unpack_from("<IIII", full, o + 8)
    sname = "".join(c if c.isalnum() or c in "._" else "_" for c in sname)
    sec_bin = full[raddr: raddr + max(rsz, vsz)] if rsz else full[raddr: raddr + vsz]
    # 用 VA 兜底：raddr 可能残留加密时 0 值，改用 VA 定位
    if (not rsz) or (rsz == 0):
        sec_bin = full[va: va + vsz]
    fpath = os.path.join(OUT, f"{name}_{sname}.section.bin")
    open(fpath, "wb").write(sec_bin)
    manifest.append(f"  {sname}: VA=0x{va:X} VSz=0x{vsz:X} RAw=0x{raddr:X} RSz=0x{rsz:X} -> {os.path.basename(fpath)} (0x{len(sec_bin):X} bytes)")

open(os.path.join(OUT, "manifest.txt"), "w", encoding="utf-8").write("\n".join(manifest))
print("\n".join(manifest))
k32.CloseHandle(hproc)
print("ALLDONE")