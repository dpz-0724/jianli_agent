# -*- coding: utf-8 -*-
"""个性化打招呼话术生成——基于候选人简历与岗位，给 HR 一段可直接复制的外联开场白。

不用 LLM、不自动发送：纯规则模板，确定性、可控、安全。
"""
from __future__ import annotations

from typing import Any


def _s(v: Any) -> str:
    return str(v or "").strip()


def generate_greeting(candidate: dict[str, Any], job_title: str = "",
                      profile: Any = None, parsed_resume: dict | None = None) -> str:
    name = _s(candidate.get("name")) or "您好"
    title = _s(candidate.get("title"))
    job = _s(job_title) or "这个岗位"

    # 最近工作（公司+职位）
    recent_co, recent_ti = "", ""
    if parsed_resume:
        work = parsed_resume.get("work") or []
        if work:
            recent_co = _s(work[0].get("company"))
            recent_ti = _s(work[0].get("title"))
    recent_ti = recent_ti or title

    # 岗位信息
    loc = ""
    budget = ""
    if profile is not None:
        locs = getattr(profile, "locations", ()) or ()
        loc = locs[0] if locs else ""
        lo, hi = getattr(profile, "salary_min", 0), getattr(profile, "salary_max", 0)
        if lo and hi:
            budget = f"{lo}-{hi}K"

    # 现况描述
    if recent_co and recent_ti:
        cur = f"看到您目前在{recent_co}做{recent_ti}"
    elif recent_ti:
        cur = f"看到您目前在做{recent_ti}"
    else:
        cur = "看到您的简历"

    # 岗位描述
    loc_txt = f"（{loc}）" if loc else ""
    budget_txt = f"，薪资{budget}" if budget else ""
    job_txt = f"我们正在招{job}{loc_txt}{budget_txt}"

    # 匹配点（挑一个最具体的命中技能，避免空泛）
    hook = ""
    if profile is not None:
        req = [s for s in (getattr(profile, "required_skills", ()) or ()) if len(str(s)) > 2]
        if req:
            hook = f"，和您在{req[0]}方面的经验挺契合"

    msg = f"{name}您好，{cur}。{job_txt}{hook}。看您的经历匹配度不错，方便的话想跟您聊聊，期待您的回复~"
    return msg
