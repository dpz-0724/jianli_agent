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


class ProfileStatus(str, Enum):
    """A parsed profile is not authoritative until a recruiter confirms it."""

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    NEED_LOGIN = "NEED_LOGIN"
    PAUSED = "PAUSED"
    TAKEOVER = "TAKEOVER"
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
class SearchPlan:
    query: str
    max_pages: int = 5
    max_count: int = 200
    browser_mode: str = "managed"
    visible: bool = True
    sidecar: bool = True

    def normalized(self) -> "SearchPlan":
        return SearchPlan(
            query=self.query.strip(),
            max_pages=max(1, min(int(self.max_pages), 20)),
            max_count=max(1, min(int(self.max_count), 2000)),
            browser_mode=(self.browser_mode or "managed").strip().lower(),
            visible=bool(self.visible),
            sidecar=bool(self.sidecar),
        )


@dataclass(frozen=True)
class RequirementProfile:
    """Confirmed job requirement profile.

    The parser proposes this structure. A recruiter must explicitly confirm it before a
    sourcing task is allowed to start.
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
