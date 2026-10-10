"""A disposable, model-credential-free demo using the real workflow and PostgreSQL."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from acs.seed import seed
from acs.testing import temporary_database
from acs.bind import bind
from acs.service import route_service_turn

with temporary_database() as db:
    seed(db)
    bind("web:demo-a", "示例企业甲", db_url=db)
    for event, text in enumerate(["报修 DEMO-GR75-0001 异响", "查工单进度", "确认报修"], 1):
        result = route_service_turn(text, "demo", str(event), scope_key="web:demo-a", db_url=db)
        print(json.dumps({"input": text, "result": result}, ensure_ascii=False, indent=2))
