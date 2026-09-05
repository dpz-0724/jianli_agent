# 简历智能体

面向 HR 的智联招聘简历筛选工具：按 JD 自动搜索、粗筛 + 深读两段漏斗评分、证书/技能提取、一键在智联里打开候选人简历卡进行联系。

## 运行

```bash
pip install -r requirements.txt
python -m playwright install chromium   # 首次需要
python desktop_app.py                    # 桌面版（原生窗口）
# 或纯网页版：
python -m webapp.server                  # 然后访问 http://127.0.0.1:8899
```

## 目录结构

```
desktop_app.py     桌面入口（pywebview 原生窗口）
webapp/            FastAPI 服务 + 前端单页
  server.py        REST API + 页面路由
  static/index.html  前端界面
workbench/         业务层
  zhilian_browser.py  智联抓取 + 联系（打开简历卡）
  evaluation.py       候选人评估/评分/硬规则
  jd_analyzer.py      JD 解析出岗位要求
  service.py          业务编排
  browser_worker.py   浏览器工作线程
  database.py + db_*.py  SQLite 持久化
  license_mgr.py      离线授权
code/              底层
  searcher.py         搜索卡片解析 + 技能/证书提取
  matcher.py          技能词表与匹配
  bot.py              浏览器机器人
tests/             单元测试（pytest tests/）
```

## 数据与登录

数据与浏览器登录态都在 `%LOCALAPPDATA%\RecruitmentWorkbench`，与代码位置无关，换目录/换机器部署不影响。

## 测试

```bash
python -m pytest tests/ -q
```
