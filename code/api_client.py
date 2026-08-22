# -*- coding: utf-8 -*-
"""云服务器 API 客户端（字段名已通过服务端探测精确还原）。

服务器: http://175.24.227.191:8088（PHP / 宝塔 index.php）
响应格式: {"stat": <1=成功|0=失败>, "msg": <错误文本|数组数据>}

字段名（拼音，逐端点从 PHP 'Undefined array key' 泄露还原）:
  通用    zhanghao(账号) mima(密码,服务端MD5) shouji(手机) leixing(类型) pingtai(平台)
  数据    name(姓名) phone(手机号) weichat(微信) company(公司) laiyuan(来源)
          qiwangzhiwei(期望职位) goutongzhiwei(沟通职位) jibenxinxi(基本信息)
          shiyongzhe(使用者) nianlin(年龄) xueli(学历)
  更新    id key time
"""
import urllib.request
import urllib.parse
import json
import ssl
import time as _time

BASE_URL = "http://175.24.227.191:8088"

ENDPOINTS = {
    "login":               "/api/login",            # zhanghao, mima
    "reg":                 "/api/reg",              # zhanghao, mima, shouji
    "kamiSave":            "/api/kamiSave",         # 卡密激活（需 laiyuan 来源）
    "getzhilianka":        "/api/getzhilianka",     # leixing, pingtai
    "updatazhiliankanew":  "/api/updatazhiliankanew",  # id, key, pingtai, time
    "update_mima":         "/api/update_mima",      # zhanghao, mima(旧), 新密码
    "getAllData":          "/api/getAllData",       # 需登录态
    "getMoHuData":         "/api/getMoHuData",
    "getNunbers":          "/api/getNunbers",
    "daochuAllData":       "/api/daochuAllData",
    "insertDataNewUp":     "/api/insertDataNewUp",  # 数据行字段见 FIELD_MAP
    "updateWeichatNew":    "/api/updateWeichatNew", # id, weichat, time
    "updatePhoneNew":      "/api/updatePhoneNew",   # id, phone, time
    "judgeWeichat":        "/api/judgeWeichat",     # zhanghao, name, weichat, laiyuan
    "judgePhone":          "/api/judgePhone",       # zhanghao, name, phone, laiyuan
    "judgeDatas":          "/api/judgeDatas",       # zhanghao, name, nianlin, xueli, laiyuan
    "messageNotifySend2":  "/api/messageNotify/send2",  # zhanghao, 消息内容
    "messageNotifySend3":  "/api/messageNotify/send3",
}

# 简历/沟通数据行字段（中文语义）
FIELD_MAP = {
    "name":          "姓名",
    "phone":         "手机号",
    "weichat":       "微信",
    "company":       "公司",
    "laiyuan":       "来源（平台）",
    "qiwangzhiwei":  "期望职位",
    "goutongzhiwei": "沟通职位",
    "jibenxinxi":    "基本信息",
    "shiyongzhe":    "使用者",
    "nianlin":       "年龄",
    "xueli":         "学历",
}

EXTERNAL = {
    "resumes":       "http://external.5jingcai.com/api/v1/yunzhi/resumes.json",
    "resumes_wechat": "http://external.5jingcai.com/api/v1/yunzhi/resumes/wechat.json",
    "resumes_phone": "http://external.5jingcai.com/api/v1/yunzhi/resumes/phone.json",
    "resumes_match": "http://external.5jingcai.com/api/v1/yunzhi/resumes/match.json",
    "notice":        "http://api.paojiaoyun.com/v1/software/notice",
    "config":        "http://api.paojiaoyun.com/v1/software/config",
    "netver":        "http://api.ruikeyz.com/NetVer/webapi959641B1",
    "count_site":    "http://count.jimstone.com.cn/api/v1/countSite",
}


