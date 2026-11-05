"""Export node specifications from registered declarations."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from weft.nodes.registry import NodeRegistry, builtin_registry


def build_node_index(registry: NodeRegistry | None = None) -> dict[str, object]:
    nodes = (registry or builtin_registry()).all()
    return {"schema_version": 1, "nodes": [node.manifest({}) for node in nodes]}


def render_node_index(registry: NodeRegistry | None = None) -> str:
    return json.dumps(build_node_index(registry), ensure_ascii=False, indent=2) + "\n"


def render_markdown(registry: NodeRegistry | None = None) -> str:
    nodes = (registry or builtin_registry()).all()
    lines = [
        "# Weft v1 节点规格",
        "",
        "<!-- 由代码节点声明自动生成，请勿手工编辑。 -->",
        "",
        "|类型|名称|中文补充|分类|执行 lane|缓存策略|说明|",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for node in nodes:
        lines.append(
            f"|`{node.type}`|{node.name}|{node.display_name}|{node.category}|{node.lane}|"
            f"{node.cache_policy}|{node.description}|"
        )
    for node in nodes:
        lines.extend(
            [
                "",
                f"## {node.name} (`{node.type}`)",
                "",
                node.description,
                "",
                "```json",
                json.dumps(node.params_schema, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the Weft node registry")
    parser.add_argument("--output", type=Path, help="write the JSON or Markdown index")
    parser.add_argument("--check", action="store_true", help="fail when output differs")
    args = parser.parse_args(argv)
    content = (
        render_markdown() if args.output and args.output.suffix == ".md" else render_node_index()
    )
    if args.check:
        if (
            not args.output
            or not args.output.exists()
            or args.output.read_text(encoding="utf-8") != content
        ):
            print("Node specifications differ from generated output")
            return 1
        return 0
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
