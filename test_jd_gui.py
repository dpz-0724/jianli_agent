# -*- coding: utf-8 -*-
"""JD 解析 → 自动带出筛选 的端到端 GUI 集成测试。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app
a = app.App()

# 模拟粘贴 JD 并点解析
a.search.jd_text.insert("1.0", "招聘高级Java后端开发，本科及以上学历，3年以上经验，熟悉Spring Boot、MySQL、Redis，工作地北京")
a.search.do_parse_jd()

ft = a.filter_tab
edu_checked = [k for k, v in ft.edu_vars.items() if v.get()]
exp_checked = [k for k, v in ft.exp_vars.items() if v.get()]
loc = ft.loc_var.get()

print("学历勾选:", edu_checked)
print("经验勾选:", exp_checked)
print("地点:", loc)
print("解析标签:", a.search.parse_label.get())

# 断言：本科及以上 → 本科/硕士/博士
assert "本科" in edu_checked and "硕士" in edu_checked and "博士" in edu_checked, "学历带出错误"
assert "大专" not in edu_checked, "学历带出过宽"
assert "3-5年" in exp_checked and "5-10年" in exp_checked, "经验带出错误"
assert "1-3年" not in exp_checked, "经验带出过宽"
assert "北京" in loc, "地点带出错误"
assert "本科" in a.search.parse_label.get(), "解析摘要缺学历"

# 对比逻辑抽查：best_i 计算
rows = [(10, ) * 11, (20, ) * 11, (15, ) * 11]  # name..status 全占位，index9=score
best = max(range(len(rows)), key=lambda i: rows[i][9] or 0)
assert best == 1, "对比最匹配计算错误"

a.destroy()
print("JD INTEGRATION TEST OK")