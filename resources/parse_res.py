# -*- coding: utf-8 -*-
"""Parse PE .rsrc resource directory and dump resources."""
import struct, os

SRC = r"C:\Users\Administrator\Desktop\云只_智联 4.3.8.exe"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")
os.makedirs(OUT, exist_ok=True)

data = open(SRC, "rb").read()

# PE header
e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
opt_off = e_lfanew + 24
magic = struct.unpack_from("<H", data, opt_off)[0]
if magic == 0x20B:
    dd_off = opt_off + 112
else:
    dd_off = opt_off + 96

# data directory index 2 = resources
res_rva, res_size = struct.unpack_from("<II", data, dd_off + 2*8)

# section table
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

RT = {1:"CURSOR",2:"BITMAP",3:"ICON",4:"MENU",5:"DIALOG",6:"STRING",7:"FONTDIR",
      8:"FONT",9:"ACCELERATOR",10:"RCDATA",11:"MESSAGETABLE",12:"GROUP_CURSOR",
      14:"GROUP_ICON",16:"VERSION",17:"DLGINCLUDE",19:"PLUGPLAY",20:"VXD",
      21:"ANICURSOR",22:"ANIICON",23:"HTML",24:"MANIFEST"}

def parse_dir(off, base, depth=0):
    if off is None:
        return
    nchar, nid = struct.unpack_from("<HH", data, off + 12)
    entries = []
    eo = off + 16
    for i in range(nchar + nid):
        name_off, data_off = struct.unpack_from("<II", data, eo + i*8)
        if data_off & 0x80000000:
            is_dir = True
            sub = data_off & 0x7FFFFFFF
        else:
            is_dir = False
            sub = data_off
        if name_off & 0x80000000:
            no = name_off & 0x7FFFFFFF
            ln = struct.unpack_from("<H", data, base + no)[0]
            name = data[base+no+2:base+no+2+ln*2].decode("utf-16le", "ignore")
        else:
            name = str(name_off)
        entries.append((name, is_dir, sub))
    for name, is_dir, sub in entries:
        if is_dir:
            parse_dir(base + sub, base, depth+1)
        else:
            # leaf: data entry
            rva, sz, cp, resv = struct.unpack_from("<IIII", data, base + sub)
            foff = rva2off(rva)
            fname = f"res_{rva:X}.bin"
            if foff is not None:
                blob = data[foff:foff+sz]
                open(os.path.join(OUT, fname), "wb").write(blob)
                print(f"  {'  '*depth}{name!r}  rva=0x{rva:X} size={sz} -> {fname}")
            else:
                print(f"  {'  '*depth}{name!r}  rva=0x{rva:X} size={sz} (unmapped)")

print(f"Resource dir RVA=0x{res_rva:X} size=0x{res_size:X}")
root_off = rva2off(res_rva)
print("Resource tree (root entries):")

# parse top level manually to also print type names
def parse_types(off, base):
    nchar, nid = struct.unpack_from("<HH", data, off + 12)
    eo = off + 16
    types = []
    for i in range(nchar + nid):
        name_off, data_off = struct.unpack_from("<II", data, eo + i*8)
        is_dir = bool(data_off & 0x80000000)
        sub = data_off & 0x7FFFFFFF
        if name_off & 0x80000000:
            no = name_off & 0x7FFFFFFF
            ln = struct.unpack_from("<H", data, base + no)[0]
            nm = data[base+no+2:base+no+2+ln*2].decode("utf-16le", "ignore")
        else:
            nm = name_off
            nm = RT.get(name_off, str(name_off))
        types.append((nm, is_dir, sub))
    return types

types = parse_types(root_off, root_off)
for nm, is_dir, sub in types:
    print(f"TYPE {nm!r} is_dir={is_dir}")

# full recursive dump
print("\n--- Full resource dump ---")
parse_dir(root_off, root_off)
print("DONE ->", OUT)