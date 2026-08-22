# -*- coding: utf-8 -*-
import unittest

from workbench.evaluation import assess_candidate, build_requirement_profile, requirement_summary
from workbench.models import AssessmentStatus


class EvaluationTests(unittest.TestCase):
    def test_required_and_preferred_are_separated(self):
        profile = build_requirement_profile(
            keyword="Java",
            jd="要求熟悉 Java 和 MySQL；有 Redis 经验优先；本科及以上，至少3年经验，工作地点南京。",
        )
        self.assertIn("java", profile.required_skills)
        self.assertIn("mysql", profile.required_skills)
        self.assertIn("redis", profile.preferred_skills)
        self.assertEqual(profile.min_education, "本科")
        self.assertEqual(profile.min_experience_years, 3)
        self.assertIn("南京", profile.locations)
        self.assertIn("必须能力", requirement_summary(profile))

    def test_experience_range_is_review_not_false_pass(self):
        profile = build_requirement_profile(keyword="Java", jd="本科及以上，至少3年经验，熟悉Java。")
        candidate = {
            "name": "候选人",
            "title": "Java工程师",
            "education": "本科",
            "experience": "1-3年",
            "skills": "Java",
            "text": "Java开发",
        }
        assessment = assess_candidate(candidate, profile)
        self.assertEqual(assessment.status, AssessmentStatus.REVIEW)
        self.assertTrue(any("无法确认" in reason for reason in assessment.reasons))

    def test_explicit_education_conflict(self):
        profile = build_requirement_profile(keyword="Java", jd="本科及以上，熟悉Java。")
        candidate = {
            "name": "候选人",
            "title": "Java工程师",
            "education": "大专",
            "experience": "5年",
            "skills": "Java",
            "text": "Java开发",
        }
        assessment = assess_candidate(candidate, profile)
        self.assertEqual(assessment.status, AssessmentStatus.CONFLICT)

    def test_multiple_locations_use_any_match(self):
        profile = build_requirement_profile(keyword="Java", jd="熟悉Java，工作地点南京或苏州。")
        candidate = {
            "name": "候选人",
            "title": "Java工程师",
            "location": "南京",
            "skills": "Java",
            "text": "Java开发",
        }
        assessment = assess_candidate(candidate, profile)
        self.assertFalse(any("工作地点需确认" in reason for reason in assessment.reasons))

    def test_age_and_gender_do_not_affect_assessment(self):
        profile = build_requirement_profile(keyword="Java", jd="熟悉Java。")
        base = {
            "name": "候选人",
            "title": "Java工程师",
            "skills": "Java",
            "text": "Java开发",
        }
        first = assess_candidate({**base, "age": 22, "gender": "女"}, profile)
        second = assess_candidate({**base, "age": 50, "gender": "男"}, profile)
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.fit_score, second.fit_score)
        self.assertEqual(first.reasons, second.reasons)


if __name__ == "__main__":
    unittest.main()
