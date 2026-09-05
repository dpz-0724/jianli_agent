# -*- coding: utf-8 -*-
"""技能去噪 + 证书提取/归一 的单元测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from searcher import _extract_skills, _extract_certificates  # noqa: E402


# ---------- 技能去噪 ----------
def test_skills_exclude_education():
    s = _extract_skills("销售行政主管 本科 3年 数据分析 门店管理")
    assert "本科" not in s
    assert "销售" in s and "数据分析" in s


def test_skills_exclude_cert_words():
    s = _extract_skills("持驾驶证 会计证 销售经验")
    assert "驾驶证" not in s and "会计证" not in s
    assert "销售" in s


def test_skills_no_false_positive_substring():
    # "pr" 不应误中 "spring"；中文词正常子串
    s = _extract_skills("负责 spring 框架开发")
    assert "pr" not in s.split("|")


# ---------- 证书提取与归一 ----------
def test_cert_basic():
    assert "教师资格证" in _extract_certificates("有教师资格证")


def test_cert_dedup_driver_license():
    # "驾驶证C1" 不应同时出现 驾驶证 和 驾驶证(C1)
    r = _extract_certificates("有驾驶证C1")
    assert "驾驶证(C1)" in r and "驾驶证、" not in r and r.count("驾驶证") == 1


def test_cert_alias_cpa():
    r = _extract_certificates("持证注册会计师CPA")
    assert "注册会计师(CPA)" in r
    assert "CPA" not in r.split("、")  # 不重复出现裸 CPA


def test_cert_english_level_alias():
    r = _extract_certificates("英语四级，CET-6")
    assert "英语四级" in r and "英语六级" in r


def test_cert_empty():
    assert _extract_certificates("普通销售经验") == ""
    assert _extract_certificates("") == ""
