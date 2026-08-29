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
    # 销售/业务细分（提升销售岗区分度：只命中"销售"≠命中"大客户销售"）
    "大客户销售", "大客户", "ka", "渠道销售", "渠道拓展", "电话销售", "电销",
    "网络销售", "网销", "门店销售", "区域销售", "直销", "分销", "会销", "招商",
    "销售管理", "客户开发", "商务拓展", "bd", "面销", "陌拜", "地推", "销售代表",
    "客户经理", "商务谈判", "客户关系", "客情维护", "招投标", "政府客户", "企业客户",
    "tob", "toc", "b端", "c端", "制造业", "汽车", "医药", "医疗器械", "快消", "房地产",
    # 运营/职能细分
    "用户运营", "内容运营", "活动运营", "私域运营", "门店运营", "跨境电商", "国内电商",
    "财务分析", "成本会计", "总账", "审计", "薪酬", "绩效", "招聘配置",
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
        # 最常见的"X年(相关)经验"写法；负向后瞻避免误吃"1-3年"里的下界
        r"(?<![-—~至到\d])(\d{1,2})\s*年[^，。；;\n]{0,8}?经验",
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


# 证书词典（招聘高频）——作为岗位硬性/优先筛选条件
CERT_KEYWORDS = [
    "驾驶证", "驾照", "c1", "c2", "普通话", "教师资格证", "会计证", "初级会计", "中级会计",
    "cpa", "注册会计师", "acca", "英语四级", "英语六级", "cet-4", "cet-6", "四级", "六级",
    "专四", "专八", "计算机二级", "护士证", "执业药师", "电工证", "焊工证", "叉车证", "健康证",
    "育婴师", "保育员", "一级建造师", "一建", "二级建造师", "二建", "造价工程师", "造价师",
    "消防工程师", "监理工程师", "安全工程师", "法律职业资格", "法考", "证券从业", "基金从业",
    "银行从业", "期货从业", "frm", "cfa", "pmp", "软考", "人力资源管理师", "导游证",
    "营养师", "心理咨询师", "社工证",
]
_CERT_NORM = {
    "c1": "驾驶证(C1)", "c2": "驾驶证(C2)", "驾照": "驾驶证", "四级": "英语四级",
    "六级": "英语六级", "初级会计": "会计证(初级)", "中级会计": "会计证(中级)",
}


def _extract_certificates(text: str) -> tuple[list[str], list[str]]:
    found, evidence = [], []
    low = (text or "").lower()
    for cert in CERT_KEYWORDS:
        if _contains_token(low, cert):
            norm = _CERT_NORM.get(cert, cert)
            if norm not in found:
                found.append(norm)
                for clause in re.split(r"[。；;\n]", text or ""):
                    if _contains_token(clause, cert):
                        evidence.append(clause.strip()[:60])
                        break
    if any("驾驶证(" in d for d in found):
        found = [d for d in found if d != "驾驶证"]
    return found, evidence


def _extract_age_range(text: str) -> tuple[int, int, list[str]]:
    t = text or ""
    m = re.search(r"年龄\s*(\d{2})\s*[-—~至到]\s*(\d{2})\s*岁", t) or re.search(r"(\d{2})\s*[-—~至到]\s*(\d{2})\s*岁", t)
    if m:
        return int(m.group(1)), int(m.group(2)), [m.group(0)]
    m = (re.search(r"(\d{2})\s*岁\s*(?:以下|以内|之内)", t) or re.search(r"不超过\s*(\d{2})\s*岁", t)
         or re.search(r"(\d{2})\s*岁以下", t))
    if m:
        return 0, int(m.group(1)), [m.group(0)]
    return 0, 0, []


def parse_salary_to_k(text: str) -> tuple[int, int]:
    """把 '8-12K' / '8千-1.2万' / '1万-1.5万' / '3万/月' 等解析为 (minK, maxK)。解析不到返回 (0,0)。"""
    t = (text or "").replace(" ", "")
    if not t:
        return 0, 0

    def _to_k(num: float, unit: str) -> int:
        if unit == "万":
            return int(round(num * 10))
        if unit in ("千", "k", "K"):
            return int(round(num))
        # 纯数字：>=1000 视为元/月，转 K；否则视为 K
        return int(round(num / 1000)) if num >= 1000 else int(round(num))

    # X千-Y万  / X万-Y万 / XK-YK / X-YK
    # 第一个数若带小数必须紧跟单位（"1.2万-2万"合法）；否则整数即可。
    # 这样编号列表"3. 15-25K"不会被粘成"3.15-25K"而把下限解析成 3。
    m = re.search(
        r"(?:(\d+\.\d+)(千|万|k|K)|(\d+)(千|万|k|K)?)\s*[-~—至到]\s*(\d+(?:\.\d+)?)(千|万|k|K)", t)
    if m:
        lo = _to_k(float(m.group(1) or m.group(3)), (m.group(2) or m.group(4)) or "")
        hi = _to_k(float(m.group(5)), m.group(6) or "")
        if lo and hi:
            return (min(lo, hi), max(lo, hi))
    # 单个 X万 / X千 / XK
    m = re.search(r"(\d+(?:\.\d+)?)(万|千|k|K)", t)
    if m:
        v = _to_k(float(m.group(1)), m.group(2))
        return (v, v)
    return 0, 0