class CloudAPI:
    def __init__(self, base=BASE_URL, zhanghao=None, pingtai="zhaopin"):
        self.base = base
        self.zhanghao = zhanghao
        self.pingtai = pingtai
        self.session = None       # 登录成功后由服务端 cookie 维持
        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode = ssl.CERT_NONE

    # ---- 底层 ----
    def _post(self, endpoint, data=None, timeout=15):
        data = dict(data or {})
        if self.zhanghao and "zhanghao" not in data:
            data["zhanghao"] = self.zhanghao
        if self.pingtai and "pingtai" not in data and endpoint in ("getzhilianka", "updatazhiliankanew"):
            data["pingtai"] = self.pingtai
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(self.base + ENDPOINTS[endpoint], data=body, method="POST",
                                     headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
        rs = urllib.request.urlopen(req, timeout=timeout, context=self._ssl)
        text = rs.read().decode("utf-8", "replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"stat": 0, "msg": text, "raw": True}

    # ---- 账号 ----
    def login(self, zhanghao, mima):
        """mima 按明文发送，服务端做 md5 比对。"""
        resp = self._post("login", {"zhanghao": zhanghao, "mima": mima})
        if resp.get("stat") == 1:
            self.zhanghao = zhanghao
            self.session = True
        return resp

    def register(self, zhanghao, mima, shouji=""):
        return self._post("reg", {"zhanghao": zhanghao, "mima": mima, "shouji": shouji})

    def change_password(self, zhanghao, old_mima, new_mima):
        # 字段由 .rdata 明文还原: &newmima=
        return self._post("update_mima", {"zhanghao": zhanghao, "mima": old_mima, "newmima": new_mima})

    # ---- 授权 ----
    def activate_kami(self, kami_code, laiyuan="智联招聘"):
        return self._post("kamiSave", {"kami": kami_code, "laiyuan": laiyuan})

    def get_zhilianka(self, leixing="1"):
        return self._post("getzhilianka", {"leixing": leixing})

    # ---- 数据同步 / 导出 ----
    def sync_all(self):
        return self._post("getAllData")

    def get_mohu_data(self):
        return self._post("getMoHuData")

    def get_numbers(self):
        return self._post("getNunbers")

    def export_all(self):
        return self._post("daochuAllData")

    def upload_record(self, record: dict):
        """record 键名需为 FIELD_MAP 中的拼音字段（name/phone/weichat/...）。"""
        return self._post("insertDataNewUp", record)

    def update_wechat(self, id, weichat, time_val=None):
        return self._post("updateWeichatNew", {"id": id, "weichat": weichat,
                                              "time": time_val or _time.strftime("%Y-%m-%d %H:%M:%S")})

    def update_phone(self, id, phone, time_val=None):
        return self._post("updatePhoneNew", {"id": id, "phone": phone,
                                            "time": time_val or _time.strftime("%Y-%m-%d %H:%M:%S")})

    # ---- 校验 ----
    def judge_wechat(self, name, weichat, laiyuan="智联招聘"):
        return self._post("judgeWeichat", {"name": name, "weichat": weichat, "laiyuan": laiyuan})

    def judge_phone(self, name, phone, laiyuan="智联招聘"):
        return self._post("judgePhone", {"name": name, "phone": phone, "laiyuan": laiyuan})

    def judge_data(self, name, nianlin="", xueli="", laiyuan="智联招聘"):
        return self._post("judgeDatas", {"name": name, "nianlin": nianlin, "xueli": xueli, "laiyuan": laiyuan})

    # ---- 通知 ----
    def notify(self, content, channel="send2"):
        return self._post("messageNotifySend2" if channel == "send2" else "messageNotifySend3",
                          {"neirong": content})

    # ---- 第三方 ----
    def fetch_resumes(self, kind="resumes", **params):
        req = urllib.request.Request(EXTERNAL[kind] + ("?" + urllib.parse.urlencode(params) if params else ""),
                                     headers={"User-Agent": "Mozilla/5.0"})
        return json.loads(urllib.request.urlopen(req, timeout=15, context=self._ssl).read().decode("utf-8", "replace"))

    def check_update(self):
        return json.loads(urllib.request.urlopen(EXTERNAL["config"], timeout=15, context=self._ssl).read().decode("utf-8", "replace"))


if __name__ == "__main__":
    c = CloudAPI()
    print("登录探测:", c.login("test999999", "testpass"))          # 预期 stat=0（账号不存在）
    print("智联卡:", c.get_zhilianka("1"))                          # 预期 stat=1
    print("微信校验:", c.judge_wechat("张三", "wx_test"))           # 预期 stat=1