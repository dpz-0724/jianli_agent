# -*- coding: utf-8 -*-
"""演示数据生成器：无账号时一键生成模拟候选人池，体验搜索/筛选/排序全流程。"""
import random

SURNAMES = ["张", "王", "李", "刘", "陈", "杨", "黄", "赵", "周", "吴", "徐", "孙", "马", "朱", "胡", "郭", "林", "何", "高", "罗"]
GIVEN = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "秀英", "霞", "平", "刚", "桂英"]

# 岗位 -> (标题列表, 技能词, 常见地点, 学历池, 经验池)
JOBS = [
    ("java", ["Java开发工程师", "高级Java工程师", "Java后端开发", "Java架构师"],
     ["Java", "Spring", "Spring Boot", "MySQL", "Redis", "微服务", "MyBatis", "分布式", "Docker", "K8s"],
     ["北京", "上海", "杭州", "深圳"], ["大专", "本科", "硕士"], ["1-3年", "3-5年", "5-10年"]),
    ("python", ["Python开发", "Python后端", "数据工程师", "爬虫工程师"],
     ["Python", "Django", "Flask", "爬虫", "数据分析", "机器学习", "Linux", "MySQL"],
     ["北京", "上海", "深圳", "广州"], ["本科", "硕士"], ["1-3年", "3-5年"]),
    ("前端", ["前端开发", "Web前端", "Vue开发", "React开发"],
     ["JavaScript", "Vue", "React", "TypeScript", "HTML", "CSS", "小程序", "Node.js"],
     ["北京", "杭州", "深圳", "成都"], ["大专", "本科"], ["1-3年", "3-5年"]),
    ("测试", ["软件测试", "测试工程师", "自动化测试", "QA工程师"],
     ["测试", "自动化测试", "Selenium", "Python", "接口测试", "性能测试", "App测试"],
     ["北京", "上海", "深圳"], ["大专", "本科"], ["1-3年", "3-5年", "5-10年"]),
    ("销售", ["销售经理", "大客户销售", "电话销售", "销售顾问"],
     ["销售", "客户开发", "谈判", "BD", "地推", "电销", "CRM"],
     ["北京", "上海", "广州", "武汉", "成都"], ["高中", "大专", "本科"], ["一年以内", "1-3年", "3-5年"]),
    ("财务", ["会计", "财务专员", "总账会计", "出纳"],
     ["会计", "财务", "记账", "报税", "Excel", "金蝶", "用友", "成本核算"],
     ["北京", "上海", "深圳", "南京"], ["大专", "本科"], ["1-3年", "3-5年", "5-10年"]),
    ("运营", ["新媒体运营", "电商运营", "内容运营", "用户运营"],
     ["运营", "新媒体", "短视频", "文案", "数据分析", "抖音", "公众号", "直播"],
     ["北京", "上海", "杭州", "广州"], ["大专", "本科"], ["1-3年", "3-5年"]),
    ("设计", ["平面设计", "UI设计师", "美工", "视觉设计"],
     ["Photoshop", "PS", "AI", "Illustrator", "UI", "平面设计", "Sketch", "海报"],
     ["北京", "上海", "深圳", "成都"], ["大专", "本科"], ["1-3年", "3-5年"]),
]

ACTIVITIES = ["在线", "刚刚活跃", "今日活跃", "本周活跃", "本月活跃"]
ACT_W = [0.12, 0.15, 0.18, 0.25, 0.30]  # 活跃度概率权重

_AGE_MAP = {"一年以内": (20, 24), "1-3年": (22, 28), "3-5年": (26, 34), "5-10年": (30, 42), "在校/应届": (19, 23)}


def gen_candidates(n=40, seed=None):
    """生成 n 个覆盖多岗位的模拟候选人。"""
    rng = random.Random(seed)
    cands = []
    for _ in range(n):
        _jk, titles, skills, locs, edus, exps = rng.choice(JOBS)
        title = rng.choice(titles)
        name = rng.choice(SURNAMES) + rng.choice(GIVEN)
        edu = rng.choice(edus)
        exp = rng.choice(exps)
        lo, hi = _AGE_MAP.get(exp, (22, 35))
        age = rng.randint(lo, hi)
        act = rng.choices(ACTIVITIES, weights=ACT_W)[0]
        k = rng.randint(2, 4)
        skill_hits = rng.sample(skills, min(k, len(skills)))
        text = " ".join(skill_hits) + f" {title} {exp}经验"
        cands.append({
            "name": name, "title": title, "location": rng.choice(locs),
            "education": edu, "experience": exp, "age": age,
            "activity": act, "skills": "|".join(skill_hits), "text": text,
            "source": "演示数据",
        })
    return cands


if __name__ == "__main__":
    for c in gen_candidates(8, seed=1):
        print(c["name"], c["title"], c["location"], c["education"], c["experience"], c["age"], c["activity"])