# 招聘自动化工作台 V0.9

面向企业招聘人员的本地优先工作台。系统以“岗位”为中心，连接智联招聘受控浏览器、候选人入池、证据化评估、人工复核和跟进记录。

当前版本为 **V0.9 Productization Alpha**：工程主链路、现代桌面界面、受控浏览器和测试基线已经完成；真实客户账号、平台页面稳定性、安装签名、升级回滚和合规边界仍需现场验收。

## 产品主线

```text
登录智联
  → 创建或选择岗位
  → 填写结构化硬性条件 / 加分条件和完整 JD
  → 招聘人员确认岗位标准
  → 配置搜索页数、人数和浏览器
  → 点击“开始招聘”
  → 可视化智联搜索
  → 暂停 / 人工接管 / 继续 / 停止
  → 候选人去重、入池与快照
  → 首次入池 / 本岗位已更新 / 跨岗位已见
  → 建议优先查看 / 信息待核验 / 明确冲突
  → 人工复核、跟进、面试、人才库或归档
```

## V0.9 已实现

### 登录优先的统一工作台

- 主页面顶部直接显示智联登录与受控浏览器状态
- 返回应用时自动检查已保存的登录状态
- 未登录时点击“创建岗位”会明确进入登录流程，不再出现按钮无反馈
- 登录、岗位标准、开始招聘、暂停、接管、继续和停止集中在同一日常工作台
- 自动化任务和系统页保留为诊断与高级设置入口

### 现代桌面工作台

- PySide6 现代化企业界面，不再使用旧式灰色 Tkinter 主界面
- 左侧岗位中心，右侧主工作台、候选人收件箱、自动化任务和系统设置
- 首次空状态、四步招聘流程、岗位级统计和业务化状态文案
- Qt 操作异常会显示错误并写入日志，不再表现为“按钮没有反应”
- 候选人复核对话框：证据、阶段、负责人、备注、下一次跟进和人工结论

### 岗位与评估

岗位创建同时支持：

- 岗位名称和智联搜索关键词
- 完整岗位 JD
- 硬性最低学历
- 硬性最低经验
- 工作地点
- 必须能力标签
- 加分能力标签

岗位画像分为 `DRAFT` 和 `CONFIRMED`：

- 只有招聘人员明确确认岗位标准后，系统才允许开始搜索
- 修改岗位标准后自动回到草稿状态，避免旧标准继续驱动自动化
- 不同岗位的候选人、评估、阶段、统计和导出完全隔离
- 年龄、性别和联系方式不参与自动评估和排序
- 信息缺失或经验区间不确定进入“信息待核验”，不会自动淘汰
- 明确学历、经验等规则冲突才进入“明确冲突”

### 候选人去重与处理状态

去重优先级：

1. 智联平台 UID
2. 候选人来源身份
3. 姓名、职位、地区、学历、经验和简历摘要组成的稳定指纹

系统区分：

- **首次入池**：第一次识别到该候选人
- **本岗位已更新**：同一候选人在本岗位再次出现，更新资料并保留快照
- **跨岗位已见**：候选人曾进入其他岗位，显示历史岗位提示

同一个候选人在同一岗位不会重复创建；人工处理状态独立保存，包括待复核、待联系、已联系、面试、Offer、已录用、不合适和人才库。

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
workbench_app.py               PySide6 产品入口与界面异常提示
workbench/
  qt_ui.py                     基础现代桌面壳
  qt_workspace.py              登录、建岗、招聘和候选人历史统一工作台
  qt_workspace_runtime.py      启动登录检查和可响应创建动作
  qt_job_dialog.py             结构化岗位创建对话框
  qt_theme.py                  企业视觉系统
  qt_dialogs.py                候选人复核对话框
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
tests_qt/                      创建岗位和桌面交互测试
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
python -m compileall -q workbench workbench_app.py app.py code tests tests_qt
python -m unittest discover -s tests -v
```

安装 PySide6 后还可以执行桌面交互测试：

```bash
python -m unittest discover -s tests_qt -p "test_*.py" -v
```

测试覆盖：

- 创建岗位按钮在登录前保持可响应
- 岗位创建对话框校验与结构化信息持久化
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
