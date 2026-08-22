# 招聘自动化工作台 V0.9

面向企业招聘人员的本地优先工作台。系统以“岗位”为中心，连接智联招聘受控浏览器、候选人入池、证据化评估、人工复核和跟进记录。

当前版本为 **V0.9 Productization Alpha**：工程主链路、现代桌面界面、受控浏览器和测试基线已经完成；真实客户账号、平台页面稳定性、安装签名、升级回滚和合规边界仍需现场验收。

## 产品主线

```text
创建岗位
  → 解析岗位画像草稿
  → 招聘人员确认岗位标准
  → 配置搜索页数、人数和浏览器
  → 可视化智联搜索
  → 暂停 / 人工接管 / 继续 / 停止
  → 候选人稳定入池与快照
  → 建议优先查看 / 信息待核验 / 明确冲突
  → 人工复核、跟进、面试、人才库或归档
```

## V0.9 已实现

### 现代桌面工作台

- PySide6 现代化企业界面，不再使用旧式灰色 Tkinter 主界面
- 左侧岗位中心，右侧岗位工作台、候选人收件箱、自动化任务和系统设置
- 首次空状态、四步招聘流程、岗位级统计和业务化状态文案
- 候选人复核对话框：证据、阶段、负责人、备注、下一次跟进和人工结论

### 岗位与评估

- 岗位画像分为 `DRAFT` 和 `CONFIRMED`
- 只有招聘人员明确确认岗位标准后，系统才允许开始搜索
- 修改岗位标准后自动回到草稿状态，避免旧标准继续驱动自动化
- 不同岗位的候选人、评估、阶段、统计和导出完全隔离
- 年龄、性别和联系方式不参与自动评估和排序
- 信息缺失或经验区间不确定进入“信息待核验”，不会自动淘汰
- 明确学历、经验等规则冲突才进入“明确冲突”

### 可视化受控浏览器

默认浏览器顺序：

1. 工作台自带 Playwright Chromium（推荐）
2. Microsoft Edge
3. Google Chrome
4. 自定义 Chromium 路径（高级模式）

V0.9 不承诺支持 360、搜狗、QQ 浏览器、Firefox 或 WebKit。

自动化运行在独立 Browser Worker 线程，支持：

- 显示受控浏览器
- 工作台与浏览器左右分屏
- 暂停
- 人工接管
- 继续
- 安全停止
- 从页面检查点恢复
- 在同一登录 Profile 中打开候选人来源
- 重置浏览器
- 清除智联登录状态

应用不再固定伪造 User-Agent，也不再使用自动化规避启动参数。

### 数据与诊断

- 岗位、搜索任务、候选人主身份、采集快照和岗位候选人关系
- 版本化评估、人工复核决定、跟进记录、审计记录和导出记录
- SQLite WAL、外键、独立连接和显式写事务
- 旧版数据库自动增加岗位确认和搜索计划字段
- 本地数据库一致性备份与恢复
- 自动化失败时保存错误码、截图、页面 HTML、Playwright Trace 和运行元数据

## 目录结构

```text
app.py                         兼容启动入口
workbench_app.py               PySide6 产品入口
workbench/
  qt_ui.py                     现代桌面工作台
  qt_theme.py                  企业视觉系统
  qt_dialogs.py                岗位创建与候选人复核
  models.py                    领域状态与搜索计划
  evaluation.py                岗位解析与证据化评估
  database.py                  岗位中心数据库门面
  db_*.py                      数据库、迁移、候选人和审计
  service.py                   应用服务与确认门禁
  browser_worker.py            专用浏览器线程和人工接管
  zhilian_browser.py           受控浏览器与智联页面适配器
  browser_runtime.py           自带浏览器运行时
  settings.py                  本地产品设置
  diagnostics.py               失败诊断包
code/
  searcher.py / bot.py         旧适配层，供新适配器复用解析能力
  recruitment_engine.py        评估引擎兼容导出
tests/                         领域、迁移、岗位隔离、浏览器控制测试
docs/                          架构、产品化、验收和安全说明
```

## 源码运行

要求 Python 3.10 或更高版本。

Windows 首次安装：

```bat
setup.bat
```

之后启动：

```bat
run.bat
```

也可直接运行：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

## 构建可分发版本

```bat
build.bat
```

构建脚本会：

1. 编译检查和运行单元测试；
2. 下载与固定 Playwright 版本匹配的 Chromium；
3. 使用 PyInstaller `onedir` 打包 PySide6、Playwright 和受控浏览器；
4. 生成发布目录和 ZIP。

产物：

```text
dist\招聘自动化工作台\招聘自动化工作台.exe
dist\招聘自动化工作台-v0.9.zip
```

正式发布包不要求客户预装 Python 或 Google Chrome。

## 本地数据位置

```text
%LOCALAPPDATA%\RecruitmentWorkbench\workbench.db
%LOCALAPPDATA%\RecruitmentWorkbench\settings.json
%LOCALAPPDATA%\RecruitmentWorkbench\browser_profiles
%LOCALAPPDATA%\RecruitmentWorkbench\diagnostics
%LOCALAPPDATA%\RecruitmentWorkbench\logs
```

## 测试

```bash
python -m compileall -q workbench workbench_app.py app.py code tests
python -m unittest discover -s tests -v
```

测试覆盖：

- 跨岗位隔离
- 候选人重复抓取和快照
- 岗位级导出
- 经验区间不误判
- 多地点任一匹配
- 年龄、性别不影响评估
- 岗位画像确认门禁
- 修改标准后回到草稿
- 搜索计划持久化
- V1 数据库增量迁移
- 浏览器专用线程
- 暂停、继续和取消
- 产品设置归一化

## 当前交付边界

V0.9 是招聘人员的决策辅助与自动化工作台，不替代最终录用判断，也不应自动淘汰信息缺失的候选人。

进入客户试点前仍必须完成：

1. 授权客户 Windows 电脑的安装与启动；
2. 客户智联账号登录及登录态复用；
3. 真实搜索页面连续运行不少于 10 次；
4. 候选人平台 UID 稳定性验证；
5. 验证码、网络中断、页面变化和浏览器关闭后的接管与恢复；
6. 客户黄金样本评估确认；
7. 平台服务规则、数据授权、保存期限和知识产权审查；
8. 安装包签名、升级和回滚。

详细门禁见：

- `docs/PRODUCTIZATION.md`
- `docs/DELIVERY_CHECKLIST.md`
- `docs/ACCEPTANCE.md`
- `docs/SECURITY_BASELINE.md`
