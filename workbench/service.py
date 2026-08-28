# -*- coding: utf-8 -*-
"""Application services coordinating jobs, sourcing and assessment."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .database import WorkbenchDB
from .evaluation import assess_candidate, build_requirement_profile
from .models import AssessmentStatus, ProfileStatus, RequirementProfile, SearchPlan


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
        """Parse a profile proposal and intentionally return the job to DRAFT state."""
        profile = build_requirement_profile(
            keyword=keyword,
            jd=jd,
            min_education=min_education,
            min_experience_years=min_experience_years,
            locations=locations,
        )
        self.db.update_job(
            job_id,
            title=title,
            keyword=keyword,
            jd=jd,
            profile=profile,
            profile_status=ProfileStatus.DRAFT,
        )
        return profile

    def confirm_job_profile(self, job_id: int, confirmed_by: str = "") -> int:
        return self.db.confirm_job_profile(job_id, confirmed_by=confirmed_by)

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
            payload["certificates"] = tuple(payload.get("certificates") or ())
            payload["age_min"] = int(payload.get("age_min") or 0)
            payload["age_max"] = int(payload.get("age_max") or 0)
            return RequirementProfile(**payload)
        return build_requirement_profile(keyword=job.get("keyword", ""), jd=job.get("jd", ""))

    def assert_job_ready(self, job_id: int) -> dict[str, Any]:
        job = self.db.get_job(job_id)
        if not job:
            raise KeyError(f"岗位不存在: {job_id}")
        if job.get("profile_status") != ProfileStatus.CONFIRMED.value:
            raise ValueError("请先确认岗位标准，再开始搜索")
        profile = self.load_profile(job_id)
        if not (profile.keyword or job.get("keyword") or job.get("title")):
            raise ValueError("岗位没有可用搜索关键词")
        return job

    def create_sourcing_run(self, job_id: int, plan: SearchPlan) -> int:
        self.assert_job_ready(job_id)
        normalized = plan.normalized()
        return self.db.create_sourcing_run(job_id, normalized.query, normalized)

    def ingest_candidates(
        self,
        *,
        job_id: int,
        run_id: int | None,
        candidates: Iterable[dict[str, Any]],
    ) -> IngestSummary:
        """Persist one page/batch atomically and return job-scoped counts.

        The browser worker streams pages. A page is considered checkpointed only after
        this method commits candidate identities, snapshots, job links and assessments.
        """
        profile = self.load_profile(job_id)
        entries: list[tuple[dict[str, Any], Any]] = []
        counts = {
            AssessmentStatus.PASS: 0,
            AssessmentStatus.REVIEW: 0,
            AssessmentStatus.CONFLICT: 0,
        }
        for candidate in candidates:
            assessment = assess_candidate(candidate, profile)
            entries.append((candidate, assessment))
            counts[assessment.status] += 1

        if hasattr(self.db, "persist_candidate_assessment_batch"):
            persisted = self.db.persist_candidate_assessment_batch(
                job_id=job_id,
                run_id=run_id,
                entries=entries,
                profile=profile,
            )
            found = int(persisted["found"])
            new_candidates = int(persisted["new_candidates"])
            new_job_links = int(persisted["new_job_links"])
        else:  # pragma: no cover - compatibility fallback
            found = new_candidates = new_job_links = 0
            for candidate, assessment in entries:
                found += 1
                candidate_id, created, _ = self.db.upsert_candidate(candidate, run_id=run_id)
                job_candidate_id, linked = self.db.link_candidate_to_job(job_id, candidate_id)
                self.db.save_assessment(job_candidate_id, assessment, profile)
                new_candidates += int(created)
                new_job_links += int(linked)

        return IngestSummary(
            found=found,
            new_candidates=new_candidates,
            new_job_links=new_job_links,
            pass_count=counts[AssessmentStatus.PASS],
            review_count=counts[AssessmentStatus.REVIEW],
            conflict_count=counts[AssessmentStatus.CONFLICT],
        )

    def update_job_profile(self, job_id: int, *, keyword=None, min_education=None,
                           min_experience_years=None, age_min=None, age_max=None,
                           locations=None, required_skills=None, preferred_skills=None,
                           certificates=None, confirmed_by: str = "web") -> RequirementProfile:
        """用可编辑字段覆盖画像并重算全部候选人。"""
        cur = self.load_profile(job_id)
        profile = RequirementProfile(
            keyword=(keyword if keyword is not None else cur.keyword),
            required_skills=tuple(required_skills) if required_skills is not None else cur.required_skills,
            preferred_skills=tuple(preferred_skills) if preferred_skills is not None else cur.preferred_skills,
            min_education=(min_education if min_education is not None else cur.min_education),
            min_experience_years=(int(min_experience_years) if min_experience_years is not None else cur.min_experience_years),
            locations=tuple(locations) if locations is not None else cur.locations,
            title_terms=cur.title_terms,
            age_min=(int(age_min) if age_min is not None else cur.age_min),
            age_max=(int(age_max) if age_max is not None else cur.age_max),
            certificates=tuple(certificates) if certificates is not None else cur.certificates,
            source_evidence=cur.source_evidence,
            parser_version=cur.parser_version,
        )
        self.db.update_job(job_id, profile=profile, profile_status=ProfileStatus.CONFIRMED)
        self.db.confirm_job_profile(job_id, confirmed_by=confirmed_by)
        self.reassess_job(job_id)
        return profile

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
                "age": row.get("age", 0),
                "expected_salary": row.get("expected_salary", ""),
                "certificates": row.get("certificates", ""),
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
