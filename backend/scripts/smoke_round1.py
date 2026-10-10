"""第 1 轮冒烟：一条真实"输入 → 工具 → 结果"链路（Mock 先行，全程不调模型）。

第 1 轮的"输入"是结构化报修请求；第 2 轮起，这个输入由模型从企业自然语言
会话里提取。跑法（项目根目录）：
    .venv\\Scripts\\python scripts\\smoke_round1.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acs.seed import seed
from acs.tools import create_repair_ticket, query_maintenance

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def show(title: str, result: dict) -> None:
    print(f"\n=== {title} ===")
    print(result)


def main() -> None:
    print("1) 重置并写入种子数据（三张前提表 + web:main 绑 internal）")
    print("  ", seed(reset=True))

    print("\n2) 报修链路：企业结构化输入 → create_repair_ticket → 工单落库")
    show(
        "报修：示例企业甲 DEMO-GR75-0001 机器异响（high）",
        create_repair_ticket(
            "示例企业甲", "DEMO-GR75-0001", "机器异响", "high",
            scope_key="web:main",
        ),
    )

    print("\n3) 保养查询链路：query_maintenance → 台账到期计算")
    show("查询：DEMO-GR75-0002（预期已过期）",
         query_maintenance("DEMO-GR75-0002", scope_key="web:main"))
    show("查询：DEMO-EP30-0007（预期正常）",
         query_maintenance("DEMO-EP30-0007", scope_key="web:main"))

    print("\n4) 失败路径（信封里带'人话+原因+下一步'）")
    show("报修查无此设备",
         create_repair_ticket("某公司", "AC-XXXX-9999", "异响", scope_key="web:main"))
    show("报修缺信息", create_repair_ticket("", "DEMO-GR75-0001", "", scope_key="web:main"))
    show("未绑定会话（fail-closed）",
         query_maintenance("DEMO-GR75-0002", scope_key="web:some-stranger"))

    print("\n第 1 轮冒烟完成：链路 = 结构化输入 → 工具 → PostgreSQL 落库/查询 → 信封返回"
          "（第 3 轮起带调用者身份隔离）")


if __name__ == "__main__":
    main()
