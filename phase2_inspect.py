import glob, os, sqlite3, re
from collections import Counter
dbs = sorted(glob.glob(os.path.join(os.environ.get("TEMP",""), "phase2_*.db")), key=os.path.getmtime)
conn = sqlite3.connect(dbs[-1]); conn.row_factory = sqlite3.Row
cols = [r[1] for r in conn.execute("PRAGMA table_info(candidates)")]
print("candidates 列:", cols)
rows2 = conn.execute("SELECT * FROM candidates").fetchall()
EDU = {"初中及以下","中专/中技","高中","大专","本科","硕士","博士"}
bad_edu = [r for r in rows2 if r["education"] not in EDU]
print(f"\n总候选人 {len(rows2)}, 学历异常 {len(bad_edu)}")
print("  异常学历分布:", Counter(r["education"] for r in bad_edu).most_common(6))
bad_exp = [r for r in rows2 if not re.search(r"(在校/应届|一年以内|1-3年|3-5年|5-10年|10年以上)", r["experience"] or "")]
print(f"经验异常 {len(bad_exp)}:", Counter(r["experience"] for r in bad_exp).most_common(6))
bad_name = [r for r in rows2 if not (r["name"] or "").strip()]
print("空姓名:", len(bad_name))
uid_n = sum(1 for r in rows2 if (r["platform_uid"] or "").strip())
print(f"\nplatform_uid 非空: {uid_n}/{len(rows2)}")
src = Counter((r["source_url"] or "")[:60] for r in rows2)
print("source_url 分布:", src.most_common(3))
