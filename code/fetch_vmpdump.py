# -*- coding: utf-8 -*-
"""抓取 vmpdump 的 GitHub 原文 README 与 release，确认架构支持与用法。"""
import urllib.request, ssl, json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"})
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read().decode("utf-8", "replace")

candidates = [
    "https://raw.githubusercontent.com/0xnobody/vmpdump/master/README.md",
    "https://raw.githubusercontent.com/0xnobody/vmpdump/main/README.md",
]
for u in candidates:
    try:
        t = fetch(u)
        print("=" * 60)
        print("### README:", u)
        print(t[:4000])
        break
    except Exception as e:
        print("FAIL", u, e)

print("\n" + "=" * 60)
print("### releases")
for repo in ["0xnobody/vmpdump"]:
    try:
        data = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases"))
        print(f"{repo}: {len(data)} releases")
        for r in data[:5]:
            print("  tag:", r.get("tag_name"), "| assets:")
            for a in r.get("assets", []):
                print("     -", a.get("name"), a.get("browser_download_url"))
    except Exception as e:
        print("release FAIL", repo, e)