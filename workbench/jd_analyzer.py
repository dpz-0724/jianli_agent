# -*- coding: utf-8 -*-
"""AI 岗位分析器：把客户给的 JD / 口语需求，结构化成一个「要招什么样的人」。

在 evaluation.build_requirement_profile（技能/学历/经验/地点）之上，补充招聘最关心的：
  - 证书要求（驾驶证、教师资格证、CPA、英语六级…）
  - 年龄区间（"35岁以下"/"20-35岁"）
  - 薪资区间（公司给出的 offer 带宽，用于参考候选人期望薪资）
  - 岗位名称推断
  - 自动生成智联搜索词（解决"搜索词质量不高"）

注意：年龄、性别等只作为客户显式要求的筛选偏好采集与展示，
默认不进入硬性匹配，避免误杀；是否启用由客户在界面勾选。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .evaluation import (
    _contains_token,
    _extract_min_education,
    _extract_min_years,
    _extract_locations,
    _extract_skills_by_context,
    _split_terms,
)

# ---- 证书词典（招聘高频）----
CERT_KEYWORDS = [
    "驾驶证", "驾照", "c1", "c2", "普通话", "教师资格证", "会计证", "初级会计", "中级会计",
    "cpa", "注册会计师", "acca", "英语四级", "英语六级", "cet-4", "cet-6", "四级", "六级",
    "专四", "专八", "计算机二级", "计算机等级", "护士证", "执业药师", "电工证", "焊工证",
    "叉车证", "健康证", "育婴师", "保育员", "一级建造师", "一建", "二级建造师", "二建",
    "造价工程师", "造价师", "消防工程师", "监理工程师", "安全工程师", "法律职业资格", "法考",
    "证券从业", "基金从业", "银行从业", "期货从业", "frm", "cfa", "pmp", "软考",
    "人力资源管理师", "劳动关系协调员", "导游证", "营养师", "心理咨询师", "社工证",
]

AGE_PATTERNS = [
    r"(\d{2})\s*岁\s*(?:以下|以内|之内)",
    r"年龄\s*(\d{2})\s*[-—~至到]\s*(\d{2})\s*岁",
    r"(\d{2})\s*[-—~至到]\s*(\d{2})\s*岁",
    r"不超过\s*(\d{2})\s*岁",
    r"(\d{2})\s*岁以下",
]

SALARY_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*[-—~至到]\s*(\d+(?:\.\d+)?)\s*[kK]",
    r"(\d+(?:\.\d+)?)\s*[-—~至到]\s*(\d+(?:\.\d+)?)\s*万",
    r"(\d{4,5})\s*[-—~至到]\s*(\d{4,5})\s*元",
]

TITLE_HINTS = ["岗位", "职位", "招聘", "诚聘", "职位名称", "岗位名称"]


@dataclass(frozen=True)
class JobAnalysis:
    """AI 分析出的「要招什么样的人」。"""
    job_title: str = ""
    search_query: str = ""
    required_skills: tuple[str, ...] = ()
    preferred_skills: tuple[str, ...] = ()
    min_education: str = ""
    min_experience_years: int = 0
    locations: tuple[str, ...] = ()
    certificates: tuple[str, ...] = ()
    age_min: int = 0
    age_max: int = 0
    salary_range: str = ""
    summary: str = ""
    evidence: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self):
        return {
            "job_title": self.job_title,
            "search_query": self.search_query,
            "required_skills": list(self.required_skills),
            "preferred_skills": list(self.preferred_skills),
            "min_education": self.min_education,
            "min_experience_years": self.min_experience_years,
            "locations": list(self.locations),
            "certificates": list(self.certificates),
            "age_min": self.age_min,
            "age_max": self.age_max,
            "salary_range": self.salary_range,
            "summary": self.summary,
            "evidence": self.evidence,
        }


def _extract_certificates(text: str) -> tuple[list[str], list[str]]:
    found, evidence = [], []
    low = (text or "").lower()
    for cert in CERT_KEYWORDS:
        if _contains_token(low, cert) and cert not in found:
            found.append(cert)
            for clause in re.split(r"[。；;\n]", text or ""):
                if _contains_token(clause, cert):
                    evidence.append(clause.strip()[:60])
                    break
    # 规范同义词并去重
    dedup = []
    for c in found:
        norm = _normalize_cert(c)
        if norm not in dedup:
            dedup.append(norm)
    # "驾驶证" 与 "驾驶证(C1)" 只保留更具体的
    if any("驾驶证(" in d for d in dedup):
        dedup = [d for d in dedup if d != "驾驶证"]
    return dedup, evidence


def _extract_age_range(text: str) -> tuple[int, int, list[str]]:
    t = text or ""
    m = re.search(AGE_PATTERNS[1], t) or re.search(AGE_PATTERNS[2], t)
    if m:
        return int(m.group(1)), int(m.group(2)), [m.group(0)]
    m = re.search(AGE_PATTERNS[0], t) or re.search(AGE_PATTERNS[3], t) or re.search(AGE_PATTERNS[4], t)
    if m:
        return 0, int(m.group(1)), [m.group(0)]
    return 0, 0, []


def _extract_salary(text: str) -> tuple[str, list[str]]:
    t = text or ""
    m = re.search(SALARY_PATTERNS[0], t)
    if m:
        return f"{m.group(1)}-{m.group(2)}K", [m.group(0)]
    m = re.search(SALARY_PATTERNS[1], t)
    if m:
        return f"{m.group(1)}-{m.group(2)}万", [m.group(0)]
    m = re.search(SALARY_PATTERNS[2], t)
    if m:
        return f"{m.group(1)}-{m.group(2)}元", [m.group(0)]
    return "", []


def _infer_job_title(text: str, keyword: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # 长词优先匹配，避免 "岗位名称：X" 被 "岗位" 吃掉
        m = re.match(r"^(?:岗位名称|职位名称|招聘岗位|招聘职位|岗位|职位|招聘|诚聘)[：:：\s]*(.{2,20})$", line)
        if m:
            title = re.sub(r"^[：:：\s]+|[：:：\s]+$", "", m.group(1)).strip()
            if title and not any(h in title for h in ("职责", "要求", "任职")):
                return title
        if len(line) <= 20 and any(h in line for h in TITLE_HINTS):
            cleaned = re.sub(r"(岗位名称|职位名称|岗位|职位|招聘|诚聘|名称)[：:：]?", "", line).strip()
            cleaned = re.sub(r"(岗位|职位|招聘|诚聘)$", "", cleaned).strip()
            if 2 <= len(cleaned) <= 20 and "：" not in cleaned and ":" not in cleaned:
                return cleaned
    return (keyword or "").strip()


_CERT_NORM = {
    "c1": "驾驶证(C1)", "c2": "驾驶证(C2)", "驾照": "驾驶证",
    "四级": "英语四级", "六级": "英语六级", "初级会计": "会计证(初级)", "中级会计": "会计证(中级)",
}


def _normalize_cert(cert: str) -> str:
    return _CERT_NORM.get(cert, cert)


def _build_search_query(job_title: str, keyword: str, required: Iterable[str]) -> str:
    """生成智联搜索框关键词：优先岗位名，其次核心技能。"""
    parts = []
    if keyword:
        parts.append(keyword.strip())
    elif job_title:
        parts.append(job_title.strip())
    core = [s for s in required if s and len(s) >= 2][:1]
    if core and core[0].lower() not in " ".join(parts).lower():
        parts.append(core[0])
    return " ".join(parts).strip() or "销售"


def analyze_job(text: str, keyword: str = "") -> JobAnalysis:
    jd = text or ""
    keyword = keyword or ""
    required, preferred, skill_evidence = _extract_skills_by_context(jd)
    for term in _split_terms(keyword):
        if term not in required:
            required.append(term)
        if term in preferred:
            preferred.remove(term)

    min_edu, edu_ev = _extract_min_education(jd)
    min_years, exp_ev = _extract_min_years(jd)
    locations, loc_ev = _extract_locations(jd)
    certificates, cert_ev = _extract_certificates(jd)
    age_min, age_max, age_ev = _extract_age_range(jd)
    salary, sal_ev = _extract_salary(jd)
    job_title = _infer_job_title(jd, keyword)
    query = _build_search_query(job_title, keyword, required)

    chunks = []
    if job_title:
        chunks.append(f"岗位：{job_title}")
    if query:
        chunks.append(f"搜索词：{query}")
    if required:
        chunks.append("必备能力：" + "、".join(required[:8]))
    if preferred:
        chunks.append("加分能力：" + "、".join(preferred[:8]))
    if min_edu:
        chunks.append(f"学历≥{min_edu}")
    if min_years:
        chunks.append(f"经验≥{min_years}年")
    if locations:
        chunks.append("地点：" + "/".join(locations))
    if certificates:
        chunks.append("证书：" + "、".join(certificates))
    if age_max:
        chunks.append(f"年龄≤{age_max}岁" if not age_min else f"年龄{age_min}-{age_max}岁")
    if salary:
        chunks.append(f"薪资：{salary}")
    summary = "；".join(chunks) or "未识别到明确条件，请人工补充。"

    evidence = dict(skill_evidence)
    evidence.update({
        "education": edu_ev, "experience": exp_ev, "locations": loc_ev,
        "certificates": cert_ev, "age": age_ev, "salary": sal_ev,
    })

    return JobAnalysis(
        job_title=job_title, search_query=query,
        required_skills=tuple(dict.fromkeys(required)),
        preferred_skills=tuple(dict.fromkeys(preferred)),
        min_education=min_edu, min_experience_years=min_years,
        locations=tuple(dict.fromkeys(locations)),
        certificates=tuple(dict.fromkeys(certificates)),
        age_min=age_min, age_max=age_max, salary_range=salary,
        summary=summary, evidence=evidence,
    )


if __name__ == "__main__":
    demo = """岗位名称：销售经理
1. 负责华东区大客户销售，完成业绩指标；
2. 大专及以上学历，1-3年销售经验；
3. 35岁以下，持C1驾照，有英语四级证书优先；
4. 薪资8-12K，工作地点上海、杭州。"""
    import json
    print(json.dumps(analyze_job(demo).as_dict(), ensure_ascii=False, indent=2))