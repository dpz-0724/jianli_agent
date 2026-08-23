# 招聘自动化工作台 V0.9.1

面向企业招聘人员的本地优先工作台。系统以岗位为中心，连接智联招聘受控浏览器、候选人采集、证据化评估、人工复核和跟进记录。

当前状态为 **Pilot Candidate**：核心数据正确性、断点恢复、备份恢复、候选人身份和桌面交互已经进入自动化验证；真实智联账号、客户 Windows 环境、平台规则和发布签名仍需现场验收。未完成现场门禁前，不应标记为正式商用版或 V1.0 GA。

## 日常主流程

```text
登录智联
→ 创建或选择岗位
→ 填写结构化条件与完整 JD
→ 招聘人员确认岗位标准
→ 配置搜索计划并开始招聘
→ 观察浏览器 / 暂停 / 人工接管 / 继续 / 停止
→ 候选人按页安全入库
→ 去重、评估、人工复核与跟进
```

登录、岗位要求、搜索计划和自动化控制集中在同一个主工作台。任务页用于恢复和诊断，系统页用于浏览器设置、数据备份与恢复。

## 当前已实现

### 1. 岗位标准与招聘规则

岗位创建与编辑支持：岗位名称、智联搜索关键词、完整岗位 JD、最低学历、最低经验、工作地点、必须能力和加分能力。

岗位画像分为 `DRAFT` 和 `CONFIRMED`。只有招聘人员明确确认后才允许开始招聘；修改任何条件后自动回到草稿。

结构化确认值高于 JD 自动解析结果：

- 选择“学历不限”会真正取消学历硬性条件；
- 手动填写 3 年经验不会被 JD 中的 5 年重新覆盖；
- 智联搜索词用于召回，不会自动变成必须能力；
- 必须能力和加分能力由招聘人员最终确认。

> 当前智联召回阶段只自动填写搜索关键词。学历、经验、地点和能力条件用于采集后的本地评估，不会伪装成已经操作了智联网页筛选器。

### 2. 候选人按页安全持久化

每完成一页即执行原子事务：

```text
本页候选人
→ 身份解析与去重
→ 候选人快照
→ 岗位关联
→ 评估结果
→ 页面检查点
→ 提交事务
```

只有数据库提交成功后，任务才推进检查点。浏览器崩溃、应用退出或用户安全停止时，可以从最近已提交页恢复，不会因为只保存页码而丢失前面已采集的候选人。

### 3. 去重、历史识别和人工纠错

身份匹配优先级：

1. 智联平台 UID；
2. 候选人专属来源身份；
3. 精确字段指纹；
4. 低置信度稳定签名提示。

支持同岗位重复更新、UID 后补绑定、跨岗位历史标记、人工合并重复候选人。合并前自动创建数据库备份，合并和人工操作写入审计记录。

人工处理阶段独立保存：待复核、待联系、已联系、面试、Offer、已录用、不合适、人才库。

### 4. 证据化评估

系统输出：建议优先查看、信息待核验、存在明确冲突。

- 年龄、性别和联系方式不参与自动评估；
- 缺失信息进入人工核验，不自动淘汰；
- 经验区间不能确认时不错误放行；
- 明确学历或经验不足才判定为冲突；
- 每个结果保存原因、岗位标准版本和评估引擎版本；
- 候选人资料在评估后更新时，旧评估自动标记为待重新评估。

### 5. 可视化受控浏览器

默认浏览器顺序：工作台自带 Playwright Chromium、Microsoft Edge、Google Chrome、自定义 Chromium 路径。

V0.9.1 不承诺支持 360、搜狗、QQ 浏览器、Firefox 或 WebKit。

支持左右分屏、显示浏览器、暂停、人工接管、继续、安全停止、从已提交页恢复、同一登录 Profile 打开来源、浏览器被关闭后的自动重建、重置浏览器和清除登录状态。

应用不固定伪造 User-Agent，也不使用自动化规避启动参数。

### 6. 数据备份、恢复和审计

数据库使用 SQLite WAL、外键、独立连接和显式事务。备份恢复包括 SQLite Online Backup API、WAL checkpoint、完整性检查、恢复前自动备份、原子替换、V1/V2 到 V3 增量迁移和备份元数据。当前 Windows 用户自动写入操作人字段。

敏感数据默认位于：

```text
%LOCALAPPDATA%\RecruitmentWorkbench\workbench.db
%LOCALAPPDATA%\RecruitmentWorkbench\settings.json
%LOCALAPPDATA%\RecruitmentWorkbench\browser_profiles
%LOCALAPPDATA%\RecruitmentWorkbench\backups
%LOCALAPPDATA%\RecruitmentWorkbench\diagnostics
%LOCALAPPDATA%\RecruitmentWorkbench\logs
```

## 浏览器与数据边界

- 使用客户本人授权的智联招聘账号；
- 不自动作出录用或淘汰决定；
- 不把候选人数据上传到本项目服务器；
- 诊断截图、HTML 和 Trace 可能含候选人信息，外发前必须脱敏；
- 当前版本适用于单用户、单台受控 Windows 电脑的 Pilot；
- 尚未提供企业统一身份认证、多租户权限和字段级数据库加密。

## 源码运行

```bat
setup.bat
run.bat
```

或：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

## 构建发布目录

```bat
build.bat
```

构建过程会编译生产模块、运行领域/数据库/Qt 测试、下载匹配 Chromium，并使用 PyInstaller `onedir` 生成：

```text
dist\招聘自动化工作台\招聘自动化工作台.exe
dist\招聘自动化工作台-v0.9.zip
```

GitHub 还提供手动 `Package RC` 工作流，用于生成可追踪的 Windows RC 构建产物。正式发布包不要求客户预装 Python 或 Google Chrome。

## 测试

```bash
python -m compileall -q workbench workbench_app.py app.py code tests tests_qt
python -m unittest discover -s tests -v
```

Windows Qt 测试：

```bat
set QT_QPA_PLATFORM=offscreen
set PYTHONUTF8=1
python -m unittest discover -s tests_qt -p "test_*.py" -v
```

自动测试覆盖跨岗位隔离、每页持久化、身份绑定、人工合并及备份、数据库备份恢复、结构化条件覆盖、过期评估、操作人审计、浏览器自动恢复和创建岗位完整路径。

## 发布门禁

当前代码可以进入受控客户 Pilot 验证，但不能直接标记为正式商用版。

Pilot 前必须完成：

1. 干净 Windows 10/11 电脑，无 Python、无 Chrome 安装测试；
2. 使用授权智联账号连续真实搜索不少于 20 次；
3. 人为关闭浏览器、断网和结束应用后的恢复测试；
4. 任务恢复时验证候选人零丢失、零重复入池；
5. 客户黄金样本评估和字段准确性确认；
6. 平台 UID 稳定性和页面改版诊断验证；
7. 企业代理、证书和安全软件验证；
8. 安装包签名、升级和回滚；
9. 平台服务规则、数据授权、保存期限和知识产权审查。

详细说明见：

- `docs/DELIVERY_CHECKLIST.md`
- `docs/ACCEPTANCE.md`
- `docs/PILOT_RUNBOOK.md`
- `docs/SECURITY_BASELINE.md`
- `docs/RELEASE.md`
