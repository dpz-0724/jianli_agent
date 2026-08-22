# Changelog

## 1.0.0-rc1

- 将单一候选人池重构为岗位中心数据模型
- 增加搜索任务、候选人快照、岗位候选人关系和版本化评估
- 接入 PASS / REVIEW / CONFLICT 证据化评估
- 删除年龄、性别对评估和排序的影响
- 修复经验区间误放行和多城市匹配问题
- 使用专用 Browser Worker 隔离 Playwright 线程
- 增加自动化失败截图、HTML、Trace 和错误元数据
- 增加人工复核、跟进、岗位级导出和审计
- 增加跨岗位隔离、数据更新和评估正确性测试
- 增加 Windows / Linux CI
