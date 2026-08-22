# 云只智联 · 候选人筛选排序工具

> 复刻自 `云只_智联 4.3.8.exe`（VMProtect 加壳 32 位易语言程序），已**剥离原软件的全部账号/卡密/设备绑定/云同步**机制，只保留核心找人功能，并重构为更易用的产品形态。
> 逆向过程与证据见 [`逆向分析报告.md`](逆向分析报告.md)。

## 这是什么

给一线 HR 用的智联招聘自动化工具：

```
填关键词 / 粘贴 JD → 勾选筛人条件 → 点「开始筛选」
  → 软件自动登录智联、搜索人才、翻页抓取候选人
  → 按匹配度打分排序 → 输出可跟进的候选人名单
```

**两个主页面**：
1. **筛选**：写条件（JD 一键解析出学历/经验/地点）+ 选条件 + 开始筛选（进度条 + 实时日志全程可见）
2. **候选人排序**：按匹配分排序的结果、跟进状态标记、多人对比、CSV 导出

## 技术栈

| 模块 | 技术 |
|---|---|
| GUI | tkinter + ttk（两个主页面） |
| 浏览器自动化 | Playwright（CDP）驱动**系统已安装的 Chrome** |
| 数据源 | 智联 `rd6.zhaopin.com/app/search` 搜索人才页（不依赖在招职位） |
| 登录 | 持久化 user-data-dir，登录一次长期有效 |
| 存储 | SQLite（位于 `%LOCALAPPDATA%\云只智联\yunzhi.db`） |
| 打包 | PyInstaller onefile |

## 打分模型（0~100）

- **关键词匹配 40 分**：用户关键词 + JD 提取的技能/岗位词在候选人简历中的命中率
- **条件符合度 35 分**：学历 10 + 经验 8 + 地点 7 + 年龄 5 + 性别 5
- **活跃度 25 分**：在线 25 / 刚刚活跃 20 / 今日 15 / 本周 10 / 本月 5

≥70 绿色高匹配，≥40 黄色，其余灰色。

## 目录结构

```
app.py                  主程序（GUI + 筛选流水线）
build.bat               一键打包脚本
code/
  bot.py                BrowserBot：系统 Chrome 探测/启动/登录检测
  searcher.py           候选人抓取：搜索人才翻页抓取 + IM 卡片解析
  matcher.py            关键词提取 + 打分排序引擎
  jd_parser.py          JD 解析（硬性条件/技能/城市）
  db.py                 SQLite 存储（候选人池 + 跟进状态）
  demo_data.py          演示模式模拟数据
  *.py                  逆向辅助脚本（vmpdump/rdata 提取/接口探测）
dumped/                 原程序 rdata 提取的选择器/URL/API 清单
逆向分析报告.md          原软件逆向分析（VMProtect/易语言/UI 结构/技术方案）
test_*.py               各阶段验证脚本（登录链路/跨线程/真实抓取/全流程）
```

## 运行

```bat
pip install playwright
python app.py
```

打包：`build.bat` 或

```bat
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "云只智联候选人筛选排序工具" ^
  --paths code --collect-all playwright ^
  --hidden-import matcher --hidden-import searcher --hidden-import bot ^
  --hidden-import db --hidden-import scripts --hidden-import demo_data ^
  --hidden-import jd_parser app.py
```

## 使用说明

1. 打开软件，「关键词」框填要找的岗位/技能（如 `Java`、`销售`）
2. 可选：粘贴岗位 JD → 点「解析 JD 并自动填条件」；勾选学历/经验/年龄/城市等
3. 点 **开始筛选**：
   - 首次会弹出浏览器引导登录智联（扫码/短信），登录一次后自动记住
   - 之后每次自动进入搜索人才页 → 输入关键词 → 翻页抓取（每次最多 5 页 / 200 人）
4. 完成后自动跳转到「候选人排序」页，可标记跟进状态、对比、导出 CSV

> 未登录智联时可勾选「演示模式」体验完整流程（模拟数据）。

## 与原软件的关系

| 维度 | 原软件 云只_智联 4.3.8 | 本复刻版 |
|---|---|---|
| 授权 | 卡密/账号/设备绑定 + 云端验证 | 无，直接运行 |
| 浏览器 | 驱动外部 Chrome（CSS 选择器） | 相同思路：Playwright 驱动系统 Chrome |
| 数据源 | 推荐人才/IM 流 | 搜索人才页（不依赖职位，更稳定） |
| 候选人跟进 | 简单 | 状态标记 + 对比 + 导出 |

## 注意事项

- 仅用于自己账号的招聘工作提效，请遵守智联招聘平台规则
- 抓取频率已做节流，请勿用于批量爬取
- 候选人个人信息请注意保密，勿外传
