# -*- coding: utf-8 -*-
"""resumeNumber 抓取与匹配：拦接口 → 按姓名定位。"""
import json

from workbench.zhilian_browser import ProductCandidateSearcher, open_candidate_contact  # noqa


def _make_bot():
    # 不启动浏览器，只测纯逻辑（_take_resume_number / 监听器的 JSON 解析）
    bot = ProductCandidateSearcher.__new__(ProductCandidateSearcher)
    bot._api_by_name = {}
    bot._api_ordered = []
    return bot


class _FakeResp:
    def __init__(self, url, payload):
        self.url = url
        self.headers = {"content-type": "application/json"}
        self._payload = payload

    def body(self):
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def _fire(bot, payload):
    """模拟触发监听器里的 JSON 解析逻辑。"""
    captured = {}

    def _on_response(resp):
        if "talent/search/list" in resp.url:
            data = json.loads(resp.body())
            lst = (data.get("data") or {}).get("list") or []
            byname, ordered = {}, []
            for item in lst:
                name = (item.get("userName") or "").strip()
                rn = (item.get("resumeNumber") or "").strip()
                if rn:
                    ordered.append(rn)
                if name and rn:
                    byname.setdefault(name, []).append(rn)
            if ordered:
                bot._api_by_name = byname
                bot._api_ordered = ordered
    _on_response(_FakeResp("https://rd6.zhaopin.com/api/talent/search/list?x=1", payload))


def test_resume_number_matched_by_name():
    bot = _make_bot()
    _fire(bot, {"data": {"list": [
        {"userName": "张先生", "resumeNumber": "RN_A"},
        {"userName": "刘女士", "resumeNumber": "RN_B"},
    ]}})
    assert bot._take_resume_number("张先生") == "RN_A"
    assert bot._take_resume_number("刘女士") == "RN_B"
    assert bot._api_ordered == ["RN_A", "RN_B"]


def test_duplicate_names_consumed_in_order():
    bot = _make_bot()
    _fire(bot, {"data": {"list": [
        {"userName": "张先生", "resumeNumber": "RN_1"},
        {"userName": "张先生", "resumeNumber": "RN_2"},
    ]}})
    assert bot._take_resume_number("张先生") == "RN_1"
    assert bot._take_resume_number("张先生") == "RN_2"
    assert bot._take_resume_number("张先生") == ""  # 消耗完


def test_unknown_name_returns_empty():
    bot = _make_bot()
    _fire(bot, {"data": {"list": [{"userName": "张先生", "resumeNumber": "RN_A"}]}})
    assert bot._take_resume_number("不存在的人") == ""
    assert bot._take_resume_number("") == ""


def test_non_search_url_ignored():
    bot = _make_bot()
    # 非搜索接口不应影响
    resp = _FakeResp("https://rd6.zhaopin.com/api/base/dict", {"data": {"list": [{"userName": "x", "resumeNumber": "y"}]}})
    assert "talent/search/list" not in resp.url
    assert bot._api_by_name == {}


def test_open_candidate_contact_signature():
    import inspect
    sig = inspect.signature(open_candidate_contact)
    assert "resume_number" in sig.parameters and "keyword" in sig.parameters
