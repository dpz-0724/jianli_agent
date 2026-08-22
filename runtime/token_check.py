# -*- coding: utf-8 -*-
import ctypes
from ctypes import wintypes

k32 = ctypes.windll.kernel32
adv = ctypes.windll.advapi32
shell = ctypes.windll.shell32

# IsUserAnAdmin
shell.IsUserAnAdmin.restype = wintypes.BOOL
print("IsUserAnAdmin:", bool(shell.IsUserAnAdmin()))

# OpenProcessToken(self, TOKEN_QUERY=0x0008)
token = wintypes.HANDLE()
ok = k32.OpenProcessToken(k32.GetCurrentProcess(), 0x0008, ctypes.byref(token))
print("OpenProcessToken:", ok)

class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", wintypes.DWORD)]

te = TOKEN_ELEVATION()
ret = wintypes.DWORD()
r = adv.GetTokenInformation(token, 20, ctypes.byref(te), ctypes.sizeof(te), ctypes.byref(ret))  # TokenElevation=20
print("GetTokenInformation(TokenElevation):", r, "TokenIsElevated:", te.TokenIsElevated)

# TokenIntegrityLevel = 25 -> TOKEN_MANDATORY_LABEL { SID_AND_ATTRIBUTES { SID*, DWORD } }
class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]
class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]
tml = TOKEN_MANDATORY_LABEL()
ret2 = wintypes.DWORD()
r2 = adv.GetTokenInformation(token, 25, ctypes.byref(tml), ctypes.sizeof(tml), ctypes.byref(ret2))
print("GetTokenInformation(Integrity):", r2)
if r2:
    sid = tml.Label.Sid
    # get RID (last subauthority)
    adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    adv.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    cnt = adv.GetSidSubAuthorityCount(sid)[0]
    rid = adv.GetSidSubAuthority(sid, cnt - 1)[0]
    print("Integrity RID:", rid, "(0x2000=medium, 0x3000=high, 0x4000=system)")
k32.CloseHandle(token)