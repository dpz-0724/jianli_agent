# 招聘自动化工作台 V0.9 架构

## 设计目标

1. 岗位之间的数据、评估和跟进完全隔离；
2. 岗位画像必须经过招聘人员确认；
3. 浏览器自动化可观察、可暂停、可人工接管、可停止；
4. 页面变化必须留下可复现诊断；
5. 客户没有 Google Chrome 时仍可使用工作台自带 Chromium；
6. UI、业务服务、数据层和平台适配器保持分离。

## 分层

```text
PySide6 Desktop
  ├── 岗位工作台
  ├── 候选人收件箱
  ├── 自动化任务
  └── 系统与数据
          │
          ▼
RecruitmentService
  ├── 岗位画像草稿 / 确认门禁
  ├── 搜索计划
  ├── 候选人入池
  └── 证据化评估
          │
          ├───────────────► WorkbenchDB / SQLite
          │                  ├── jobs
          │                  ├── sourcing_runs
          │                  ├── candidates / snapshots
          │                  ├── job_candidates
          │                  ├── assessments
          │                  ├── review_decisions
          │                  ├── follow_ups
          │                  └── audit_events
          │
          ▼
BrowserWorker（单一线程所有权）
  ├── command queue
  ├── pause / resume / takeover / cancel
  ├── page checkpoints
  └── diagnostics
          │
          ▼
ProductCandidateSearcher
  ├── 工作台 Chromium
  ├── Edge channel
  ├── Chrome channel
  ├── persistent profile
  └── 智联页面解析适配器
```

## 岗位画像状态

```text
创建 / 修改 / 重新解析
          ↓
        DRAFT
          ↓ 招聘人员确认
      CONFIRMED Vn
          ↓ 修改任意岗位字段
        DRAFT
```

`DRAFT` 不允许创建正式搜索任务。每次确认增加 `profile_version`，记录确认时间和确认人。

## 浏览器所有权

Playwright 对象只允许在 `BrowserWorker` 线程内创建和使用。UI 通过命令队列发送：

- SEARCH
- PAUSE
- RESUME
- TAKE_OVER
- CANCEL
- OPEN_URL
- BRING_TO_FRONT
- GET_BROWSER_STATUS
- RESET_BROWSER
- CLEAR_BROWSER_PROFILE

暂停和取消由线程事件控制，在候选人和页面检查点协作生效。UI 不直接持有 Page、Context 或 Browser。

## Sidecar 而非嵌入式网页

V0.9 将受控浏览器作为独立窗口与工作台左右分屏，而不是用 WebView 重新承载智联页面。这样可以：

- 保留完整 Playwright 协议；
- 使用同一持久化登录 Profile；
- 允许人工处理登录、验证码和弹窗；
- 浏览器崩溃时独立重启；
- 避免 WebView 与 Playwright 两套 Cookie 和运行时。

## 搜索检查点

每完成一页，Browser Worker 发送：

```json
{
  "last_completed_page": 3,
  "found_count": 87,
  "query": "Java 后端"
}
```

数据库保存 `last_page` 和 `checkpoint_json`。未完成任务可以从下一页重新搜索，已入池候选人通过平台 UID 或候选人指纹去重。

## 浏览器运行时

默认使用与固定 Playwright 版本匹配的 Chromium。构建脚本把浏览器放在 `runtime-browsers` 并打入 PyInstaller onedir 发布目录。

运行顺序：

```text
requested managed / edge / chrome / custom
  → requested runtime
  → managed Chromium fallback
  → Edge fallback
  → Chrome fallback
```

不使用固定 User-Agent，也不使用规避自动化检测的启动参数。

## 数据安全

- SQLite 数据保存在 `%LOCALAPPDATA%\RecruitmentWorkbench`；
- 浏览器 Cookie 保存在独立 `browser_profiles`；
- 导出、人工复核和关键岗位操作写入审计表；
- 诊断包可能包含页面内容，交付时必须限制访问并设置清理期限；
- 数据库支持一致性备份和完整性校验恢复；
- 年龄、性别和联系方式不进入匹配模型。

## 发布边界

V0.9 仍需在授权客户环境完成平台页面、账号权限、企业代理、安装签名、升级回滚和数据授权验证。未通过门禁前不标记为正式 GA。
