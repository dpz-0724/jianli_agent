# -*- coding: utf-8 -*-
"""Core domain models for the local-first recruitment workbench."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    NEED_LOGIN = "NEED_LOGIN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AssessmentStatus(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    CONFLICT = "CONFLICT"


class CandidateStage(str, Enum):
    NEW = "NEW"
    TO_REVIEW = "TO_REVIEW"
    TO_CONTACT = "TO_CONTACT"
    CONTACTED = "CONTACTED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    HIRED = "HIRED"
    REJECTED = "REJECTED"
    TALENT_POOL = "TALENT_POOL"


@dataclass(frozen=True)
class RequirementProfile:
    """Confirmed job requirement profile.

    The parser may propose this structure, but a recruiter remains responsible for
    confirming it before sourcing or assessment is treated as authoritative.
    """

    keyword: str = ""
    required_skills: tuple[str, ...] = ()
    preferred_skills: tuple[str, ...] = ()
    min_education: str = ""
    min_experience_years: int = 0
    locations: tuple[str, ...] = ()
    title_terms: tuple[str, ...] = ()
    source_evidence: dict[str, list[str]] = field(default_factory=dict)
    parser_version: str = "rules-v1"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateAssessment:
    status: AssessmentStatus
    fit_score: float
    reasons: tuple[str, ...]
    matched_required: tuple[str, ...] = ()
    missing_required: tuple[str, ...] = ()
    matched_preferred: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    engine_version: str = "assessment-v1"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class BrowserCommand:
    command: str
    request_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserEvent:
    event: str
    request_id: str
    payload: dict[str, Any] = field(default_factory=dict)
