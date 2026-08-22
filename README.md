# 招聘自动化工作台 V1

面向一线招聘人员的本地优先工作台：以“岗位”为中心连接智联招聘搜索、候选人入池、证据化评估、人工复核和跟进记录。

当前版本为 **V1 Release Candidate**。它已经完成生产主链路重构和自动化测试，但真实智联页面、账号权限、平台规则及客户电脑环境仍需按验收清单进行现场验证。

## V1 解决什么问题

```text
创建岗位
  → 解析并确认岗位画像
  → 智联搜索任务
  → 候选人稳定入池与快照
  → PASS / REVIEW / CONFLICT 证据化评估
  → 招聘人员人工复核
  → 跟进、面试、人才库或归档
```

### 已实现

- 岗位隔离：不同岗位的候选人、评估、统计和导出互不污染
- 岗位画像：必须能力、加分能力、学历、经验和地点结构化
- 证据化评估：缺失信息进入 `REVIEW`，明确冲突进入 `CONFLICT`
- 招聘公平性基线：年龄、性别不参与自动评估和排序
- 候选人快照：同一候选人再次出现时更新资料并保留采集快照
- 专用浏览器线程：Playwright 对象只在 Browser Worker 内创建和使用
- 失败诊断：保存错误码、截图、页面 HTML、Trace 和运行元数据
- 人工复核：招聘阶段、负责人、备注、下次跟进和复核理由
- 岗位级 CSV 导出及审计记录
- SQLite WAL、外键、独立连接与显式写事务
- Windows / Linux、Python 3.10 / 3.12 的 CI 单元测试

## 目录结构

```text
app.py                     兼容启动入口
workbench_app.py           V1 主入口
workbench/
  models.py                领域模型与状态机
  evaluation.py            岗位解析与证据化评估
  database.py              岗位中心数据库与审计
  service.py               应用服务
  browser_worker.py        单线程浏览器任务执行器
  diagnostics.py           失败诊断包
  demo.py                  离线演示数据
  ui.py                    招聘工作台桌面界面
code/
  bot.py / searcher.py     现有智联自动化适配层
  recruitment_engine.py    V1 评估引擎兼容导出
tests/                     领域、数据库、岗位隔离和服务测试
docs/                      架构、验收与交付说明
```

## 运行

### Windows 首次安装与运行

首次使用：

```bat
setup.bat
```

之后启动：

```bat
run.bat
```

### 源码运行

要求 Python 3.10 或更高版本，并已安装 Chrome。

```bash
python -m pip install -r requirements.txt
python app.py
```

首次进行智联搜索时，应用会打开独立浏览器窗口。完成扫码或短信登录后，回到工作台点击“登录完成，继续搜索”。登录状态保存在：

```text
%LOCALAPPDATA%\RecruitmentWorkbench\browser_profile
```

工作台数据保存在：

```text
%LOCALAPPDATA%\RecruitmentWorkbench\workbench.db
```

失败诊断包保存在：

```text
%LOCALAPPDATA%\RecruitmentWorkbench\diagnostics
```

## 测试

```bash
python -m compileall -q workbench workbench_app.py app.py
python -m unittest discover -s tests -v
```

当前自动化测试覆盖：

- 两个岗位候选人和评估完全隔离
- 经验区间不会被错误判定为满足硬性要求
- 多城市使用“任一地点匹配”
- 年龄、性别变化不影响评估结果
- 重复抓取更新候选人并新增快照
- 岗位导出不会混入其他岗位数据
- 候选人入池后生成岗位级评估

## 构建

```bat
build.bat
```

构建前会执行单元测试，成功后生成：

```text
dist\招聘自动化工作台.exe
```

## 交付边界

V1 是招聘人员的决策辅助工具，不进行最终录用决策，也不应自动淘汰信息缺失的候选人。

正式商用前必须完成：

1. 客户账号和真实智联页面的端到端验收；
2. 平台服务规则、数据处理授权和保存期限确认；
3. 客户电脑上的安装、升级、备份和恢复测试；
4. 候选人数据访问、导出、删除和审计责任确认；
5. 生产仓库与研究/逆向材料隔离，并完成知识产权审查。

详细门禁见 [`docs/DELIVERY_CHECKLIST.md`](docs/DELIVERY_CHECKLIST.md) 和 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。
