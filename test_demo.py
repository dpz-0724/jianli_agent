# -*- coding: utf-8 -*-
"""演示数据 + 跟进状态 + 统计概览 逻辑测试。"""
import os, sys, tempfile, json
sys.path.insert(0, "code")
from db import DB
from demo_data import gen_candidates
from matcher import extract_keywords, rank_candidates

tmp = os.path.join(tempfile.gettempdir(), "demo_test.db")
if os.path.exists(tmp):
    os.remove(tmp)
db = DB(tmp)

# 1. 生成演示数据
cands = gen_candidates(40, seed=42)
print(f"生成演示候选人: {len(cands)}")

# 2. 打分排序
jd = "招聘高级 Java 后端开发，本科以上，5年经验，熟悉 Spring Boot、MySQL、Redis，工作地北京"
kws = extract_keywords(jd, ["后端"])
ranked = rank_candidates(cands, kws, {"location": "北京", "education": ["本科", "硕士"]})
for c in ranked:
    c["score"] = c["_score"]; c["rank"] = c["_rank"]
    c["detail"] = json.dumps(c["_detail"], ensure_ascii=False)
    c["status"] = "待联系"
db.save_candidates(ranked)

# 3. 统计
s = db.stats()
print(f"统计: {s}")
assert s["total"] == len(ranked), "total 统计错误"

# 4. 跟进状态
ids = db.query("SELECT id FROM candidates ORDER BY score DESC LIMIT 3")
for i, (cid,) in enumerate(ids):
    db.update_status(cid, ["已联系", "已约面试", "不合适"][i])
s2 = db.stats()
print(f"标记 3 人后统计: {s2}")
assert s2["contacted"] >= 3, "已跟进统计错误"

# 5. 高匹配计数
db.conn.execute("UPDATE candidates SET score=75 WHERE id=?", (ids[0][0],))
db.conn.commit()
s3 = db.stats()
print(f"高匹配数: {s3['high']}, 平均分: {s3['avg']}")
assert s3["high"] >= 1, "高匹配统计错误"

# 6. 读回排序+状态
rows = db.ranked_candidates(5)
print("排序前 5（id,name,title,score,status）:")
for r in rows:
    print("  ", r[0], r[1], r[2], r[7], r[8])

db.close()
print("DEMO/STATUS/STATS TEST OK")