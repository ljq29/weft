from __future__ import annotations

import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from weft.workflow.store import WorkflowStore


@dataclass(frozen=True)
class DemoInfo:
    id: str
    title: str
    description: str
    requirements: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "requirements": self.requirements,
        }


DEMOS = (
    DemoInfo(
        "csv-sales",
        "CSV 销售汇总",
        "读取内置销售数据，筛选高金额订单，按地区汇总并写出 CSV。",
        "无需外部服务",
    ),
    DemoInfo(
        "table-transform",
        "表格计算与预览",
        "从内嵌表格计算销售额，按类别聚合并预览结果。",
        "无需外部服务",
    ),
    DemoInfo(
        "llm-text",
        "LLM 文本处理",
        "通过一次 LLM Call 提取文本要点，演示命名模型配置的使用。",
        "需配置名为 demo 的 OpenAI 兼容端点",
    ),
)


def list_demos() -> list[DemoInfo]:
    return list(DEMOS)


def create_demo(demo_id: str, name: str, parent_dir: Path) -> Path:
    demo = next((item for item in DEMOS if item.id == demo_id), None)
    if demo is None:
        raise KeyError(demo_id)
    target = parent_dir / f"{name}.weft"
    if target.exists():
        raise FileExistsError(f"目标目录已存在：{target}")
    source = resources.files("weft.demos").joinpath(f"{demo.id}.weft")
    with resources.as_file(source) as source_path:
        shutil.copytree(source_path, target)
    try:
        document = WorkflowStore(target).load()
        now = datetime.now(UTC)
        document.id = f"wf_{secrets.token_hex(6)}"
        document.name = name
        document.revision = 1
        document.created_at = now
        document.modified_at = now
        (target / "workflow.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")
        return target
    except Exception:
        shutil.rmtree(target)
        raise
