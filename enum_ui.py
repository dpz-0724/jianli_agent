# -*- coding: utf-8 -*-
"""枚举原程序主界面的完整窗口/控件树（PID 由参数传入）。"""
import ctypes, ctypes.wintypes as wt, sys

pid = int(sys.argv[1])
u32 = ctypes.windll.user32

out = []
def get_text(hwnd):
    n = u32.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, b, n + 1)
    return b.value

def get_cls(hwnd):
    b = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, b, 256)
    return b.value

def visible(hwnd):
    return bool(u32.IsWindowVisible(hwnd))

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
tops = []
def enum_top(hwnd, lp):
    t = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(t))
    if t.value == pid:
        tops.append(hwnd)
    return True
u32.EnumWindows(WNDENUMPROC(enum_top), 0)

def walk(hwnd, depth):
    txt = get_text(hwnd)
    cls = get_cls(hwnd)
    vis = visible(hwnd)
    out.append(("  " * depth) + f"[0x{hwnd:X}] cls={cls!r} text={txt!r} visible={vis}")
    if depth < 5:
        CHILD = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def ec(h, lp):
            walk(h, depth + 1)
            return True
        u32.EnumChildWindows(hwnd, CHILD(ec), 0)

for h in tops:
    walk(h, 0)

open(r"E:\终身学习\云只智联_reverse\runtime\main_ui_tree.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out[:400]))
print(f"... total {len(out)} lines")