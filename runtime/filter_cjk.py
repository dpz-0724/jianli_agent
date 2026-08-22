# -*- coding: utf-8 -*-
import re

src = r"E:\终身学习\云只智联_reverse\runtime\pid99568_cjk.txt"
anchor_words = ("登录 注册 密码 账号 用户 设备 绑定 激活 验证 手机 微信 简历 数据 同步 导出 导入 通知 "
"消息 设置 退出 保存 删除 连接 服务器 网络 版本 更新 升级 成功 失败 错误 提示 确认 取消 确定 "
"查看 打开 关闭 开始 停止 清空 新增 编辑 查询 搜索 检测 驱动 打印 图标 显示 隐藏 地区 办公 "
"工作 效率 入职 邀约 历史 软件 文件 路径 目录 数据库 套件 服务 当前 重新 运行 程序 管理员 "
"身份 复制 快捷 一键 实时 已加 兼容 无效 使用 下载 上传 切换 卡 抓取 采集 去重 邀请 沟通 "
"老板 招聘 猎头 号码 添加 分组 批量 授权 到期 续费 充值 支付 订单 客户 管理 中心 列表 详情 "
"状态 刷新 扫描 蓝牙 串口 眼镜 消防 巡检 摄像头 视频 音频 记录 统计 报表 模板 帮助 关于 "
"反馈 意见 检查 完成 安装 卸载 启动 运行 出错 异常 警告 记住 忘记 找回 复制 选中 全选 导出全部"
).split()

anchors = anchor_words

def is_good(s):
    L = len(s)
    if not (2 <= L <= 40):
        return False
    cjk = sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
    if cjk < 2:
        return False
    ratio = cjk / L
    if ratio < 0.5:
        return False
    # anchored keyword OR full-sentence
    if any(w in s for w in anchors):
        return True
    if L >= 6 and ratio >= 0.9:
        return True
    return False

kept = []
seen = set()
for line in open(src, encoding="utf-8", errors="ignore"):
    s = line.strip()
    if is_good(s) and s not in seen:
        seen.add(s)
        kept.append(s)

kept.sort(key=lambda x: -len(x))
outp = r"E:\终身学习\云只智联_reverse\runtime\filtered_cjk.txt"
open(outp, "w", encoding="utf-8").write("\n".join(kept))
print("filtered:", len(kept), "->", outp)