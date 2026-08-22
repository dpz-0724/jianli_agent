# -*- coding: utf-8 -*-
"""Explainable, job-related candidate assessment.

The module deliberately excludes age, gender and other non-job-related personal
attributes from screening and ranking. Missing profile data is routed to REVIEW;
only explicit evidence can produce a hard CONFLICT.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from .models import AssessmentStatus, CandidateAssessment, RequirementProfile

ENGINE_VERSION = "assessment-v1.1"
PARSER_VERSION = "rules-v1.1"

BASE_SKILLS = [
    "java", "python", "c++", "c#", "go", "golang", "php", "javascript", "typescript",
    "node", "nodejs", "vue", "react", "angular", "spring", "spring boot", "sql", "mysql",
    "postgresql", "oracle", "redis", "linux", "docker", "k8s", "kubernetes", "微服务",
    "大数据", "算法", "机器学习", "深度学习", "ai", "llm", "rag", "office", "excel",
    "word", "ppt", "photoshop", "cad", "solidworks", "plc", "销售", "会计", "财务",
    "行政", "人事", "hr", "招聘", "运营", "客服", "采购", "供应链", "仓储", "外贸",
    "英语", "日语", "平面设计", "文案", "新媒体", "短视频", "直播", "电商", "测试",
    "自动化测试", "运维", "数据分析", "项目管理", "产品经理", "物流", "电工", "焊工",
    "护士", "教师", "律师", "医生", "施工", "造价", "投标", "消防", "安全管理",
]
SKILL_CATALOG = tuple(dict.fromkeys(s.lower() for s in BASE_SKILLS))

EDU_LEVEL = {
    "": 0,
    "不限": 0,
    "初中及以下": 1,
    "初中": 1,
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

CITIES = (
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安",
    "重庆", "天津", "长沙", "郑州", "青岛", "东莞", "佛山", "合肥", "厦门", "福州",
    "大连", "济南", "昆明", "宁波", "无锡", "南昌", "南宁", "贵阳", "海口", "兰州",
    "哈尔滨", "长春", "沈阳", "石家庄", "太原", "珠海", "乌鲁木齐", "呼和浩特",
)

REQUIRED_MARKERS = ("必须", "任职要求", "要求", "熟练", "精通", "掌握", "具备", "熟悉", "至少")
PREFERRED_MARKERS = ("优先", "加分", "最好", "更佳", "优先考虑")


@dataclass(frozen=True)
class ExperienceRange:
    minimum: int
    maximum: int | None
    exact: bool
    raw: str


def _contains_token(text: str, token: str) -> bool:
    low = (text or "").lower()
    term = token.lower().strip()
    if not term:
        return False
    if re.fullmatch(r"[a-z0-9+#. ]+", term):
        escaped = re.escape(term).replace(r"\ ", r"\s+")
        return bool(re.search(r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])", low))
    return term in low


def _split_terms(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = re.split(r"[\s,，、;；/|]+", value)
    else:
        raw = [str(v) for v in value]
    return list(dict.fromkeys(v.strip().lower() for v in raw if v and v.strip()))


def _clauses(text: str) -> list[str]:
    """Split enough to separate required and preferred phrases in one sentence."""
    parts = re.split(r"[。；;\n]+", text or "")
    result: list[str] = []
    for part in parts:
        result.extend(p.strip() for p in re.split(r"[，,](?=[^，,]{2,})", part) if p.strip())
    return result


def _extract_min_education(text: str) -> tuple[str, list[str]]:
    patterns = [
        ("博士", r"博士(?:及以上|以上)?"),
        ("硕士", r"(?:硕士|研究生)(?:及以上|以上)?"),
        ("本科", r"本科(?:及以上|以上)?"),
        ("大专", r"(?:大专|专科)(?:及以上|以上)?"),
        ("高中", r"高中(?:及以上|以上)?"),
        ("中专/中技", r"(?:中专|中技)(?:及以上|以上)?"),
    ]
    for edu, pattern in patterns:
        matches = [m.group(0) for m in re.finditer(pattern, text or "")]
        if matches:
            return edu, matches
    return "", []


def _extract_min_years(text: str) -> tuple[int, list[str]]:
    evidence: list[tuple[int, str]] = []
    patterns = (
        r"(\d{1,2})\s*年\s*(?:以上|及以上|起)",
        r"至少\s*(\d{1,2})\s*年",
        r"(\d{1,2})\s*[-—~至到]\s*\d{1,2}\s*年",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text or ""):
            evidence.append((int(match.group(1)), match.group(0)))
    if not evidence:
        return 0, []
    max_value = max(v for v, _ in evidence)
    return max_value, [raw for value, raw in evidence if value == max_value]


def _extract_locations(text: str) -> tuple[list[str], list[str]]:
    found = [city for city in CITIES if city in (text or "")]
    return found, found.copy()


def _extract_skills_by_context(jd: str) -> tuple[list[str], list[str], dict[str, list[str]]]:
    required: list[str] = []
    preferred: list[str] = []
    evidence: dict[str, list[str]] = {}
    for clause in _clauses(jd):
        mentioned = [skill for skill in SKILL_CATALOG if _contains_token(clause, skill)]
        if not mentioned:
            continue
        is_preferred = any(marker in clause for marker in PREFERRED_MARKERS)
        is_required = any(marker in clause for marker in REQUIRED_MARKERS)
        target = preferred if is_preferred else required if is_required else preferred
        for skill in mentioned:
            if skill not in target:
                target.append(skill)
            evidence.setdefault(skill, []).append(clause)
    return required, preferred, evidence


def build_requirement_profile(
    *,
    keyword: str = "",
    jd: str = "",
    min_education: str = "",
    min_experience_years: int | str = 0,
    locations: str | Iterable[str] | None = None,
) -> RequirementProfile:
    manual_terms = _split_terms(keyword)
    required, preferred, skill_evidence = _extract_skills_by_context(jd)
    for term in manual_terms:
        if term not in required:
            required.append(term)
        if term in preferred:
            preferred.remove(term)
        skill_evidence.setdefault(term, []).append("手动关键词")

    parsed_education, education_evidence = _extract_min_education(jd)
    confirmed_education = (min_education or "").strip()
    if not confirmed_education or confirmed_education == "不限":
        confirmed_education = parsed_education

    try:
        explicit_years = int(min_experience_years or 0)
    except (TypeError, ValueError):
        explicit_years = 0
    parsed_years, experience_evidence = _extract_min_years(jd)
    confirmed_years = max(explicit_years, parsed_years)

    explicit_locations = _split_terms(locations)
    parsed_locations, location_evidence = _extract_locations(jd)
    confirmed_locations = explicit_locations or parsed_locations

    source_evidence = {
        "education": education_evidence,
        "experience": experience_evidence,
        "locations": location_evidence,
    }
    for skill, clauses in skill_evidence.items():
        source_evidence[f"skill:{skill}"] = clauses

    return RequirementProfile(
        keyword=(keyword or "").strip(),
        required_skills=tuple(dict.fromkeys(required)),
        preferred_skills=tuple(dict.fromkeys(preferred)),
        min_education=confirmed_education,
        min_experience_years=confirmed_years,
        locations=tuple(dict.fromkeys(confirmed_locations)),
        title_terms=tuple(manual_terms[:8]),
        source_evidence=source_evidence,
        parser_version=PARSER_VERSION,
    )


def requirement_summary(profile: RequirementProfile) -> str:
    chunks = []
    if profile.required_skills:
        chunks.append("必须能力：" + "、".join(profile.required_skills[:10]))
    if profile.preferred_skills:
        chunks.append("加分能力：" + "、".join(profile.preferred_skills[:10]))
    if profile.min_education:
        chunks.append("最低学历：" + profile.min_education)
    if profile.min_experience_years:
        chunks.append(f"最低经验：{profile.min_experience_years}年")
    if profile.locations:
        chunks.append("地点：" + " / ".join(profile.locations))
    return "；".join(chunks) or "未识别到明确岗位条件，请人工补充。"


def _education_level(text: str) -> int | None:
    if not text:
        return None
    found = [level for name, level in EDU_LEVEL.items() if name and name in text]
    return max(found) if found else None


def parse_candidate_experience(text: str) -> ExperienceRange | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if any(token in raw for token in ("应届", "在校", "无经验", "一年以内")):
        return ExperienceRange(0, 1, False, raw)
    match = re.search(r"(\d{1,2})\s*[-—~至到]\s*(\d{1,2})\s*年", raw)
    if match:
        return ExperienceRange(int(match.group(1)), int(match.group(2)), False, raw)
    match = re.search(r"(\d{1,2})\s*年\s*(?:以上|及以上)", raw)
    if match:
        return ExperienceRange(int(match.group(1)), None, False, raw)
    match = re.search(r"(\d{1,2})\s*年", raw)
    if match:
        years = int(match.group(1))
        return ExperienceRange(years, years, True, raw)
    mappings = {
        "1-3年": (1, 3),
        "3-5年": (3, 5),
        "5-10年": (5, 10),
        "10年以上": (10, None),
    }
    for label, (minimum, maximum) in mappings.items():
        if label in raw:
            return ExperienceRange(minimum, maximum, False, raw)
    return None


def sanitize_candidate(candidate: dict) -> dict:
    """Keep only fields required for this workflow.

    This intentionally drops age, gender, phone and other sensitive/non-job-related
    attributes from assessment input. Contact data can be handled in a separate,
    permission-controlled workflow later.
    """
    allowed = (
        "platform_uid", "name", "title", "location", "education", "experience",
        "activity", "skills", "text", "source", "source_url", "platform",
    )
    return {key: candidate.get(key, "") for key in allowed}


def candidate_fingerprint(candidate: dict) -> str:
    sanitized = sanitize_candidate(candidate)
    platform = str(sanitized.get("platform") or "zhilian").strip().lower()
    uid = str(sanitized.get("platform_uid") or "").strip()
    if uid:
        return f"{platform}:{uid}"
    pieces = [
        sanitized.get("name", ""),
        sanitized.get("title", ""),
        sanitized.get("location", ""),
        sanitized.get("education", ""),
        sanitized.get("experience", ""),
        (sanitized.get("text", "") or "")[:1200],
    ]
    normalized = "|".join(re.sub(r"\s+", " ", str(piece)).strip().lower() for piece in pieces)
    digest = hashlib.sha256(normalized.encode("utf-8", "ignore")).hexdigest()[:40]
    return f"fallback:{digest}"


def source_snapshot_hash(candidate: dict) -> str:
    payload = json.dumps(sanitize_candidate(candidate), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assess_candidate(candidate: dict, profile: RequirementProfile) -> CandidateAssessment:
    sanitized = sanitize_candidate(candidate)
    searchable_text = " ".join(
        str(sanitized.get(key, "") or "")
        for key in ("title", "skills", "text", "education", "experience")
    )

    matched_required = [skill for skill in profile.required_skills if _contains_token(searchable_text, skill)]
    missing_required = [skill for skill in profile.required_skills if skill not in matched_required]
    matched_preferred = [skill for skill in profile.preferred_skills if _contains_token(searchable_text, skill)]

    conflicts: list[str] = []
    reviews: list[str] = []
    positives: list[str] = []

    if profile.min_education:
        candidate_level = _education_level(str(sanitized.get("education", "")))
        required_level = EDU_LEVEL.get(profile.min_education, 0)
        if candidate_level is None:
            reviews.append("学历信息缺失，需人工核验")
        elif candidate_level < required_level:
            conflicts.append(f"学历低于岗位要求（要求 {profile.min_education}）")
        else:
            positives.append("学历满足要求")

    experience_state = "not_applicable"
    experience_range = None
    if profile.min_experience_years > 0:
        experience_range = parse_candidate_experience(str(sanitized.get("experience", "")))
        if experience_range is None:
            reviews.append("经验年限无法确认")
            experience_state = "unknown"
        elif experience_range.maximum is not None and experience_range.maximum < profile.min_experience_years:
            conflicts.append(f"经验明确低于岗位要求（要求至少 {profile.min_experience_years} 年）")
            experience_state = "conflict"
        elif experience_range.minimum >= profile.min_experience_years:
            positives.append("经验满足要求")
            experience_state = "pass"
        else:
            reviews.append(
                f"经验区间为 {experience_range.raw}，无法确认是否达到 {profile.min_experience_years} 年"
            )
            experience_state = "uncertain"

    if profile.required_skills:
        required_coverage = len(matched_required) / len(profile.required_skills)
        if matched_required:
            positives.append("命中必须能力：" + "、".join(matched_required[:8]))
        if missing_required:
            reviews.append("简历摘要未发现必须能力：" + "、".join(missing_required[:8]))
    else:
        required_coverage = None

    location_match: bool | None = None
    if profile.locations:
        candidate_location = str(sanitized.get("location", "") or "")
        if not candidate_location:
            reviews.append("工作地点信息缺失")
        else:
            location_match = any(
                required in candidate_location or candidate_location in required
                for required in profile.locations
            )
            if location_match:
                positives.append("工作地点匹配")
            else:
                reviews.append(
                    "工作地点需确认（候选人：%s；岗位：%s）"
                    % (candidate_location, " / ".join(profile.locations))
                )

    title = str(sanitized.get("title", "") or "")
    title_hits = [term for term in profile.title_terms if _contains_token(title, term)]

    weighted: list[tuple[float, float]] = []
    if required_coverage is not None:
        weighted.append((required_coverage, 0.60))
    if profile.preferred_skills:
        weighted.append((len(matched_preferred) / len(profile.preferred_skills), 0.20))
    if profile.title_terms:
        weighted.append((len(title_hits) / len(profile.title_terms), 0.15))
    if location_match is not None:
        weighted.append((1.0 if location_match else 0.0, 0.05))

    if weighted:
        numerator = sum(value * weight for value, weight in weighted)
        denominator = sum(weight for _, weight in weighted)
        fit_score = round(100 * numerator / denominator, 1)
    else:
        fit_score = 50.0

    if conflicts:
        status = AssessmentStatus.CONFLICT
        reasons = [*positives, *conflicts, *reviews]
    elif reviews:
        status = AssessmentStatus.REVIEW
        reasons = [*positives, *reviews]
    else:
        status = AssessmentStatus.PASS
        reasons = [*positives, "未发现明确规则冲突"]

    evidence = {
        "title_hits": title_hits,
        "candidate_location": sanitized.get("location", ""),
        "candidate_education": sanitized.get("education", ""),
        "candidate_experience": sanitized.get("experience", ""),
        "experience_state": experience_state,
        "experience_range": (
            {
                "minimum": experience_range.minimum,
                "maximum": experience_range.maximum,
                "exact": experience_range.exact,
                "raw": experience_range.raw,
            }
            if experience_range
            else None
        ),
        "requirement_parser_version": profile.parser_version,
    }

    return CandidateAssessment(
        status=status,
        fit_score=fit_score,
        reasons=tuple(dict.fromkeys(reasons)),
        matched_required=tuple(matched_required),
        missing_required=tuple(missing_required),
        matched_preferred=tuple(matched_preferred),
        evidence=evidence,
        engine_version=ENGINE_VERSION,
    )
