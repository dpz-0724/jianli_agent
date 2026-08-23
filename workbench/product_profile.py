# -*- coding: utf-8 -*-
"""Recruiter-confirmed requirement profile semantics.

The generic JD parser proposes requirements. This module applies the product rule that
structured recruiter input is authoritative, including an explicit "不限" or zero-year
override. Platform search keywords are recall terms and are not silently promoted to
hard candidate requirements.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from .evaluation import build_requirement_profile
from .models import RequirementProfile


def _split_terms(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,，、;；/|]+", value)
    else:
        parts = [str(item) for item in value]
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        term = part.strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            result.append(term)
    return result


def build_recruiter_confirmed_profile(
    *,
    keyword: str = "",
    jd: str = "",
    min_education: str = "不限",
    min_experience_years: int | str = 0,
    locations: str | Iterable[str] | None = None,
    required_skills: str | Iterable[str] | None = None,
    preferred_skills: str | Iterable[str] | None = None,
) -> RequirementProfile:
    """Build the job profile that the recruiter actually confirmed.

    Structured education and experience values always override JD suggestions. An empty
    skills field means "use the parser proposal"; a populated field replaces the parser
    proposal for that category. Search keywords remain search/title terms only.
    """

    parsed = build_requirement_profile(keyword="", jd=jd)

    education = (min_education or "").strip()
    confirmed_education = "" if education in {"", "不限"} else education
    try:
        confirmed_years = max(0, int(min_experience_years or 0))
    except (TypeError, ValueError):
        confirmed_years = 0

    explicit_locations = _split_terms(locations)
    confirmed_locations = tuple(explicit_locations or parsed.locations)

    explicit_required = _split_terms(required_skills)
    explicit_preferred = _split_terms(preferred_skills)
    required = tuple(explicit_required or parsed.required_skills)
    preferred_source = explicit_preferred or list(parsed.preferred_skills)
    required_keys = {skill.lower() for skill in required}
    preferred = tuple(skill for skill in preferred_source if skill.lower() not in required_keys)

    search_terms = tuple(_split_terms(keyword)[:12])
    evidence = dict(parsed.source_evidence)
    evidence["education:confirmed"] = ["招聘人员结构化确认：不限" if not confirmed_education else confirmed_education]
    evidence["experience:confirmed"] = [f"招聘人员结构化确认：{confirmed_years}年"]
    if explicit_locations:
        evidence["locations:confirmed"] = list(explicit_locations)
    for skill in explicit_required:
        evidence.setdefault(f"skill:{skill}", []).append("招聘人员结构化确认：必须能力")
    for skill in explicit_preferred:
        evidence.setdefault(f"skill:{skill}", []).append("招聘人员结构化确认：加分能力")
    if search_terms:
        evidence["platform_search_terms"] = list(search_terms)

    return replace(
        parsed,
        keyword=(keyword or "").strip(),
        required_skills=required,
        preferred_skills=preferred,
        min_education=confirmed_education,
        min_experience_years=confirmed_years,
        locations=confirmed_locations,
        title_terms=search_terms,
        source_evidence=evidence,
    )


__all__ = ["build_recruiter_confirmed_profile"]
