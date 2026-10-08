"""意图分类能力测评（第 3 轮 · 证明层）。

测什么：分诊台的意图路由（repair 报修 / maintenance 保养 / progress 进度 / other 其他或模糊）。
怎么测：把会话输入单独喂给同一个模型（deepseek-flash），用蒸馏自任务书第三节的
分类提示词，temperature=0，要求只输出 JSON。这是"能力测评"——慢、花钱、低频跑
（发版前/提示词改动后），日常守门员是工具层的 pytest 回归。

近似性声明：真实系统里路由发生在 Pi 运行时完整上下文中（含四段提示词与历史
对话）；本脚本用同一模型+蒸馏提示词做代理评测，结论是"模型在干净输入下的
路由能力"，不是端到端通过率。标注=设计推断，已向用户说明。

回流规则（评测失败只改 Prompt 不算修复）：
  1. 问法在集内但分错 → 先看错成什么：与其他类混淆→改提示词定义/给示例（编排层）；
  2. 工具返回内容错误 → 回第 1 轮修工具（材料层），不在这里兜；
  3. 发现该答没答的新问法 → 先进 intent_cases.json 再改代码（评测集是唯一事实源）；
  4. 每次修复必须附重跑报告对比（reports/ 留档）。

用法（项目根目录）：
  .venv\\Scripts\\python evals\\run_intent_eval.py --dry-run     # 不出网，校验集与提示词
  .venv\\Scripts\\python evals\\run_intent_eval.py               # 全量 30 条真模型
  .venv\\Scripts\python evals\\run_intent_eval.py --limit 5      # 小样本试跑
环境变量（或项目根 .env）：DEEPSEEK_API_KEY 必填；
  DEEPSEEK_BASE_URL 默认 https://api.deepseek.com/anthropic；
  DEEPSEEK_MODEL 默认 deepseek-flash。
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = Path(__file__).resolve().parent / "intent_cases.json"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
VALID_INTENTS = ("repair", "maintenance", "progress", "other")

SYSTEM_PROMPT = """你是空压机售后服务分诊台的意图分类器。把客户的一条消息分成四类之一：
- repair：报修。设备故障、要派人来修、描述任何异常现象（异响/漏气/不出气/报警/异味等），含情绪化催促。
- maintenance：保养咨询。保养周期、到期与否、保养项目、保养提醒。
- progress：进度查询。工单/报修单/零件/工程师上门的进展，报不报工单号都算。
- other：其他或分不清。费用、退货、投诉、闲聊、身份询问；以及信息太少无法判断的模糊消息——模糊必须归 other，不许猜。

只输出一个 JSON 对象，不要输出任何其他文字：
{"intent": "repair|maintenance|progress|other"}"""


def load_dotenv(path: Path) -> None:
    """极简 .env 加载：KEY=VALUE 每行一条，不覆盖已有环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_cases() -> list[dict]:
    data = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    cases = data["cases"]
    bad = [c["id"] for c in cases if c["expected"] not in VALID_INTENTS]
    if bad:
        raise SystemExit(f"评测集有非法 expected 标签：{bad}")
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise SystemExit("评测集 id 有重复")
    return cases


def parse_intent(text: str) -> str | None:
    """从回复里抠出 intent；模型偶尔多话，取第一个出现的合法标签。"""
    match = re.search(r'\{\s*"intent"\s*:\s*"(\w+)"', text)
    if match and match.group(1) in VALID_INTENTS:
        return match.group(1)
    for intent in VALID_INTENTS:
        if f'"{intent}"' in text:
            return intent
    return None


def call_model(client, base_url: str, api_key: str, model: str, text: str) -> tuple[str, dict]:
    """Anthropic messages 格式调用；返回 (原始文本, usage)。"""
    resp = client.post(
        f"{base_url}/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        json={
            "model": model,
            # deepseek-flash 默认带 thinking 块且计入输出预算：给足余量，
            # 否则长思考案例（如带情绪的投诉）会被截断到没有正文（2026-09-13 R09 教训）
            "max_tokens": 300,
            "temperature": 0,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text}],
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    text_out = "".join(
        block.get("text", "") for block in payload.get("content", [])
    )
    return text_out, payload.get("usage", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="意图分类能力测评")
    parser.add_argument("--dry-run", action="store_true", help="不出网，只校验评测集与提示词")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（试跑用）")
    parser.add_argument("--offset", type=int, default=0, help="从第 N 条开始（配合 --limit 抽样）")
    parser.add_argument("--threshold", type=float, default=0.9,
                        help="通过率门槛，低于则退出码 1（首跑后按实测校准）")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    cases = load_cases()
    if args.offset:
        cases = cases[args.offset:]
    if args.limit:
        cases = cases[: args.limit]

    if args.dry_run:
        print(f"dry-run OK：{len(cases)} 条用例，标签分布：",
              {tag: sum(1 for c in cases if c['expected'] == tag) for tag in VALID_INTENTS})
        print(f"提示词 {len(SYSTEM_PROMPT)} 字符；模型="
              f"{os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash')}；"
              f"key={'已配置' if os.environ.get('DEEPSEEK_API_KEY') else '未配置'}")
        return 0

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("缺 DEEPSEEK_API_KEY：请写入项目根 .env（该文件已 gitignore，勿提交）")
        return 2
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")

    import httpx

    client = httpx.Client(timeout=60)
    results = []
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    for case in cases:
        started = time.time()
        try:
            raw, usage = call_model(client, base_url, api_key, model, case["text"])
            predicted = parse_intent(raw)
            error = None if predicted else f"无法解析输出：{raw[:120]}"
        except Exception as exc:  # 网络/鉴权等，单条失败不中断整轮
            predicted, raw, usage = None, "", {}
            error = f"{type(exc).__name__}: {str(exc)[:150]}"
        for key in usage_total:
            usage_total[key] += int(usage.get(key) or 0)
        results.append({
            **case,
            "predicted": predicted,
            "correct": predicted == case["expected"],
            "latency_ms": int((time.time() - started) * 1000),
            "error": error,
        })
        mark = "✓" if predicted == case["expected"] else "✗"
        print(f"[{mark}] {case['id']} 期望={case['expected']} 实际={predicted}"
              + (f"  ({error})" if error else ""))

    passed = sum(1 for r in results if r["correct"])
    accuracy = passed / len(results) if results else 0.0
    confusion = {}
    for r in results:
        if not r["correct"] and r["predicted"]:
            key = f"{r['expected']}→{r['predicted']}"
            confusion[key] = confusion.get(key, 0) + 1

    report = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "base_url": base_url,
        "total": len(results),
        "passed": passed,
        "accuracy": round(accuracy, 4),
        "threshold": args.threshold,
        "gate_pass": accuracy >= args.threshold,
        "confusion": confusion,
        "usage_total": usage_total,
        "results": results,
    }
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n通过 {passed}/{len(results)} = {accuracy:.1%}（门槛 {args.threshold:.0%}）"
          f" | 混淆对 {confusion or '无'}"
          f" | tokens {usage_total['input_tokens']}入/{usage_total['output_tokens']}出")
    print(f"报告已写入 {report_path}")
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
