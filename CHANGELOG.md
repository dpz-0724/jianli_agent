# Changelog

## V0.9 Productization Alpha

- 主界面由 Tkinter 工程界面迁移到 PySide6 现代桌面工作台
- 新增岗位画像草稿 / 明确确认门禁与版本记录
- 新增搜索页数、人数上限和浏览器运行时配置
- 默认支持工作台 Chromium，Edge / Chrome 作为备用
- 新增 Sidecar 左右分屏、显示浏览器、暂停、人工接管、继续和安全停止
- 新增按页检查点及未完成任务恢复入口
- 候选人来源改为在同一受控浏览器 Profile 中打开
- 移除固定 User-Agent 和自动化规避启动参数
- 新增浏览器中心、本地设置、数据库备份恢复和登录状态清理
- 新增 V1 数据库增量迁移
- Playwright 与 PySide6 使用固定版本
- 构建改为携带 Chromium 的 PyInstaller onedir 发布包
- 扩展 Windows / Linux、Python 3.10 / 3.12 测试与桌面导入检查

## V0.8 Engineering Baseline

- 建立岗位中心数据模型
- 建立候选人快照与岗位级评估
- 新增 PASS / REVIEW / CONFLICT
- Playwright 改为专用 Browser Worker 线程
- 新增诊断包、审计和岗位级导出
