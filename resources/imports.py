# -*- coding: utf-8 -*-
"""Dump PE import directory: DLLs and imported functions (these survive packing at module level)."""
import struct, os

SRC = r"C:\Users\Administrator\Desktop\云只_智联 4.3.8.exe"
data = open(SRC, "rb").read()

e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
opt_off = e_lfanew + 24
magic = struct.unpack_from("<H", data, opt_off)[0]
dd_off = opt_off + (112 if magic == 0x20B else 96)
imp_rva, imp_size = struct.unpack_from("<II", data, dd_off + 1*8)
print(f"Import table RVA=0x{imp_rva:X} size=0x{imp_size:X}")

nsec = struct.unpack_from("<H", data, e_lfanew + 6)[0]
size_opt = struct.unpack_from("<H", data, e_lfanew + 20)[0]
sec_off = opt_off + size_opt
sections = []
for i in range(nsec):
    o = sec_off + i*40
    name = data[o:o+8].rstrip(b"\x00").decode("ascii", "ignore")
    vsz, va, rsz, raddr = struct.unpack_from("<IIII", data, o+8)
    sections.append((name, va, vsz, raddr, rsz))

def rva2off(rva):
    for name, va, vsz, raddr, rsz in sections:
        if va <= rva < va + max(vsz, rsz):
            return raddr + (rva - va)
    return None

def cstr_at(rva):
    o = rva2off(rva)
    if o is None: return None
    end = data.find(b"\x00", o)
    if end < 0: end = o + 256
    return data[o:end].decode("ascii", "ignore")

off = rva2off(imp_rva)
if off is None:
    print("No import table (fully packed/stripped)"); raise SystemExit

i = 0
while True:
    o = off + i*20
    oft, ts, fchain, name_rva, ft = struct.unpack_from("<IIIII", data, o)
    if name_rva == 0 and oft == 0 and ft == 0:
        break
    dll = cstr_at(name_rva) or "<none>"
    funcs = []
    if oft != 0:
        thunk_off = rva2off(oft)
        if thunk_off:
            j = 0
            while True:
                val = struct.unpack_from("<I", data, thunk_off + j*4)[0]
                if val == 0: break
                if val & 0x80000000:
                    funcs.append(f"ord#{val & 0xFFFF}")
                else:
                    no = rva2off(val)
                    if no:
                        hint = struct.unpack_from("<H", data, no)[0]
                        fn = data[no+2:data.find(b"\x00", no+2)].decode("ascii","ignore")
                        funcs.append(fn)
                    else:
                        funcs.append(f"??0x{val:X}")
                j += 1
    print(f"\n[{dll}]  ({len(funcs)} imports)")
    print("  " + ", ".join(funcs[:200]))
    i += 1
    if i > 60: break
print("\nDONE")