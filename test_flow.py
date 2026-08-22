# -*- coding: utf-8 -*-
"""端到端流程测试：候选数据 → 关键词提取 → 打分排序 → 入库 → 读取排序。"""
import os, sys, tempfile, json
sys.path.insert(0, "code")
from db import DB
from matcher import extract_keywords, rank_candidates

# 用临时库，避免污染真实数据
tmp = os.path.join(tempfile.gettempdir(), "flow_test.db")
if os.path.exists(tmp):
    os.remove(tmp)

db = DB(tmp)

jd = "招聘高级 Java 后端开发，本科以上，5年经验，熟悉 Spring Boot、MySQL、Redis、微服务，工作地北京朝阳"
kws = extract_keywords(jd, ["后端"])
print("提取关键词:", kws)

cands = [
    {"name": "张三", "title": "Java后端开发", "location": "北京", "education": "本科",
     "experience": "6年", "age": 30, "activity": "在线", "text": "Spring Boot MySQL Redis 微服务"},
    {"name": "李四", "title": "销售", "location": "上海", "education": "大专",
     "experience": "3年", "age": 28, "activity": "本月活跃", "text": "销售管理 客户"},
    {"name": "王五", "title": "Java开发", "location": "北京", "education": "硕士",
     "experience": "5年", "age": 27, "activity": "刚刚活跃", "text": "Java Spring Redis"},
    {"name": "张三", "title": "Java后端开发", "location": "北京", "education": "本科",
     "experience": "6年", "age": 30, "activity": "在线", "text": "重复记录"},
]

filt = {"education": ["本科", "硕士"], "experience": ["3-5年", "5-10年", "1-3年"],
        "location": "北京", "age_min": "22", "age_max": "40"}

ranked = rank_candidates(cands, kws, filt)
print("\n=== 排序结果 ===")
for c in ranked:
    print(f"#{c['_rank']} {c['name']:<4} 分={c['_score']:<6} {c['_detail']}")

# 入库
for c in ranked:
    c["score"] = c["_score"]
    c["rank"] = c["_rank"]
    c["detail"] = json.dumps(c["_detail"], ensure_ascii=False)
saved = db.save_candidates(ranked)
print(f"\n入库 {saved} 条（去重后）")

rows = db.ranked_candidates()
print("读回排序行数:", len(rows))
for r in rows[:3]:
    print(" ", r)

db.close()
print("FLOW TEST OK")