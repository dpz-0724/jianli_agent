# -*- coding: utf-8 -*-
"""Job-related candidate evaluation for the delivery workbench.

This module deliberately excludes protected/personal attributes such as age and gender
from screening and ranking. It is designed as recruiter decision support: rule conflicts
are surfaced for human review; they are not final hiring decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import re
from typing import Iterable

try:
    from matcher import SKILL_DICT as _LEGACY_SKILLS
except Exception:  # pragma: no cover - standalone test fallback
    _LEGACY_SKILLS = []

BASE_SKILLS = [
    "java", "python", "c++", "c#", "go", "php", "javascript", "typescript",
    "node", "nodejs", "vue", "react", "sql", "mysql", "oracle", "redis",
    "linux", "docker", "k8s", "kubernetes", "大数据", "算法", "机器学习",
    "深度学习", "ai", "excel", "office", "cad", "solidworks", "plc",
    "销售", "会计", "财务", "行政", "人事", "hr", "运营", "客服", "采购",
    "外贸", "英语", "日语", "平面设计", "文案", "新媒体", "短视频", "直播",
    "电商", "测试", "运维", "数据分析", "项目管理", "产品经理", "物流",
    "电工", "焊工", "护士", "教师", "律师", "医生",
]
SKILL_CATALOG = list(dict.fromkeys([*(str(s).lower() for s in _LEGACY_SKILLS), *BASE_SKILLS]))

EDU_LEVEL = {
    "": 0,
    "不限": 0,
    "初中及以下": 1,
    "中专/中技": 2,
    "中专": 2,
    "中技": 2,
    "高中": 3,
    "大专": 4,
    "专科": 4,
    "本科": 5,
    "硕士": 6,
    "研究生": 6,
    "博士": 7,
}

CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安",
    "重庆", "天津", "长沙", "郑州", "青岛", "东莞", "佛山", "合肥", "厦门", "福州",
    "大连", "济南", "昆明", "宁波", "无锡", "南昌", "南宁", "贵阳", "海口", "兰州",
    "哈尔滨", "长春", "沈阳", "石家庄", "太原", "珠海", "乌鲁木齐", "呼和浩特",
]

REQUIRED_MARKERS = ("必须", "要求", "熟练", "精通", "掌握", "具备", "熟悉", "至少")
PREFERRED_MARKERS = ("优先", "加分", "最好", "更佳", "优先考虑")


def _contains_token(text: str, token: str) -> bool:
    low = (text or "").lower()
    t = token.lower()
    if re.fullmatch(r"[a-z0-9+#.]+", t):
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low))
    return t in low


def _split_terms(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,，、;；/|]+", value)
    else:
        parts = [str(v) for v in value]
    return list(dict.fromkeys(p.strip() for p in parts if p and p.strip()))


def _extract_min_education(text: str) -> str:
    patterns = [
        ("博士", r"博士(?:及以上|以上)?"),
        ("硕士", r"(?:硕士|研究生)(?:及以上|以上)?"),
        ("本科", r"本科(?:及以上|以上)?"),
        ("大专", r"(?:大专|专科)(?:及以上|以上)?"),
        ("高中", r"高中(?:及以上|以上)?"),
        ("中专/中技", r"(?:中专|中技)(?:及以上|以上)?"),
    ]
    for edu, pat in patterns:
        if re.search(pat, text or ""):
            return edu
    return ""


def _extract_min_years(text: str) -> int:
    text = text or ""
    matches = []
    for pat in (
        r"(\d{1,2})\s*年\s*(?:以上|及以上|起)",
        r"至少\s*(\d{1,2})\s*年",
        r"(\d{1,2})\s*[-—~至到]\s*\d{1,2}\s*年",
    ):
        for m in re.finditer(pat, text):
            matches.append(int(m.group(1)))
    return max(matches) if matches else 0


def _candidate_years(exp: str) -> int | None:
    text = (exp or "").strip()
    if not text:
        return None
    if any(k in text for k in ("应届", "在校", "无经验", "一年以内")):
        return 0
    m = re.search(r"(\d{1,2})\s*[-—~至到]\s*(\d{1,2})\s*年", text)
    if m:
        return int(m.group(2))
    m = re.search(r"(\d{1,2})\s*年", text)
    if m:
        return int(m.group(1))
    if "1-3年" in text:
        return 3
    if "3-5年" in text:
        return 5
    if "5-10年" in text:
        return 10
    if "10年以上" in text:
        return 10
    return None


def _candidate_edu_level(text: str) -> int | None:
    t = text or ""
    if not t:
        return None
    found = [level for name, level in EDU_LEVEL.items() if name and name in t]
    return max(found) if found else None


def _extract_locations(text: str) -> list[str]:
    return [c for c in CITIES if c in (text or "")]


def _extract_skills_by_context(jd: str) -> tuple[list[str], list[str]]:
    required, preferred = [], []
    sentences = [s.strip() for s in re.split(r"[。；;\n]+", jd or "") if s.strip()]
    for sentence in sentences:
        mentioned = [s for s in SKILL_CATALOG if _contains_token(sentence, s)]
        if not mentioned:
            continue
        if any(m in sentence for m in PREFERRED_MARKERS):
            preferred.extend(mentioned)
        elif any(m in sentence for m in REQUIRED_MARKERS):
            required.extend(mentioned)
        else:
            preferred.extend(mentioned)
    return list(dict.fromkeys(required)), list(dict.fromkeys(preferred))


@dataclass(frozen=True)
class RequirementProfile:
    keyword: str
    required_skills: tuple[str, ...]
    preferred_skills: tuple[str, ...]
    min_education: str
    min_experience_years: int
    locations: tuple[str, ...]
    title_terms: tuple[str, ...]

    @classmethod
    def from_inputs(
        cls,
        keyword: str = "",
        jd: str = "",
        min_education: str = "",
        min_experience_years: int | str = 0,
        locations: str | Iterable[str] | None = None,
    ) -> "RequirementProfile":
        manual = _split_terms(keyword)
        req, pref = _extract_skills_by_context(jd)
        for term in manual:
            if term not in req:
                req.append(term)
            if term in pref:
                pref.remove(term)

        parsed_edu = _extract_min_education(jd)
        edu = (min_education or "").strip()
        if not edu or edu == "不限":
            edu = parsed_edu

        try:
            years = int(min_experience_years or 0)
        except (TypeError, ValueError):
            years = 0
        years = max(years, _extract_min_years(jd))

        locs = _split_terms(locations) or _extract_locations(jd)
        title_terms = tuple(manual[:6])
        return cls(
            keyword=(keyword or "").strip(),
            required_skills=tuple(dict.fromkeys(req)),
            preferred_skills=tuple(dict.fromkeys(pref)),
            min_education=edu,
            min_experience_years=years,
            locations=tuple(dict.fromkeys(locs)),
            title_terms=title_terms,
        )

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CandidateAssessment:
    eligibility: str
    fit_score: float
    reasons: tuple[str, ...]
    matched_required: tuple[str, ...]
    missing_required: tuple[str, ...]
    matched_preferred: tuple[str, ...]
    evidence: dict

    def as_dict(self) -> dict:
        return asdict(self)


def sanitize_candidate(candidate: dict) -> dict:
    """Keep only fields needed for recruiting workflow; drop sensitive/protected extras."""
    allowed = (
        "platform_uid", "name", "title", "location", "education", "experience",
        "activity", "skills", "text", "source",
    )
    return {k: candidate.get(k, "") for k in allowed}


def candidate_fingerprint(candidate: dict) -> str:
    uid = str(candidate.get("platform_uid") or "").strip()
    if uid:
        return "zhilian:" + uid
    pieces = [
        candidate.get("name", ""), candidate.get("title", ""), candidate.get("location", ""),
        candidate.get("education", ""), candidate.get("experience", ""),
        (candidate.get("text", "") or "")[:800],
    ]
    norm = "|".join(re.sub(r"\s+", " ", str(p)).strip().lower() for p in pieces)
    return "fp:" + hashlib.sha256(norm.encode("utf-8", "ignore")).hexdigest()[:32]


def assess_candidate(candidate: dict, profile: RequirementProfile) -> CandidateAssessment:
    c = sanitize_candidate(candidate)
    text = " ".join(str(c.get(k, "") or "") for k in ("title", "skills", "text", "education", "experience"))

    matched_req = [s for s in profile.required_skills if _contains_token(text, s)]
    missing_req = [s for s in profile.required_skills if s not in matched_req]
    matched_pref = [s for s in profile.preferred_skills if _contains_token(text, s)]

    conflicts: list[str] = []
    review: list[str] = []
    reasons: list[str] = []

    if profile.min_education:
        required_level = EDU_LEVEL.get(profile.min_education, 0)
        cand_level = _candidate_edu_level(str(c.get("education", "")))
        if cand_level is None:
            review.append("学历信息缺失")
        elif cand_level < required_level:
            conflicts.append(f"学历低于岗位要求（要求{profile.min_education}）")
        else:
            reasons.append("学历满足要求")

    if profile.min_experience_years > 0:
        years = _candidate_years(str(c.get("experience", "")))
        if years is None:
            review.append("经验年限无法确认")
        elif years < profile.min_experience_years:
            conflicts.append(f"经验低于岗位要求（要求≥{profile.min_experience_years}年）")
        else:
            reasons.append("经验满足要求")

    if profile.required_skills:
        coverage = len(matched_req) / len(profile.required_skills)
        if missing_req:
            review.append("关键能力需人工核验：" + "、".join(missing_req[:6]))
        if matched_req:
            reasons.append("命中关键能力：" + "、".join(matched_req[:6]))
    else:
        coverage = None

    if profile.locations:
        loc = str(c.get("location", "") or "")
        if not loc:
            review.append("工作地点信息缺失")
            location_match = None
        else:
            location_match = any(x in loc or loc in x for x in profile.locations)
            if location_match:
                reasons.append("工作地点匹配")
            else:
                review.append("工作地点需确认")
    else:
        location_match = None

    title = str(c.get("title", "") or "")
    title_hits = [t for t in profile.title_terms if _contains_token(title, t)]

    # Weighted only on applicable, job-related signals. No age/gender are referenced here.
    weighted: list[tuple[float, float]] = []
    if coverage is not None:
        weighted.append((coverage, 0.55))
    if profile.preferred_skills:
        weighted.append((len(matched_pref) / len(profile.preferred_skills), 0.20))
    if profile.title_terms:
        weighted.append((len(title_hits) / len(profile.title_terms), 0.15))
    if location_match is not None:
        weighted.append((1.0 if location_match else 0.0, 0.10))

    if weighted:
        num = sum(v * w for v, w in weighted)
        den = sum(w for _, w in weighted)
        score = round(100 * num / den, 1)
    else:
        score = 50.0

    if conflicts:
        eligibility = "CONFLICT"
        reasons.extend(conflicts)
    elif review:
        eligibility = "REVIEW"
        reasons.extend(review)
    else:
        eligibility = "PASS"
        reasons.append("未发现规则冲突")

    evidence = {
        "title_hits": title_hits,
        "candidate_location": c.get("location", ""),
        "candidate_education": c.get("education", ""),
        "candidate_experience": c.get("experience", ""),
    }
    return CandidateAssessment(
        eligibility=eligibility,
        fit_score=score,
        reasons=tuple(dict.fromkeys(reasons)),
        matched_required=tuple(matched_req),
        missing_required=tuple(missing_req),
        matched_preferred=tuple(matched_pref),
        evidence=evidence,
    )


def rank_candidates(candidates: Iterable[dict], profile: RequirementProfile) -> list[tuple[dict, CandidateAssessment]]:
    assessed = [(sanitize_candidate(c), assess_candidate(c, profile)) for c in candidates]
    order = {"PASS": 0, "REVIEW": 1, "CONFLICT": 2}
    assessed.sort(key=lambda x: (order.get(x[1].eligibility, 9), -x[1].fit_score, str(x[0].get("name", ""))))
    return assessed
