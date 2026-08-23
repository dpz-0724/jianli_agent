# V0.9.1 Pilot Readiness Gate

## 目的

在把 Windows 发布包交给客户前，先验证“安装包自身是否完整”。该自检不登录智联、不执行真实搜索，也不读取客户候选人数据。

它验证：

- 发布包内是否包含匹配版本的 Playwright Chromium；
- 当前用户数据目录是否可写；
- SQLite 建库、迁移、备份、删除、恢复和完整性检查；
- 产品设置能否可靠保存并重新加载；
- 发布包、数据库 Schema 和产品版本是否一致。

## 运行方式

源码环境：

```bat
python app.py --self-test --report pilot-readiness.json
```

打包环境：

```bat
招聘自动化工作台.exe --self-test --report pilot-readiness.json
```

退出码：

- `0`：离线交付自检通过；
- `2`：至少一个必需检查未通过；
- `3`：自检程序本身异常。

报告中的 `overall` 必须为 `PASS`。报告同时保留 `field_validation_required=true`，避免把离线自检误认为真实平台验收。

## 构建门禁

`build.bat` 在生成 PyInstaller onedir 目录后，会直接运行打包后的 EXE 自检。只有以下条件同时满足才生成发布 ZIP：

1. 单元测试通过；
2. Qt 交互测试通过；
3. Chromium 被打入发布目录；
4. 打包 EXE 能执行自检；
5. SQLite 备份恢复往返成功；
6. 自检 JSON 为 `PASS`。

GitHub Actions 的 `Package RC` 工作流也执行同一构建门禁，并上传 Windows RC 产物。

## 自检不能替代的现场门禁

以下项目仍必须在授权客户环境完成：

- 智联账号真实登录与登录态复用；
- 连续真实搜索和分页采集；
- 平台 UID、页面选择器和搜索配额；
- 验证码、浏览器关闭、网络中断后的接管与恢复；
- 企业代理、证书、安全软件和浏览器策略；
- 客户黄金样本评估；
- 安装包签名、升级和回滚；
- 数据授权、保存期限、平台规则和知识产权审查。

离线自检通过但现场门禁未完成时，版本状态仍是 `Pilot Candidate`，不能标记为 GA。
