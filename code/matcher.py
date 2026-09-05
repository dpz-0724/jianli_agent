# -*- coding: utf-8 -*-
"""候选人匹配与排序引擎。

用途：用户输入「关键词 + 岗位 JD + 企业筛人条件」，
对从智联招聘抓到的候选人逐个打分，按匹配分排序输出候选人池。

打分模型（0~100）：
    关键词匹配  40 分  （用户关键词 + JD 提取的技能/岗位词，在候选人简历文本中的命中率）
    条件符合度  35 分  （学历10 + 经验8 + 地点7 + 年龄5 + 性别5）
    活跃度      25 分  （在线25 / 刚刚活跃20 / 今日15 / 本周10 / 本月5）
"""
import re

# 技能 / 岗位 / 学历 词典（JD 关键词提取用，可按需扩充）
SKILL_DICT = [
    # 技术
    "java", "python", "c++", "c#", "c语言", "go", "php", "javascript", "typescript",
    "node", "nodejs", "vue", "react", "html", "css", "小程序", "安卓", "android",
    "ios", "sql", "mysql", "oracle", "redis", "linux", "docker", "k8s", "大数据",
    "爬虫", "算法", "机器学习", "深度学习", "ai", "office", "excel", "word", "ppt",
    "photoshop", "ps", "pr", "ae", "cad", "solidworks", "plc",
    # 职能 / 岗位
    "销售", "会计", "出纳", "财务", "行政", "人事", "hr", "运营", "客服", "采购",
    "仓管", "质检", "跟单", "外贸", "英语", "日语", "平面设计", "平面", "文案",
    "新媒体", "短视频", "直播", "电商", "美工", "测试", "运维", "数据分析",
    "项目管理", "产品经理", "采购", "物流", "司机", "厨师", "电工", "焊工",
    "普工", "技工", "保安", "保洁", "服务员", "店长", "导购", "美容", "护士",
    "教师", "家教", "律师", "医生", "前台",
    # 学历 / 经验 / 证书
    "本科", "大专", "硕士", "博士", "全日制", "中专", "高中", "驾驶证", "会计证",
    "教师资格证", "电工证", "焊工证",
]

ACTIVITY_SCORE = {"在线": 25, "刚刚活跃": 20, "今日活跃": 15, "本周活跃": 10, "本月活跃": 5,
                  "30天活跃": 4, "3月活跃": 3, "半年活跃": 2, "": 0}

# 学历等级（排序/筛选比较用，越大越高）
EDU_LEVEL = {"初中及以下": 1, "中专/中技": 2, "高中": 3, "大专": 5, "本科": 8,
             "硕士": 10, "博士": 12, "全日制": 0, "不限": -1}


def _has_word(low, w):
    """单词级匹配：纯英文/数字词用边界，中文词用子串（避免 'pr' 误中 'spring'）。"""
    if re.fullmatch(r"[a-z0-9+#.]+", w):
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low))
    return w in low


def extract_keywords(jd_text, manual_kws=()):
    """从 JD 文本提取关键词：先并入用户手动关键词，再从词典命中 + 英文缩写。"""
    keywords = list(dict.fromkeys(k for k in manual_kws if k and k.strip()))
    if not jd_text:
        return keywords
    low = jd_text.lower()
    for w in SKILL_DICT:
        if _has_word(low, w) and w.lower() not in [k.lower() for k in keywords]:
            keywords.append(w)
    return keywords


def candidate_text(cand):
    """候选人所有可检索文本（用于关键词命中）。"""
    parts = [cand.get(k, "") for k in ("title", "text", "skills", "brief",
                                       "education", "experience", "school", "company")]
    return " ".join(str(p) for p in parts if p)


def score_candidate(cand, keywords, filters=None):
    """对单个候选人打分，返回 (0~100 浮点, 命中明细 dict)。"""
    filters = filters or {}
    score = 0.0
    detail = {}

    # ---- 1. 关键词匹配 (40) ----
    if keywords:
        text = candidate_text(cand).lower()
        hits = [k for k in keywords if k.lower() in text]
        kw_score = 40.0 * len(hits) / len(keywords)
        detail["关键词命中"] = f"{len(hits)}/{len(keywords)}"
    else:
        kw_score = 20.0  # 无关键词时给基准分
        detail["关键词命中"] = "-"
    score += kw_score

    # ---- 2. 条件符合度 (35) ----
    cond = 0.0
    # 学历 (10)
    if filters.get("education"):
        c_edu = cand.get("education", "")
        if c_edu and any(e in c_edu for e in filters["education"] if e != "不限"):
            cond += 10
    # 经验 (8)
    if filters.get("experience"):
        c_exp = cand.get("experience", "")
        exps = [e for e in filters["experience"] if e != "不限"]
        if c_exp and any(e in c_exp for e in exps):
            cond += 8
    # 地点 (7)
    if filters.get("location"):
        loc = filters["location"].strip()
        if loc and loc in str(cand.get("location", "")):
            cond += 7
    # 年龄 (5)
    amin = filters.get("age_min"); amax = filters.get("age_max")
    if amin and amax:
        try:
            age = int(cand.get("age", 0) or 0)
            if age and int(amin) <= age <= int(amax):
                cond += 5
        except (TypeError, ValueError):
            pass
    # 性别 (5)
    if filters.get("gender") and filters["gender"] != "不限":
        if cand.get("gender") == filters["gender"]:
            cond += 5
    score += cond
    detail["条件符合"] = f"{int(cond)}/35"

    # ---- 3. 活跃度 (25) ----
    act = cand.get("activity", "")
    act_score = ACTIVITY_SCORE.get(act, 0)
    score += act_score
    detail["活跃度"] = f"{act_score}/25"

    return round(score, 1), detail


def rank_candidates(candidates, keywords, filters=None, limit=None):
    """候选池排序：打分 → 按分降序 → 附加 _rank/_score/_detail，缺分并列按活跃度。"""
    scored = []
    for c in candidates:
        s, d = score_candidate(c, keywords, filters)
        c2 = dict(c)
        c2["_score"] = s
        c2["_detail"] = d
        scored.append(c2)
    scored.sort(key=lambda x: (-x["_score"], -ACTIVITY_SCORE.get(x.get("activity", ""), 0)))
    for i, c in enumerate(scored, 1):
        c["_rank"] = i
    return scored[:limit] if limit else scored


if __name__ == "__main__":
    jd = "招聘 Java 后端开发，要求本科及以上，3年以上经验，熟悉 MySQL、Redis、Spring Boot，工作地北京"
    kws = extract_keywords(jd)
    print("JD 关键词:", kws)
    cands = [
        {"name": "张三", "title": "Java开发工程师", "location": "北京", "education": "本科",
         "experience": "5年", "age": 28, "activity": "在线", "text": "熟悉 Java、MySQL、Redis"},
        {"name": "李四", "title": "销售经理", "location": "上海", "education": "大专",
         "experience": "2年", "age": 30, "activity": "本周活跃", "text": "销售管理"},
        {"name": "王五", "title": "Java开发", "location": "北京", "education": "硕士",
         "experience": "4年", "age": 26, "activity": "刚刚活跃", "text": "Java Spring Redis MySQL"},
    ]
    filt = {"education": ["本科", "硕士"], "experience": ["3-5年"], "location": "北京",
            "age_min": 22, "age_max": 40, "gender": "不限"}
    for c in rank_candidates(cands, kws, filt):
        print(c["_rank"], c["name"], c["_score"], c["_detail"])