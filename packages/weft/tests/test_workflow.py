from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from weft.workflow import (
    MigrationRegistry,
    NodeDeclaration,
    NodeManifest,
    PortDeclaration,
    WorkflowDocument,
    WorkflowStore,
    WorkflowValidationError,
    load_workflow,
    validate_workflow,
)


def document_dict() -> dict:
    return {
        "schema_version": 1,
        "revision": 1,
        "id": "wf_0123456789ab",
        "name": "demo",
        "description": "",
        "created_at": "2026-01-01T00:00:00+00:00",
        "modified_at": "2026-01-01T00:00:00+00:00",
        "settings": {
            "concurrency_policy": "queue",
            "sandbox": {"mode": "inherit", "auto_apply_in_root": False},
        },
        "variables": [{"name": "threshold", "type": "int", "value": 10}],
        "nodes": [
            {
                "id": "n_00000001",
                "type": "flow.trigger",
                "node_version": 1,
                "name": "Trigger",
                "position": {"x": 0, "y": 0},
                "params": {"manual": {"enabled": True}},
            },
            {
                "id": "n_00000002",
                "type": "table.row_filter",
                "node_version": 1,
                "name": "Filter",
                "position": {"x": 200, "y": 0},
                "params": {"column": "amount", "operator": ">", "value": {"$var": "threshold"}},
            },
        ],
        "edges": [],
        "notes": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def declarations() -> dict[str, NodeDeclaration]:
    return {
        "flow.trigger": NodeDeclaration(
            node_type="flow.trigger",
            outputs=[
                PortDeclaration("variable", "variable"),
                PortDeclaration("message", "message"),
                PortDeclaration("table", "table"),
            ],
        ),
        "table.row_filter": NodeDeclaration(
            node_type="table.row_filter",
            inputs=[PortDeclaration("in", "table"), PortDeclaration("variables", "variable")],
            outputs=[PortDeclaration("out", "table")],
        ),
        "flow.merge": NodeDeclaration(
            node_type="flow.merge",
            inputs=[PortDeclaration("left", "table"), PortDeclaration("right", "table")],
            outputs=[PortDeclaration("out", "table")],
            accepts_partial_inputs=True,
        ),
    }


def test_newer_schema_version_is_rejected(tmp_path: Path) -> None:
    """US-PKG-05/AC-1: a newer workflow requires a Weft upgrade."""
    path = tmp_path / "workflow.json"
    document = document_dict()
    document["schema_version"] = 2
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(WorkflowValidationError, match="请升级 Weft"):
        load_workflow(path)


def test_migrations_are_incremental_and_backed_up(tmp_path: Path) -> None:
    """US-PKG-05/AC-2: migration creates a backup and runs registered steps in order."""
    path = tmp_path / "workflow.json"
    document = document_dict()
    document["schema_version"] = 0
    path.write_text(json.dumps(document), encoding="utf-8")
    registry = MigrationRegistry()

    def migrate_zero(document: dict) -> dict:
        document["schema_version"] = 1
        document["description"] = "migrated"
        return document

    registry.register(0, migrate_zero)
    migrated = load_workflow(path, migrations=registry)
    assert migrated.schema_version == 1
    assert migrated.description == "migrated"
    assert (
        json.loads((tmp_path / "workflow.json.bak.v0").read_text(encoding="utf-8"))[
            "schema_version"
        ]
        == 0
    )


def test_atomic_save_and_revision_cas(tmp_path: Path) -> None:
    """US-DES-07/AC-4, US-EXE-04/AC-8: save is atomic and stale revisions cannot overwrite."""
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(document_dict()), encoding="utf-8")
    store = WorkflowStore(tmp_path)
    original = store.load()
    saved = store.save(original, expected_revision=1)
    assert saved.revision == 2
    assert not (tmp_path / "workflow.json.tmp").exists()
    stale = store.load()
    stale.description = "newer"
    store.save(stale, expected_revision=2)
    stale.description = "stale overwrite"
    with pytest.raises(WorkflowValidationError, match="revision"):
        store.save(stale, expected_revision=2)
    assert store.load().description == "newer"


def test_active_run_rejects_structural_changes_only(tmp_path: Path) -> None:
    """US-DES-07/AC-5: active runs reject graph edits but allow position and comments."""
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(document_dict()), encoding="utf-8")
    store = WorkflowStore(tmp_path)
    document = store.load()
    document.nodes[1].position.x = 300
    document.nodes[1].comment = "note"
    moved = store.save(document, expected_revision=1, run_active=True)
    assert moved.revision == 2
    moved.nodes.pop()
    with pytest.raises(WorkflowValidationError, match="active run"):
        store.save(moved, expected_revision=2, run_active=True)


@pytest.mark.parametrize(
    ("node_id", "edge_id"),
    [("bad", "e_00000001"), ("n_00000001", "bad")],
)
def test_node_and_edge_id_formats(node_id: str, edge_id: str) -> None:
    """T1.1: node and edge identifiers use their documented stable formats."""
    document = document_dict()
    document["nodes"][1]["id"] = node_id
    document["edges"] = [
        {
            "id": edge_id,
            "source": "n_00000001",
            "sourcePort": "table",
            "target": node_id,
            "targetPort": "in",
            "order": 0,
        }
    ]
    with pytest.raises(ValidationError):
        WorkflowDocument.model_validate(document)


