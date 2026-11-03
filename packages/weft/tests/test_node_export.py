import json
from pathlib import Path

from weft.nodes.export import main, render_node_index


def test_node_registry_exports_a_stable_index(tmp_path: Path) -> None:
    """T0.1: the exporter creates parent directories and emits a stable JSON index."""
    output = tmp_path / "nested" / "nodes.json"
    assert main(["--output", str(output)]) == 0
    exported = json.loads(output.read_text(encoding="utf-8"))
    assert exported["schema_version"] == 1
    assert "flow.trigger" in {node["type"] for node in exported["nodes"]}
    assert render_node_index().endswith("\n")
