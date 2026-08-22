# -*- coding: utf-8 -*-
"""数据库层：复现「云只智联」的本地 SQLite 数据模型。

原程序在内存中暴露了大量 SQLite 查询字符串（sqlite_master / vacuum / sqlite_sequence），
据此还原其本地库结构。字段名按还原的功能词命名，可自行调整。
"""
import os
import sqlite3

def _default_db_dir():
    # PyInstaller onefile 下 `__file__` 指向临时解压目录，数据会随进程退出丢失；
    # 统一固定到用户本地数据目录（与 chrome_profile 同父目录），保证数据库持久化。
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "云只智联")


DEFAULT_DB = os.path.join(_default_db_dir(), "yunzhi.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS resumes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,                 -- 姓名
    phone       TEXT,                 -- 手机号
    wechat      TEXT,                 -- 微信号
    gender      TEXT,                 -- 性别
    age         INTEGER,
    education   TEXT,                 -- 学历
    school      TEXT,                 -- 学校
    experience  TEXT,                 -- 工作经验
    location    TEXT,                 -- 工作地点
    job_status  TEXT,                 -- 求职状态: 离职-正在找工作 / 在职-暂不找工作 / 在职-正在找工作
    source      TEXT,                 -- 来源帖子/职位
    virtual     INTEGER DEFAULT 0,    -- 是否虚拟号码(过滤虚拟号码)
    collected_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS talks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname      TEXT,               -- 牛人昵称
    title         TEXT,               -- 期望职位
    platform_uid  TEXT,               -- 平台用户ID
    post_url      TEXT,               -- 来源帖子
    status        TEXT DEFAULT '未沟通',  -- 未沟通/已沟通/不沟通
    matched_kw    TEXT,               -- 命中的过滤关键词
    updated_at    TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS accounts (
    slot       TEXT PRIMARY KEY,      -- 账号1 ~ 账号9
    username   TEXT,
    password   TEXT,
    owner      TEXT,                  -- 账号所有者
    expire_at  TEXT,                  -- 到期时间
    device_id  TEXT                   -- 绑定设备
);

CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY,
    v TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_uid TEXT,               -- 平台唯一ID（去重用）
    name        TEXT,                -- 姓名/昵称
    title       TEXT,                -- 期望/当前职位
    location    TEXT,
    education   TEXT,
    experience  TEXT,
    age         INTEGER,
    activity    TEXT,                -- 在线/刚刚活跃/今日活跃/本周活跃/本月活跃
    skills      TEXT,                -- 技能/标签
    text        TEXT,                -- 简历摘要（关键词匹配命中用）
    score       REAL,                -- 匹配分 0-100
    rank        INTEGER,             -- 排序号
    detail      TEXT,                -- 匹配明细(JSON/文本)
    status      TEXT DEFAULT '待联系', -- 跟进状态: 待联系/已联系/已约面试/不合适
    source      TEXT,
    collected_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_candidates_uid ON candidates(platform_uid);
"""


class DB:
    def __init__(self, path=DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # check_same_thread=False：筛选流水线在后台线程写库；本工具同一时刻只有一个
        # 工作线程在写，主线程只读，串行安全。
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        # 兼容旧库：为 candidates 补充 status 列
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(candidates)").fetchall()]
        if cols and "status" not in cols:
            self.conn.execute("ALTER TABLE candidates ADD COLUMN status TEXT DEFAULT '待联系'")
        self.conn.commit()

    # ---- 简历 ----
    def upsert_resume(self, r: dict):
        # 按 phone/wechat 去重（对应「简历导出去重」「去重时间」）
        phone = r.get("phone") or ""
        wechat = r.get("wechat") or ""
        if phone:
            row = self.conn.execute("SELECT id FROM resumes WHERE phone=?", (phone,)).fetchone()
            if row:
                return row[0]
        if wechat:
            row = self.conn.execute("SELECT id FROM resumes WHERE wechat=?", (wechat,)).fetchone()
            if row:
                return row[0]
        cols = list(r.keys())
        q = ("INSERT INTO resumes (%s) VALUES (%s)" %
             (",".join(cols), ",".join("?" * len(cols))))
        cur = self.conn.execute(q, [r[c] for c in cols])
        self.conn.commit()
        return cur.lastrowid

    def query(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    # ---- 候选人池 ----
    def save_candidates(self, cands: list):
        """批量写入候选人（platform_uid 去重，否则 name+title 去重）。"""
        saved = 0
        for c in cands:
            uid = c.get("platform_uid")
            if uid:
                row = self.conn.execute("SELECT id FROM candidates WHERE platform_uid=?", (uid,)).fetchone()
            else:
                nm = c.get("name") or ""
                tt = c.get("title") or ""
                row = self.conn.execute(
                    "SELECT id FROM candidates WHERE name=? AND title=?", (nm, tt)).fetchone() if (nm or tt) else None
            if row:
                continue  # 已存在，跳过
            cols = [k for k in c.keys() if not str(k).startswith("_") and k != "id"]
            self.conn.execute(
                "INSERT INTO candidates (%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))),
                [c[k] for k in cols])
            saved += 1
        self.conn.commit()
        return saved

    def clear_candidates(self):
        self.conn.execute("DELETE FROM candidates")
        self.conn.commit()

    def ranked_candidates(self, limit=500):
        """按匹配分降序读取候选人池。"""
        return self.conn.execute(
            "SELECT id,name,title,location,education,experience,activity,score,status,detail "
            "FROM candidates ORDER BY score DESC, activity DESC LIMIT ?", (limit,)).fetchall()

    def update_status(self, cid, status):
        self.conn.execute("UPDATE candidates SET status=? WHERE id=?", (status, cid))
        self.conn.commit()

    def stats(self):
        """统计概览：总候选 / 高匹配(≥70) / 已跟进 / 平均分。"""
        total = self.conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        high = self.conn.execute("SELECT COUNT(*) FROM candidates WHERE score>=70").fetchone()[0]
        contacted = self.conn.execute(
            "SELECT COUNT(*) FROM candidates WHERE status NOT IN ('待联系','')").fetchone()[0]
        avg = self.conn.execute("SELECT COALESCE(AVG(score),0) FROM candidates").fetchone()[0]
        return {"total": total, "high": high, "contacted": contacted, "avg": round(avg, 1)}

    def clear_db(self):
        """清空数据库（对应 UI「清空数据库」）"""
        for t in ("resumes", "talks"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()

    def dedup(self):
        """简历去重：按 phone/wechat 保留最早一条"""
        self.conn.execute("""
            DELETE FROM resumes WHERE id NOT IN (
                SELECT MIN(id) FROM resumes GROUP BY COALESCE(phone, '')||COALESCE(wechat,'')
            )""")
        self.conn.commit()

    def export_csv(self, path):
        import csv
        rows = self.conn.execute("SELECT * FROM resumes").fetchall()
        cols = [c[1] for c in self.conn.execute("PRAGMA table_info(resumes)").fetchall()]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        return path

    def close(self):
        self.conn.close()


if __name__ == "__main__":
    d = DB()
    d.upsert_resume({"name": "测试", "phone": "13800000000", "wechat": "wx_test"})
    print("rows:", d.query("SELECT count(*) FROM resumes"))
    d.close()