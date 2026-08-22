# -*- coding: utf-8 -*-
"""GUI 冒烟测试：创建主窗口，1.5 秒后自动关闭，验证能正常构建与销毁。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app
a = app.App()
a.after(1500, a.destroy)
a.mainloop()
print("GUI OK: window created and closed without error")