# -*- coding: utf-8 -*-
import socket, sys, urllib.request, ssl, json

results = {}
# 1) raw socket
for host, port in [("github.com", 443), ("pypi.org", 443), ("8.8.8.8", 53), ("www.baidu.com", 80)]:
    try:
        s = socket.create_connection((host, port), timeout=10)
        s.close()
        results[f"socket {host}:{port}"] = "OK"
    except Exception as e:
        results[f"socket {host}:{port}"] = repr(e)

# 2) TLS via urllib
for url in ["https://pypi.org/simple/pefile/", "https://api.github.com"]:
    try:
        ctx = ssl.create_default_context()
        r = urllib.request.urlopen(url, timeout=15, context=ctx)
        results[url] = r.status
    except Exception as e:
        results[url] = repr(e)

for k, v in results.items():
    print(k, "=>", v)