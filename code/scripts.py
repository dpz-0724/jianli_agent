# -*- coding: utf-8 -*-
"""话术模板 + 关键词过滤引擎。

还原自逆向提取的真实文案：
- 打招呼话术（固定模板，%s 占位为牛人昵称/期望职位）
- 「条件不符回复话术」：当牛人回复包含过滤关键词时，发送的终止话术
- 关键词过滤：命中关键词则不与该牛人沟通
"""
import re

# --- 打招呼话术（还原自 final_cjk.txt）---
GREETINGS = [
    "您好，看您有时在线，找到适合的工作了吗？您看我们单位是否适合您，可以的话给您介绍下？",
    "可以的话请同意下联系方式，相信您和我们的详细了解后，会让您对这份工作更加有兴趣的",
    "详细的薪资待遇我们微信上聊吧，麻烦交换下哦！",
    "这方面问题我们加V详聊吧，直接给您发表格查看",
    "关于补贴方面需要面谈的，方便的话先加个联系方式吧，我发给您过目！",
]

# --- 终结/终止话术（条件不符）---
REJECT_TEMPLATES = [
    "非常抱歉，您的年龄暂时不符合要求，祝您找到满意的工作",
    "打扰您了，祝您找到满意的工作！",
]

# 默认：命中「没兴趣/不想去/太远了」等关键词 → 不与该牛人沟通
DEFAULT_FILTER_KEYWORDS = [
    "没兴趣", "不想去", "太远了", "不考虑", "不合适", "看机会",
    "干什么", "做什么", "工作内容",  # 示例：来自「干什么 做什么 工作内容」
]

# 请求交换联系方式类关键词（用于判断牛人是否愿意交换微信/手机）
EXCHANGE_KEYWORDS = ["微信", "vx", "VX", "加V", "手机号", "电话", "联系方式"]


class KeywordFilter:
    """沟通关键词过滤器（对应 UI「过滤沟通关键词：」「简历关键词：」）"""

    def __init__(self, keywords=None):
        self.keywords = [k for k in (keywords or DEFAULT_FILTER_KEYWORDS) if k]

    def match(self, text: str):
        """返回命中的关键词列表（空列表=可以沟通）"""
        if not text:
            return []
        return [k for k in self.keywords if k and k in text]

    def should_skip(self, text: str):
        """命中任一关键词 → 不沟通（不与该牛人打招呼/继续沟通）"""
        return bool(self.match(text))


class ScriptEngine:
    """话术引擎：挑选打招呼话术 / 生成终止话术"""

    def __init__(self, greetings=None, rejects=None):
        self.greetings = greetings or GREETINGS
        self.rejects = rejects or REJECT_TEMPLATES
        self._i = 0

    def next_greeting(self, nickname="", title=""):
        """轮换取一条打招呼话术"""
        tpl = self.greetings[self._i % len(self.greetings)]
        self._i += 1
        return tpl

    def reject_message(self):
        return self.rejects[0]


if __name__ == "__main__":
    kf = KeywordFilter()
    assert kf.should_skip("不好意思，太远了") is True
    assert kf.should_skip("想去看看") is False
    print("keyword filter ok, matched:", kf.match("太远了不想去"))
    se = ScriptEngine()
    print("greeting:", se.next_greeting("张三", "销售"))
    print("reject:", se.reject_message())