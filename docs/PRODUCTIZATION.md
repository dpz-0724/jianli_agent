# V0.9 产品化说明

## 产品定位

V0.9 聚焦一个可验收闭环：招聘人员确认岗位标准后，系统在受控浏览器中执行智联搜索，候选人按岗位入池并生成可解释评估，最终由招聘人员复核和跟进。

它不是无人值守的“自动录用 Agent”，也不承诺规避平台验证或替代招聘判断。

## 用户流程

1. 创建岗位并粘贴 JD；
2. 系统生成岗位画像草稿；
3. 招聘人员检查必须能力、加分能力、学历、经验和地点；
4. 点击“确认岗位标准”；
5. 配置搜索页数、人数上限和浏览器；
6. 启动可视化搜索；
7. 遇到登录、验证码或特殊页面时暂停并人工接管；
8. 任务按页保存检查点；
9. 候选人进入本岗位收件箱；
10. 招聘人员保存复核结论、负责人、备注和下一次跟进。

## 浏览器支持矩阵

| 运行时 | 支持级别 | 说明 |
|---|---|---|
| 工作台 Chromium | 完整支持 | 与固定 Playwright 版本一同构建 |
| Microsoft Edge Stable | 备用支持 | 使用 Playwright `msedge` channel |
| Google Chrome Stable | 备用支持 | 使用 Playwright `chrome` channel |
| 自定义 Chromium 路径 | 高级模式 | 仅用于受控客户环境 |
| 360 / 搜狗 / QQ 浏览器 | 不支持 | 未纳入兼容测试 |
| Firefox / WebKit | 不支持 | 智联适配器仅验证 Chromium 系列 |

## 为什么采用 Sidecar 浏览器

V0.9 不将网页强行嵌入桌面窗口，而是让工作台和受控浏览器左右分屏：

- Playwright 保持完整协议和稳定性；
- 招聘人员能看到真实操作；
- 登录、验证码、弹窗和协议确认可人工处理；
- 浏览器可以独立重启，不拖垮工作台；
- 候选人来源始终在同一登录 Profile 中打开。

## 自动化控制

Browser Worker 支持：

- `SEARCH`
- `PAUSE`
- `RESUME`
- `TAKE_OVER`
- `CANCEL`
- `OPEN_URL`
- `BRING_TO_FRONT`
- `GET_BROWSER_STATUS`
- `RESET_BROWSER`
- `CLEAR_BROWSER_PROFILE`

暂停和取消为协作式控制，在页面和候选人检查点生效。每完成一页会保存页码、发现数量和查询信息。

## 岗位确认门禁

岗位画像有两种状态：

- `DRAFT`：系统解析或招聘人员修改后的草稿；
- `CONFIRMED`：招聘人员明确确认的版本。

只有 `CONFIRMED` 才能创建正式搜索任务。任何岗位字段修改都会重新变为 `DRAFT`。每次确认都会增加 `profile_version` 并记录确认时间。

## 安装与更新策略

源码安装使用 `setup.bat`。正式发布使用 PyInstaller `onedir`：

- 内含 Python 运行时；
- 内含 PySide6；
- 内含固定 Playwright 版本；
- 内含匹配的 Chromium；
- 不依赖客户预装 Google Chrome。

V0.9 尚未实现自动更新服务。客户试点必须使用版本化 ZIP，升级前先备份 `%LOCALAPPDATA%\RecruitmentWorkbench\workbench.db`。

## 仍需现场验证

- 智联页面选择器与候选人 UID；
- 企业代理、证书和浏览器策略；
- 登录态保存和清除；
- 连续运行稳定性；
- 页面变化诊断包；
- 安装签名与安全软件误报；
- 数据保存期限、导出和删除责任；
- 平台规则和知识产权边界。
