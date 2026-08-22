# -*- coding: utf-8 -*-
"""抓取用户提供的参考链接内容，了解 vmpdump 工具与脱壳方法。"""
import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read().decode("utf-8", "replace")

def strip_html(html):
    html = re.sub(r"<script[\s\S]*?</script>", " ", html)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html)
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()

targets = [
    ("CSDN博客", "https://blog.csdn.net/gitblog_00661/article/details/154009676"),
    ("gitcode vmpdump", "https://gitcode.com/gh_mirrors/vm/vmpdump"),
]

for name, url in targets:
    print("=" * 60)
    print(f"### {name}: {url}")
    try:
        html = fetch(url)
        # title
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
        if m:
            print("TITLE:", m.group(1).strip()[:200])
        txt = strip_html(html)
        print("LEN:", len(txt))
        # print first meaningful chunk
        print(txt[:2500])
    except Exception as e:
        print("FETCH FAIL:", e)
    print()