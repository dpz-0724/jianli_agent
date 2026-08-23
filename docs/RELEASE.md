# V0.9.1 Pilot Candidate 发布流程

## 1. 发布条件

发布负责人必须确认：

- PR 仍标记为 Pilot Candidate，而不是 GA；
- `CI` 与 `Desktop Smoke` 全部通过；
- 当前提交 SHA 已记录；
- `docs/DELIVERY_CHECKLIST.md` 中代码基线完成；
- 发布包仅发给已签署 Pilot 约定的客户；
- 真实账号、数据授权和平台规则已确认。

## 2. 本地工程门禁

```bat
.venv\Scripts\python.exe -m compileall -q workbench workbench_app.py app.py code tests tests_qt
.venv\Scripts\python.exe -m unittest discover -s tests -v
set QT_QPA_PLATFORM=offscreen
set PYTHONUTF8=1
.venv\Scripts\python.exe -m unittest discover -s tests_qt -p "test_*.py" -v
```

必须覆盖：

- 岗位创建；
- 逐页候选人持久化；
- 检查点；
- 身份绑定；
- 候选人合并与合并前备份；
- 数据库备份恢复；
- 浏览器关闭后恢复；
- 结构化规则覆盖；
- 过期评估和操作人审计。

## 3. 可重复 RC 构建

推荐在 GitHub Actions 中手动运行：

```text
Actions → Package RC → Run workflow
```

工作流会：

1. 使用固定 Python 3.10；
2. 安装固定依赖；
3. 运行 `build.bat`；
4. 下载匹配 Playwright 版本的 Chromium；
5. 构建 PyInstaller `onedir` 发布目录；
6. 检查 EXE 和 ZIP；
7. 上传保留 14 天的构建产物。

本地也可执行：

```bat
build.bat
```

产物：

```text
dist\招聘自动化工作台\
dist\招聘自动化工作台-v0.9.zip
```

发布目录内必须完整保留：

- `招聘自动化工作台.exe`；
- `_internal`；
- `runtime-browsers`；
- 其他 PyInstaller 依赖。

不得只复制单个 EXE。

## 4. 发布包检查

在一台没有源码、Python 和 Chrome 的干净 Windows 电脑执行：

1. 解压 ZIP；
2. 启动 EXE；
3. 检查工作台 Chromium；
4. 登录智联；
5. 创建并确认岗位；
6. 执行 1 页 / 20 人任务；
7. 备份数据库；
8. 重启应用并恢复任务。

检查发布目录没有包含：

- 候选人数据库；
- 浏览器 Profile；
- 日志；
- 诊断包；
- 调试脚本；
- 逆向转储；
- 本地账号或配置。

## 5. 生成安装程序

安装 Inno Setup 6 后运行：

```bat
build_release.bat
```

生成：

```text
dist\installer\招聘自动化工作台-v0.9-Setup.exe
```

安装位置：

```text
%LOCALAPPDATA%\Programs\RecruitmentWorkbench
```

用户数据独立保存在：

```text
%LOCALAPPDATA%\RecruitmentWorkbench
```

卸载程序默认不删除用户数据，避免误删。客户退出 Pilot 时必须明确执行保留、归档或删除。

## 6. 签名与校验

正式发给客户前签署：

- 主 EXE；
- 安装程序；
- 需要签名的 DLL 或辅助程序。

同时生成：

```powershell
Get-FileHash -Algorithm SHA256 <发布文件>
```

发布记录必须包含：

- 版本；
- Git commit SHA；
- 构建工作流 run ID；
- 构建时间；
- SHA-256；
- 签名证书信息；
- 发布客户；
- 发布负责人。

未签名构建只能用于内部或客户明确同意的受控 Pilot。

## 7. 升级

升级前：

1. 停止所有招聘任务；
2. 使用应用备份数据库；
3. 核对备份完整性；
4. 记录当前版本和数据库 schema；
5. 保留上一版安装包或 ZIP；
6. 在副本上验证 V1/V2 → V3 迁移；
7. 安装新版本；
8. 检查岗位、候选人、评估、快照、身份和审计。

## 8. 回滚

发生以下情况立即回滚：

- 候选人丢失；
- 检查点跳过未保存页；
- 数据库恢复不一致；
- 大量身份误合并；
- 发布包无法启动；
- 浏览器持续无法恢复。

回滚流程：

1. 停止工作台；
2. 保存当前日志和诊断包；
3. 恢复上一版程序；
4. 使用升级前备份恢复数据库；
5. 执行完整性检查；
6. 核对关键岗位和候选人；
7. 记录事故和影响范围。

## 9. Pilot 发布

客户 Pilot 必须按照：

- `docs/ACCEPTANCE.md`；
- `docs/PILOT_RUNBOOK.md`；
- `docs/SECURITY_BASELINE.md`；
- `docs/DELIVERY_CHECKLIST.md`。

完成两周运行和所有门禁后，才能将构建标记为 `V0.9.1 Pilot`。V1.0 GA 需要至少两个客户环境和完整合规审查。
