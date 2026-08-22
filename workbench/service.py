# -*- coding: utf-8 -*-
"""Application services coordinating jobs, sourcing and assessment."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .database import WorkbenchDB
from .evaluation import assess_candidate, build_requirement_profile
from .models import AssessmentStatus, RequirementProfile


@dataclass(frozen=True)
class IngestSummary:
    found: int
    new_candidates: int
    new_job_links: int
    pass_count: int
    review_count: int
    conflict_count: int


class RecruitmentService:
    def __init__(self, db: WorkbenchDB):
        self.db = db

    def parse_and_save_job(
        self,
        job_id: int,
        *,
        title: str,
        keyword: str,
        jd: str,
        min_education: str = "",
        min_experience_years: int | str = 0,
        locations: str | Iterable[str] | None = None,
    ) -> RequirementProfile:
        profile = build_requirement_profile(
            keyword=keyword,
            jd=jd,
            min_education=min_education,
            min_experience_years=min_experience_years,
            locations=locations,
        )
        self.db.update_job(job_id, title=title, keyword=keyword, jd=jd, profile=profile)
        return profile

    def load_profile(self, job_id: int) -> RequirementProfile:
        job = self.db.get_job(job_id)
        if not job:
            raise KeyError(f"岗位不存在: {job_id}")
        raw = job.get("requirements_json") or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        if payload:
            payload["required_skills"] = tuple(payload.get("required_skills") or ())
            payload["preferred_skills"] = tuple(payload.get("preferred_skills") or ())
            payload["locations"] = tuple(payload.get("locations") or ())
            payload["title_terms"] = tuple(payload.get("title_terms") or ())
            return RequirementProfile(**payload)
        return build_requirement_profile(keyword=job.get("keyword", ""), jd=job.get("jd", ""))

    def ingest_candidates(
        self,
        *,
        job_id: int,
        run_id: int | None,
        candidates: Iterable[dict[str, Any]],
    ) -> IngestSummary:
        profile = self.load_profile(job_id)
        found = new_candidates = new_job_links = 0
        counts = {
            AssessmentStatus.PASS: 0,
            AssessmentStatus.REVIEW: 0,
            AssessmentStatus.CONFLICT: 0,
        }
        for candidate in candidates:
            found += 1
            candidate_id, created, _ = self.db.upsert_candidate(candidate, run_id=run_id)
            job_candidate_id, linked = self.db.link_candidate_to_job(job_id, candidate_id)
            assessment = assess_candidate(candidate, profile)
            self.db.save_assessment(job_candidate_id, assessment, profile)
            new_candidates += int(created)
            new_job_links += int(linked)
            counts[assessment.status] += 1
        return IngestSummary(
            found=found,
            new_candidates=new_candidates,
            new_job_links=new_job_links,
            pass_count=counts[AssessmentStatus.PASS],
            review_count=counts[AssessmentStatus.REVIEW],
            conflict_count=counts[AssessmentStatus.CONFLICT],
        )

    def reassess_job(self, job_id: int) -> IngestSummary:
        profile = self.load_profile(job_id)
        rows = self.db.list_job_candidates(job_id, limit=100000)
        counts = {
            AssessmentStatus.PASS: 0,
            AssessmentStatus.REVIEW: 0,
            AssessmentStatus.CONFLICT: 0,
        }
        for row in rows:
            candidate = {
                "name": row.get("name", ""),
                "title": row.get("title", ""),
                "location": row.get("location", ""),
                "education": row.get("education", ""),
                "experience": row.get("experience", ""),
                "activity": row.get("activity", ""),
                "skills": row.get("skills", ""),
                "text": row.get("text", ""),
                "source_url": row.get("source_url", ""),
                "platform": "zhilian",
            }
            assessment = assess_candidate(candidate, profile)
            self.db.save_assessment(int(row["job_candidate_id"]), assessment, profile)
            counts[assessment.status] += 1
        return IngestSummary(
            found=len(rows),
            new_candidates=0,
            new_job_links=0,
            pass_count=counts[AssessmentStatus.PASS],
            review_count=counts[AssessmentStatus.REVIEW],
            conflict_count=counts[AssessmentStatus.CONFLICT],
        )
