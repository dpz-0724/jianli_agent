# -*- coding: utf-8 -*-
"""V3 产品端到端测试：演示模式下「开始筛选」全流水线。
验证：填条件 → 点开始 → 进度可见 → 结果入池 → 自动切换到排序页。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod

a = appmod.App()
ft = a.filter_tab

# 填条件
ft.kw_var.set("Java 后端")
ft.jd_text.insert("1.0", "招聘高级Java后端开发，本科及以上学历，3年以上经验，熟悉Spring Boot、MySQL，工作地北京")
ft.do_parse_jd()
ft.demo_var.set(True)

print("解析后条件:", ft.collect())
print("进度状态(开始):", ft.status_var.get())

# 点「开始筛选」
ft.start_filter()

deadline = time.time() + 25
final = ""
while time.time() < deadline:
    a.update()
    final = ft.status_var.get()
    if final.startswith("✓") or "出错" in final or "失败" in final or "超时" in final:
        break
    time.sleep(0.1)

print("进度状态(结束):", final)
print("进度条:", ft.progress_bar["value"])
rows = a.pool.tree.get_children()
print("候选人排序页行数:", len(rows))
print("当前所在页:", a.nb.tab(a.nb.select(), "text"))

ok = (final.startswith("✓") and len(rows) > 0
      and a.nb.select() == a.nb.tabs()[1])
logs = ft.log_area.get("1.0", "end").strip().splitlines()
print("---- 筛选过程日志 ----")
for line in logs[-12:]:
    print(" ", line)

a.destroy()
print("PIPELINE DEMO TEST", "OK" if ok else "FAILED")