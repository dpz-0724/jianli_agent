# 招聘自动化工作台 V1 架构

## 1. 架构原则

1. **岗位中心**：候选人的评估、阶段、备注和导出必须绑定岗位。
2. **浏览器单一所有者**：Playwright Page、Context 和 Browser 只在 Browser Worker 线程中使用。
3. **证据优先**：评估必须说明命中项、缺失项和冲突项，不能只输出一个分数。
4. **人工确认**：缺失信息进入 REVIEW；招聘人员保留最终复核和覆盖权。
5. **本地优先**：V1 使用本地 SQLite 和本地浏览器登录态，降低集成复杂度。
6. **失败可诊断**：所有自动化失败必须输出错误码和诊断目录。

## 2. 运行结构

```text
Tkinter UI
   │
   ├── RecruitmentService
   │      ├── Requirement Parser
   │      ├── Assessment Engine
   │      └── WorkbenchDB
   │
   └── Command Queue
          │
          ▼
      Browser Worker Thread
          ├── CandidateSearcher
          ├── Playwright Context
          └── Diagnostic Capture
```

## 3. 数据模型

```text
jobs
  ├── sourcing_runs
  └── job_candidates
         ├── assessments
         ├── review_decisions
         └── follow_ups

candidates
  └── candidate_snapshots
```

### 关键分离

- `candidates`：候选人的跨岗位主身份和最新可见资料
- `candidate_snapshots`：每次采集的原始快照
- `job_candidates`：候选人与特定岗位的关系
- `assessments`：某一版岗位画像和引擎下的评估结果

因此，同一个候选人可以同时属于多个岗位，但每个岗位拥有独立评估和跟进状态。

## 4. 评估状态

| 状态 | 含义 | 系统行为 |
|---|---|---|
| PASS | 已有信息未发现冲突 | 排在本岗位优先复核区 |
| REVIEW | 信息缺失或区间不确定 | 必须由招聘人员核验 |
| CONFLICT | 有明确证据不满足硬性条件 | 显示冲突证据，仍保留人工决定 |

匹配度仅用于同一岗位内部排序，不用于跨岗位比较，也不能替代人工录用决定。

## 5. 浏览器线程边界

UI 不得直接调用任何 Playwright 对象。所有操作通过 `BrowserCommand` 进入专用线程，结果通过 `BrowserEvent` 返回。

支持的核心事件：

- `STATUS`
- `PROGRESS`
- `NEED_LOGIN`
- `COMPLETED`
- `FAILED`

失败时生成：

```text
error.json
screenshot.png
page.html
trace.zip
```

## 6. 数据库并发

每个 Repository 操作创建独立 SQLite 连接，启用：

- WAL
- foreign_keys
- busy_timeout
- BEGIN IMMEDIATE 写事务

禁止 UI 和 Browser Worker 长期共享同一个 SQLite Connection。

## 7. 下一阶段扩展点

V1 现场验收完成后，再考虑：

- 智联选择器合同测试和自动健康检查
- 候选人平台 UID 的更稳定提取
- 安装包签名与自动更新
- 企业 ATS 接口
- 多账号权限与团队协作
- 受控的其他招聘平台适配器
