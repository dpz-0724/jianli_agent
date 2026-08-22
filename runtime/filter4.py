# -*- coding: utf-8 -*-
"""Final filter: GB2312 + length + functional anchor words to isolate real UI strings."""
src = r"E:\终身学习\云只智联_reverse\runtime\pid90364_cjk.txt"

anchor_words = """
登录 注册 密码 账号 用户 设备 绑定 激活 验证 手机 微信 简历 数据 同步 导出 导入 通知 消息
设置 退出 保存 删除 连接 服务器 网络 版本 更新 升级 成功 失败 错误 提示 确认 取消 确定 查看
打开 关闭 开始 停止 清空 新增 编辑 查询 搜索 检测 驱动 打印 图标 显示 隐藏 地区 办公 工作
效率 入职 邀约 历史 软件 文件 路径 目录 数据库 套件 服务 当前 重新 运行 程序 管理员 身份
复制 快捷 一键 实时 已加 兼容 无效 使用 下载 上传 切换 卡密 抓取 采集 去重 邀请 沟通 招聘
猎头 号码 添加 分组 批量 授权 到期 续费 充值 支付 订单 客户 管理 中心 列表 详情 状态 刷新
扫描 帮助 关于 检查 完成 安装 卸载 出错 异常 警告 记住 忘记 找回 选中 更换 通知区 已入职
简历导 同步简历 无效设备 没有该设备 设备仍 设备已 请输入 文件名 切换设备 切换地区 提升工作
""".split()

def gb2312_ok(c):
    try:
        c.encode("gb2312"); return True
    except Exception:
        return False

kept = []
seen = set()
for line in open(src, encoding="utf-8", errors="ignore"):
    s = line.strip()
    L = len(s)
    if not (3 <= L <= 44):
        continue
    cjk = [c for c in s if "\u4e00" <= c <= "\u9fff"]
    if len(cjk) < 2:
        continue
    if (len(cjk) / L) < 0.6:
        continue
    g = sum(1 for c in cjk if gb2312_ok(c))
    if g / len(cjk) < 0.9:
        continue
    if not any(w in s for w in anchor_words):
        continue
    if s not in seen:
        seen.add(s)
        kept.append(s)

kept.sort(key=lambda x: -len(x))
out = r"E:\终身学习\云只智联_reverse\runtime\final_cjk.txt"
open(out, "w", encoding="utf-8").write("\n".join(kept))
print("kept:", len(kept), "->", out)