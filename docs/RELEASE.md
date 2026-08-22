# V0.9 发布流程

## 1. 运行工程门禁

```bat
.venv\Scripts\python.exe -m compileall -q workbench workbench_app.py app.py code tests
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GitHub Actions 的 Windows / Linux、Python 3.10 / 3.12 和 Qt 离屏窗口检查必须全部通过。

## 2. 生成自带浏览器的发布目录

```bat
build.bat
```

该步骤下载与固定 Playwright 版本匹配的 Chromium，并生成：

```text
dist\招聘自动化工作台\
dist\招聘自动化工作台-v0.9.zip
```

发布目录内必须保留所有 `_internal` 和 `runtime-browsers` 文件，不得只复制单个 EXE。

## 3. 生成安装程序

安装 Inno Setup 6 后运行：

```bat
build_release.bat
```

生成：

```text
dist\installer\招聘自动化工作台-v0.9-Setup.exe
```

安装程序使用当前 Windows 用户权限安装到 `%LOCALAPPDATA%\Programs\RecruitmentWorkbench`，不要求管理员权限。

## 4. 签名

正式发给客户前，使用企业代码签名证书签署：

- 主 EXE；
- 安装程序；
- 如发布 ZIP，同时提供 SHA-256 校验值。

未签名构建只能用于内部测试。

## 5. 升级和回滚

升级前：

1. 在应用“系统与数据”页面备份数据库；
2. 记录当前版本；
3. 保留上一版安装包或 ZIP；
4. 验证新版本能读取旧数据库并完成迁移。

回滚时恢复上一版程序；数据库只能在确认新旧 schema 兼容时直接复用，否则使用升级前备份。

## 6. 客户试点

发布到客户前按 `docs/ACCEPTANCE.md` 执行：

- 无 Python / Chrome 启动；
- 智联登录和 10 次连续搜索；
- 暂停、人工接管、恢复；
- 候选人 UID；
- 数据备份恢复；
- 企业代理、证书和安全软件；
- 平台规则和数据授权。
