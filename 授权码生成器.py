# -*- coding: utf-8 -*-
"""授权码生成器 —— 仅卖方使用，绝不随软件分发给客户。

用法（命令行）：
  python 授权码生成器.py 客户名 机器码 [天数]
    客户名：如 某某人力资源公司
    机器码：客户软件激活界面显示的 XXXX-XXXX-XXXX-XXXX；填 * 表示不绑定机器
    天数：授权有效天数，0 或省略表示永久

也可以直接运行后按提示交互输入。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

_PRIV = pathlib.Path(__file__).parent / "tools" / "_vendor_private.key"


def main() -> None:
    if not _PRIV.exists():
        print("❌ 未找到私钥 tools/_vendor_private.key —— 请先运行 tools/_gen_vendor_keys.py")
        sys.exit(1)
    priv_hex = _PRIV.read_text(encoding="utf-8").strip()

    from workbench.license_mgr import make_license

    if len(sys.argv) >= 3:
        customer, machine = sys.argv[1], sys.argv[2]
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    else:
        customer = input("客户名: ").strip()
        machine = input("机器码(XXXX-XXXX-XXXX-XXXX，* 不绑定): ").strip() or "*"
        days = int((input("有效天数(0=永久): ").strip() or "0"))

    code = make_license(priv_hex, customer, machine, days)
    print("\n========== 授权码（整段复制发给客户） ==========")
    print(code)
    print("=============================================")
    print(f"客户:{customer}  机器:{machine}  期限:{'永久' if days<=0 else str(days)+'天'}")


if __name__ == "__main__":
    main()