def _extract_salary_budget(text: str) -> tuple[int, int, list[str]]:
    """从 JD 提取岗位薪资预算（K）。命中 薪资/月薪/待遇 等语境优先。"""
    for clause in re.split(r"[。；;\n]", text or ""):
        if any(k in clause for k in ("薪资", "月薪", "待遇", "工资", "薪酬", "薪")):
            lo, hi = parse_salary_to_k(clause)
            if lo and hi:
                return lo, hi, [clause.strip()[:60]]
    # 兜底：全文任意薪资
    lo, hi = parse_salary_to_k(text or "")
    if lo and hi:
        return lo, hi, []
    return 0, 0, []


def _analyze_stability(full_text: str) -> tuple[int, int]:
    """从完整简历分析稳定性。返回 (平均任期月数, 最长空档月数)。无数据返回 (0,0)。

    简历工作经历里每段带 '(X年Y个月)' 任期；智联还会标注 '两份工作间有N个月空档期'。
    """
    t = full_text or ""
    if not t:
        return 0, 0
    # 任期：(6年1个月) / (6年) / (5个月)
    tenures = []
    for m in re.finditer(r"\((?:(\d+)年)?\s*(?:(\d+)个?月)?\)", t):
        y = int(m.group(1) or 0); mo = int(m.group(2) or 0)
        months = y * 12 + mo
        if 0 < months <= 600:
            tenures.append(months)
    avg_tenure = round(sum(tenures) / len(tenures)) if tenures else 0
    # 空档期
    gaps = [int(x) for x in re.findall(r"(\d+)\s*个?月空档", t)]
    max_gap = max(gaps) if gaps else 0
    return avg_tenure, max_gap


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

    certificates, cert_evidence = _extract_certificates(jd)
    age_min, age_max, age_evidence = _extract_age_range(jd)
    salary_min, salary_max, salary_evidence = _extract_salary_budget(jd)

    source_evidence = {
        "education": education_evidence,
        "experience": experience_evidence,
        "locations": location_evidence,
        "certificates": cert_evidence,
        "age": age_evidence,
        "salary": salary_evidence,
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
        age_min=age_min,
        age_max=age_max,
        certificates=tuple(dict.fromkeys(certificates)),
        salary_min=salary_min,
        salary_max=salary_max,
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

    age / expected_salary / certificates 是招聘方关心的展示与可选筛选字段，
    采集入库并在界面展示；但**不进入硬性匹配打分**——年龄、性别不参与
    assess_candidate 评分，避免误杀，是否按年龄/证书筛选由招聘方显式决定。
    """
    allowed = (
        "platform_uid", "name", "title", "location", "education", "experience",
        "activity", "skills", "text", "source", "source_url", "platform",
        "age", "expected_salary", "certificates", "full_text",
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
    # 完整简历全文优先（若有），技能/经验匹配基于全文，比卡片摘要准得多
    searchable_text = " ".join(
        str(sanitized.get(key, "") or "")
        for key in ("title", "skills", "text", "education", "experience", "full_text")
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

    # 年龄约束（客户在 JD 显式写明时才生效；不参与加权分，作为硬性/复核条件）
    age_state = "not_applicable"
    candidate_age = 0
    if profile.age_max or profile.age_min:
        try:
            candidate_age = int(sanitized.get("age") or 0)
        except (TypeError, ValueError):
            candidate_age = 0
        lo = profile.age_min or 16
        hi = profile.age_max or 65
        if candidate_age <= 0:
            reviews.append("年龄信息缺失，需人工核验")
            age_state = "unknown"
        elif candidate_age > hi:
            conflicts.append(f"年龄 {candidate_age} 岁超出岗位要求（要求 ≤{hi} 岁）")
            age_state = "conflict"
        elif candidate_age < lo:
            conflicts.append(f"年龄 {candidate_age} 岁低于岗位要求（要求 ≥{lo} 岁）")
            age_state = "conflict"
        else:
            positives.append(f"年龄 {candidate_age} 岁符合要求")
            age_state = "pass"

    # 证书约束（招聘方明确要求持证时：简历可确认则加分，未提及则复核）
    matched_certs: list[str] = []
    missing_certs: list[str] = []
    if profile.certificates:
        cand_cert_text = " ".join([
            str(sanitized.get("certificates", "") or ""),
            str(sanitized.get("skills", "") or ""),
            str(sanitized.get("text", "") or ""),
        ]).lower()
        for cert in profile.certificates:
            base = re.sub(r"\(.*?\)", "", cert).strip()
            variants = {cert.lower(), base.lower()}
            if base in ("驾驶证",): variants |= {"驾照", "c1", "c2"}
            if base in ("英语四级",): variants |= {"四级", "cet-4"}
            if base in ("英语六级",): variants |= {"六级", "cet-6"}
            if any(v and v in cand_cert_text for v in variants):
                matched_certs.append(cert)
            else:
                missing_certs.append(cert)
        if matched_certs:
            positives.append("持有证书：" + "、".join(matched_certs))
        # 缺失证书不压状态：搜索卡片阶段无法核验证书，需看完整简历；只在持有时加分

    # 薪资匹配：候选人期望 vs 岗位预算（HR 最高频的淘汰理由）
    salary_state = "not_applicable"
    salary_fit_value: float | None = None
    if profile.salary_max or profile.salary_min:
        cand_lo, cand_hi = parse_salary_to_k(str(sanitized.get("expected_salary", "") or ""))
        budget_hi = profile.salary_max or profile.salary_min
        budget_lo = profile.salary_min or 0
        if cand_lo == 0 and cand_hi == 0:
            salary_state = "unknown"  # 期望薪资未知，不扣分
        else:
            # 用期望区间中位数作为真实期望，比下限更准（期望12-20K的人不会因下限12就算"在预算内"）
            cand_expect = round((cand_lo + cand_hi) / 2) if cand_hi else cand_lo
            if budget_hi and cand_expect > budget_hi * 1.3:
                reviews.append(f"期望薪资 {sanitized.get('expected_salary')} 明显高于岗位预算（{profile.salary_min}-{profile.salary_max}K）")
                salary_state = "way_over"; salary_fit_value = 0.0
            elif budget_hi and cand_expect > budget_hi:
                reviews.append(f"期望薪资 {sanitized.get('expected_salary')} 高于岗位预算（{profile.salary_min}-{profile.salary_max}K）")
                salary_state = "over"; salary_fit_value = 0.4
            elif budget_lo and cand_hi and cand_hi < budget_lo:
                positives.append(f"期望薪资 {sanitized.get('expected_salary')} 低于预算，性价比高")
                salary_state = "below"; salary_fit_value = 1.0
            else:
                positives.append(f"期望薪资 {sanitized.get('expected_salary')} 在预算内")
                salary_state = "fit"; salary_fit_value = 1.0

    # 稳定性信号（仅在有完整简历时可得，卡片上没有）：空档期 / 平均任期
    avg_tenure_m, max_gap_m = _analyze_stability(str(sanitized.get("full_text", "") or ""))
    if max_gap_m >= 12:
        reviews.append(f"简历存在 {max_gap_m} 个月空档期，稳定性需关注")
    elif avg_tenure_m and avg_tenure_m < 14:
        reviews.append(f"平均任期约 {avg_tenure_m} 个月，跳槽较频繁")
    elif avg_tenure_m and avg_tenure_m >= 36:
        positives.append(f"平均任期约 {avg_tenure_m//12} 年，稳定性好")

    weighted: list[tuple[float, float]] = []
    if required_coverage is not None:
        weighted.append((required_coverage, 0.50))
    if profile.preferred_skills:
        weighted.append((len(matched_preferred) / len(profile.preferred_skills), 0.18))
    if profile.title_terms:
        weighted.append((len(title_hits) / len(profile.title_terms), 0.12))
    if profile.certificates:
        weighted.append((len(matched_certs) / len(profile.certificates), 0.10))
    if location_match is not None:
        weighted.append((1.0 if location_match else 0.0, 0.05))
    if salary_fit_value is not None:
        weighted.append((salary_fit_value, 0.08))

    # 区分度：教育质量与经验丰富度（满足门槛后，越高越好）
    cand_edu_level = _education_level(str(sanitized.get("education", "")))
    if cand_edu_level is not None:
        weighted.append((min(1.0, cand_edu_level / 5.0), 0.10))  # 大专3/本科4/硕士5/博士6
    if experience_range is not None:
        cand_years = experience_range.exact or experience_range.minimum or 0
        weighted.append((min(1.0, cand_years / 8.0), 0.06))

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
        "age_state": age_state,
        "candidate_age": candidate_age,
        "salary_state": salary_state,
        "candidate_salary": str(sanitized.get("expected_salary", "") or ""),
        "avg_tenure_months": avg_tenure_m,
        "max_gap_months": max_gap_m,
        "matched_certificates": matched_certs,
        "missing_certificates": missing_certs,
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
