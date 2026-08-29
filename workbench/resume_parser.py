# -*- coding: utf-8 -*-
"""把智联简历弹窗的全文文本解析成结构化数据（求职期望/工作经历/教育/证书/优势）。

输入是 innerText 抓下的纯文本（每行一个元素）。工作经历/教育经历以"时间段行"
（如 2024.07 - 2025.12 (1年 5个月)）为锚点切分条目。
"""
from __future__ import annotations

import re

SECTION_HEADERS = (
    "求职期望", "工作经历", "项目经历", "教育经历", "培训经历",
    "所获证书", "证书", "个人优势", "自我评价", "语言能力", "在校经历",
)

_PERIOD_RE = re.compile(r"(\d{4})\.(\d{2})\s*[-—~至到]\s*(?:(\d{4})\.(\d{2})|至今)")
_DURATION_RE = re.compile(r"\((?:(\d+)年)?\s*(?:(\d+)个?月)?\)")
_SALARY_RE = re.compile(r"^\d+(?:\.\d+)?\s*(?:万|千|元)\s*/?\s*月?$")
_NOISE = {"展开", "收起", "询问他", "询问她", "最近一份工作经历可能未更新", "在职，看看机会", "离职，正在找工作"}

# 公司性质/规模/融资标签——属于公司元信息，不属于职位
_COMPANY_TAG_RE = re.compile(
    r"(国有企业|民营企业|外资|上市公司|股份制|合资|国企|外企|私企|事业单位|政府机关|"
    r"专精特新|高新技术|独角兽|不需要融资|已上市|未融资|[A-D]轮|天使轮|战略投资|"
    r"\d+\s*[-~—]\s*\d+\s*人|\d+\s*人以上|\d+\s*人以下|少于\s*\d+\s*人)"
)


def _is_period(line: str) -> bool:
    return bool(_PERIOD_RE.search(line))


def _is_salary(line: str) -> bool:
    return bool(_SALARY_RE.match(line.strip()))


def _is_noise(line: str) -> bool:
    return line.strip() in _NOISE


def _duration_months(line: str) -> int:
    m = _DURATION_RE.search(line)
    if not m:
        return 0
    return int(m.group(1) or 0) * 12 + int(m.group(2) or 0)


def _is_desc(line: str) -> bool:
    """职责描述类长行：编号开头、或含句号、或较长。"""
    s = line.strip()
    return bool(re.match(r"^\d+[.、]", s)) or "。" in s or len(s) > 30


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    secs: dict[str, list[str]] = {}
    cur = None
    for ln in lines:
        s = ln.strip()
        if s in SECTION_HEADERS:
            cur = s
            secs[cur] = []
        elif cur is not None and s:
            secs[cur].append(s)
    return secs


def _parse_work(lines: list[str]) -> list[dict]:
    lines = [l for l in lines if not _is_noise(l)]
    entries = []
    period_idx = [i for i, l in enumerate(lines) if _is_period(l)]
    for k, p in enumerate(period_idx):
        # header：从上一段 body 结束处到本段时间行之间
        prev_body_end = 0 if k == 0 else period_idx[k - 1] + 1
        # 但上一段 body 可能延伸，这里 header = 上一段时间行之后到本段时间行之前，
        # 需要剥离上一段的描述行。从本段时间行向前取 header（短行），遇到描述行/上一段时间行停止。
        header = []
        i = p - 1
        while i >= prev_body_end and not _is_period(lines[i]) and not _is_desc(lines[i]):
            header.insert(0, lines[i])
            i -= 1
        # body：本段时间行之后到下一段时间行 header 之前
        nxt = period_idx[k + 1] if k + 1 < len(period_idx) else len(lines)
        body = [l for l in lines[p + 1:nxt]]
        salary = ""
        header = [h for h in header if not _is_salary(h) or (salary := h)]
        # 剥离公司性质/规模/融资标签：第一条非标签行是公司，其后第一条非标签行是职位
        clean = [h for h in header if not _COMPANY_TAG_RE.search(h)]
        company = clean[0] if clean else (header[0] if header else "")
        title = clean[1] if len(clean) > 1 else ""
        # body 里短行是标签，长行/编号行是职责
        tags = [b for b in body if not _is_desc(b)][:8]
        desc = " ".join(b for b in body if _is_desc(b))
        entries.append({
            "company": company,
            "title": title.strip("（）() "),
            "salary": salary,
            "period": lines[p],
            "months": _duration_months(lines[p]),
            "tags": tags,
            "description": desc,
        })
    return entries


def _parse_edu(lines: list[str]) -> list[dict]:
    lines = [l for l in lines if not _is_noise(l)]
    entries = []
    period_idx = [i for i, l in enumerate(lines) if _is_period(l)]
    for k, p in enumerate(period_idx):
        prev_end = 0 if k == 0 else period_idx[k - 1] + 1
        header = []
        i = p - 1
        while i >= prev_end and not _is_period(lines[i]):
            header.insert(0, lines[i])
            i -= 1
        nxt = period_idx[k + 1] if k + 1 < len(period_idx) else len(lines)
        tail = lines[p + 1:nxt]
        school = header[0] if header else ""
        degree = ""
        for t in tail:
            if t in ("博士", "硕士", "MBA", "本科", "大专", "高中", "中专", "初中"):
                degree = t
                break
        major = next((t for t in tail if t != degree and t != "统招" and not _is_period(t)), "")
        entries.append({"school": school, "period": lines[p], "major": major, "degree": degree})
    return entries


def parse_resume(full_text: str) -> dict:
    """解析完整简历全文为结构化 dict。"""
    if not full_text:
        return {}
    lines = [l for l in (full_text or "").split("\n") if l.strip()]
    secs = _split_sections(lines)
    out: dict = {}
    # 求职期望
    exp = [l for l in secs.get("求职期望", []) if not _is_noise(l)]
    if exp:
        out["expectation"] = {
            "location": exp[0].strip("[]") if exp else "",
            "title": exp[1] if len(exp) > 1 else "",
            "salary": next((e for e in exp if _is_salary(e) or "/月" in e), ""),
            "industry": exp[-1] if len(exp) > 3 else "",
        }
    if "工作经历" in secs:
        out["work"] = _parse_work(secs["工作经历"])
    if "教育经历" in secs:
        out["education"] = _parse_edu(secs["教育经历"])
    certs = [l for l in secs.get("所获证书", []) + secs.get("证书", []) if not _is_noise(l)]
    if certs:
        out["certificates"] = certs
    adv = secs.get("个人优势", []) + secs.get("自我评价", [])
    if adv:
        out["advantages"] = "\n".join(adv)
    return out