def test_edges_must_reference_existing_nodes_and_ports() -> None:
    """T1.1: semantic validation rejects missing nodes and unknown ports."""
    document = WorkflowDocument.model_validate(document_dict())
    document.edges = [
        {
            "id": "e_00000001",
            "source": "n_00000001",
            "sourcePort": "missing",
            "target": "n_00000002",
            "targetPort": "in",
            "order": 0,
        }
    ]
    report = validate_workflow(document, declarations())
    assert any("missing" in issue.message for issue in report.errors)


def test_port_compatibility_and_single_input_cardinality() -> None:
    """T1.1: incompatible ports and multiple ordinary incoming edges are errors."""
    document = WorkflowDocument.model_validate(document_dict())
    document.edges = [
        {
            "id": "e_00000001",
            "source": "n_00000001",
            "sourcePort": "variable",
            "target": "n_00000002",
            "targetPort": "in",
            "order": 0,
        },
        {
            "id": "e_00000002",
            "source": "n_00000001",
            "sourcePort": "table",
            "target": "n_00000002",
            "targetPort": "in",
            "order": 1,
        },
    ]
    report = validate_workflow(document, declarations())
    codes = {issue.code for issue in report.errors}
    assert "PORT_INCOMPATIBLE" in codes
    assert "PORT_CARDINALITY" in codes


def test_variable_edges_merge_by_unique_order() -> None:
    """T1.1: Variable inputs accept multiple edges but require unique order values."""
    document = WorkflowDocument.model_validate(document_dict())
    edge = {
        "id": "e_00000001",
        "source": "n_00000001",
        "sourcePort": "variable",
        "target": "n_00000002",
        "targetPort": "variables",
        "order": 0,
    }
    document.edges = [edge, {**edge, "id": "e_00000002"}]
    report = validate_workflow(document, declarations())
    assert any("order" in issue.message for issue in report.errors)


def test_exactly_one_trigger_and_no_shadow_trigger() -> None:
    """T1.1: Trigger params are the only trigger configuration source."""
    document = document_dict()
    document["nodes"] = [document["nodes"][0], document["nodes"][0]]
    with pytest.raises(ValidationError):
        WorkflowDocument.model_validate(document)
    document = document_dict()
    document["trigger"] = {"manual": True}
    with pytest.raises(ValidationError):
        WorkflowDocument.model_validate(document)


def test_loop_pairing_and_cycle_validation() -> None:
    """T1.1: unmatched Loop nodes and residual cycles are validation errors."""
    document = WorkflowDocument.model_validate(document_dict())
    document.nodes[1].type = "flow.loop_start"
    report = validate_workflow(document, declarations())
    assert any("Loop Start" in issue.message for issue in report.errors)
    document.nodes[1].type = "table.row_filter"
    document.edges = [
        {
            "id": "e_00000001",
            "source": "n_00000002",
            "sourcePort": "out",
            "target": "n_00000002",
            "targetPort": "in",
            "order": 0,
        }
    ]
    report = validate_workflow(document, declarations())
    assert "GRAPH_CYCLE" in {issue.code for issue in report.errors}


def test_variable_reference_and_absolute_path_are_warnings() -> None:
    """T1.1: unresolved variable references and absolute paths do not block saving."""
    document = WorkflowDocument.model_validate(document_dict())
    document.nodes[1].params["value"] = {"$var": "missing"}
    document.nodes[1].params["path"] = "D:/external/data.csv"
    report = validate_workflow(document, declarations())
    assert not report.errors
    assert len(report.warnings) == 2


def test_metanode_interface_must_map_to_internal_ports() -> None:
    """T1.1: Metanode interface mappings are validated against their embedded graph."""
    document = WorkflowDocument.model_validate(document_dict())
    document.nodes[1].type = "flow.metanode"
    document.nodes[1].params = {
        "graph": {"nodes": [], "edges": []},
        "interface": {"inputs": {"in": {"node": "n_missing", "port": "in"}}, "outputs": {}},
    }
    report = validate_workflow(document, declarations())
    assert any("Metanode" in issue.message for issue in report.errors)


def test_dynamic_ports_have_an_execution_manifest() -> None:
    """T1.1: instantiated dynamic ports are recorded without changing workflow node ids."""
    manifest = NodeManifest.model_validate(
        {
            "node_id": "n_00000002",
            "node_type": "table.concatenate",
            "node_version": 1,
            "ports": [
                {"name": "in_1", "kind": "table", "direction": "input"},
                {"name": "in_2", "kind": "table", "direction": "input"},
                {"name": "out", "kind": "table", "direction": "output"},
            ],
        }
    )
    assert [port.name for port in manifest.ports] == ["in_1", "in_2", "out"]
    assert manifest.node_id == "n_00000002"
