# -*- coding: utf-8 -*-
"""JD 智能解析：把岗位描述结构化拆成「硬性要求 vs 加分项」，
用于自动带出筛选条件（学历/经验/地点）与技能匹配关键词。"""
import re
from matcher import SKILL_DICT, _has_word

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安",
          "重庆", "天津", "长沙", "郑州", "青岛", "东莞", "佛山", "合肥", "厦门", "福州",
          "大连", "济南", "昆明", "宁波", "无锡", "南昌", "南宁", "贵阳", "海口", "兰州",
          "乌鲁木齐", "哈尔滨", "长春", "沈阳", "石家庄", "太原", "呼和浩特", "珠海"]

# 学历优先级：高到低（"本科及以上"取本科、"本科优先硕士"取硕士）
EDU_PRIORITY = [("博士", r"博士"), ("硕士", r"硕士|研究生"), ("本科", r"本科"),
                ("大专", r"大专|专科"), ("中专/中技", r"中专|中技"), ("高中", r"高中"),
                ("初中及以下", r"初中")]


def extract_education(text):
    """提取学历硬性要求（取最高要求学历）。"""
    for edu, pat in EDU_PRIORITY:
        if re.search(pat, text):
            return edu
    return ""


def years_to_range(n):
    if n <= 0:
        return "在校/应届"
    if n <= 1:
        return "一年以内"
    if n <= 2:
        return "1-3年"
    if n <= 4:
        return "3-5年"
    if n <= 10:
        return "5-10年"
    return "10年以上"


def extract_experience(text):
    """提取经验硬性要求，返回经验段（空=不限）。"""
    m = re.search(r"(\d{1,2})\s*年\s*(?:以上|及以上|起|或以上)", text)
    if m:
        return years_to_range(int(m.group(1)))
    m = re.search(r"(\d{1,2})\s*[-—至到]\s*(\d{1,2})\s*年", text)
    if m:
        return years_to_range(int(m.group(1)))
    if re.search(r"应届|实习生|无经验|经验不限|不限经验", text):
        return "在校/应届" if re.search(r"应届|实习生", text) else ""
    m = re.search(r"(\d{1,2})\s*年(?!\s*(?:以上|及以上|起|轻|龄))", text)
    if m:
        return years_to_range(int(m.group(1)))
    return ""


def extract_locations(text):
    """提取工作地点（所有出现的城市）。"""
    return [c for c in CITIES if c in text]


EDU_WORDS = ["本科", "大专", "硕士", "博士", "全日制", "中专", "中技", "高中", "初中"]


def extract_skills(text):
    """提取技能关键词（加分项来源，排除学历词）。"""
    low = text.lower()
    hits = []
    for w in SKILL_DICT:
        if w in EDU_WORDS:
            continue
        if _has_word(low, w) and w not in hits:
            hits.append(w)
    return hits


def extract_preferred_notes(text):
    """提取「优先/加分」修饰的片段。"""
    notes = []
    for m in re.finditer(r"([^，。；;、\n]{2,14}?)\s*(?:优先考虑|优先|加分|者优先)", text):
        seg = (m.group(1) or "").strip(" ，。；;、有具备熟悉")
        if seg:
            notes.append(seg)
    return notes


def parse_jd(jd_text):
    """主入口：返回结构化解析结果。"""
    text = jd_text or ""
    hard = {
        "education": extract_education(text),
        "experience": extract_experience(text),
        "location": extract_locations(text),
    }
    preferred = {
        "skills": extract_skills(text),
        "notes": extract_preferred_notes(text),
    }
    return {"hard": hard, "preferred": preferred}


def summarize(parsed):
    """生成一行中文摘要，用于界面展示。"""
    h, p = parsed["hard"], parsed["preferred"]
    parts = []
    if h["education"]:
        parts.append("学历:" + h["education"])
    if h["experience"]:
        parts.append("经验:" + h["experience"])
    if h["location"]:
        parts.append("地点:" + "/".join(h["location"]))
    hard_s = "  ".join(parts) or "未识别"
    pref_s = "、".join(p["skills"][:8]) or "无"
    notes_s = "；".join(p["notes"]) or "无"
    return f"[硬性] {hard_s}   [加分] {pref_s}   [优先项] {notes_s}"


if __name__ == "__main__":
    samples = [
        "招聘高级Java后端开发，本科及以上学历，3年以上经验，熟悉Spring Boot、MySQL、Redis，有微服务经验者优先，工作地北京朝阳",
        "招聘销售代表，大专学历，经验不限，有地推经验优先，工作地点上海、广州",
        "急聘会计，本科以上，5-10年总账经验，精通Excel、金蝶，持有会计证优先，深圳",
    ]
    for s in samples:
        p = parse_jd(s)
        print("JD:", s[:40], "...")
        print("  硬性:", p["hard"])
        print("  加分:", p["preferred"])
        print("  摘要:", summarize(p))
        print()