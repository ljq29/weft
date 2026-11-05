from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest
from fastapi.testclient import TestClient
from weft.api.app import create_app, error
from weft.nodes.registry import builtin_registry
from weft.workflow import WorkflowDocument

TOKEN = "contract-token"
HOST = "127.0.0.1:7788"

MINIMAL_WORKFLOW = {
    "schema_version": 1,
    "revision": 1,
    "id": "wf_0123456789ab",
    "name": "contract",
    "description": "",
    "created_at": "2026-01-01T00:00:00Z",
    "modified_at": "2026-01-01T00:00:00Z",
    "settings": {
        "concurrency_policy": "queue",
        "sandbox": {"mode": "inherit", "auto_apply_in_root": False},
    },
    "variables": [],
    "nodes": [
        {
            "id": "n_00000001",
            "type": "flow.trigger",
            "node_version": 1,
            "name": "Trigger",
            "position": {"x": 0, "y": 0},
            "comment": "",
            "params": {},
        }
    ],
    "edges": [],
    "notes": [],
    "viewport": {"x": 0, "y": 0, "zoom": 1},
}

ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["error"],
    "additionalProperties": False,
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "message", "detail"],
            "additionalProperties": False,
            "properties": {
                "code": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1},
                "detail": {},
            },
        }
    },
}


def test_workflow_document_json_schema_contract() -> None:
    """US-DES-07/AC-4: WorkflowDocument keeps a valid minimal JSON Schema contract."""
    schema = WorkflowDocument.model_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(MINIMAL_WORKFLOW, schema)

    assert set(schema["properties"]) == {
        "schema_version",
        "revision",
        "id",
        "name",
        "description",
        "created_at",
        "modified_at",
        "settings",
        "variables",
        "nodes",
        "edges",
        "notes",
        "viewport",
    }
    assert set(schema["required"]) == {
        "revision",
        "id",
        "name",
        "created_at",
        "modified_at",
        "nodes",
    }
    assert (
        WorkflowDocument.model_validate(MINIMAL_WORKFLOW).model_dump(mode="json")
        == MINIMAL_WORKFLOW
    )


def test_node_type_declaration_manifest_contract() -> None:
    """US-DES-04/AC-4: NodeTypeDecl manifests retain fields consumed by the frontend."""
    declaration = builtin_registry().get("flow.trigger").manifest({})

    assert set(declaration) == {
        "type",
        "node_version",
        "category",
        "name",
        "display_name",
        "description",
        "lane",
        "cache_policy",
        "tool_capability",
        "inputs",
        "outputs",
        "params_schema",
        "ui_hints",
        "tool_exposed_params",
        "portable_params",
        "external_resources",
        "cache_inputs",
    }
    assert {
        key: declaration[key]
        for key in (
            "type",
            "node_version",
            "category",
            "name",
            "display_name",
            "lane",
            "cache_policy",
            "tool_capability",
        )
    } == {
        "type": "flow.trigger",
        "node_version": 1,
        "category": "flow",
        "name": "Trigger",
        "display_name": "触发器",
        "lane": "trusted_service",
        "cache_policy": "side_effect",
        "tool_capability": "none",
    }
    jsonschema.Draft202012Validator.check_schema(declaration["params_schema"])
    for port in declaration["inputs"] + declaration["outputs"]:
        assert set(port) == {"name", "kind", "description"}


def test_run_event_websocket_envelope_contract() -> None:
    """US-EXE-05/AC-1: RunEvent keeps its topic, event, timestamp and data envelope."""
    app = create_app(token=TOKEN, enable_triggers=False)
    with TestClient(app, base_url=f"http://{HOST}") as client:
        with client.websocket_connect("/api/ws") as socket:
            socket.send_json({"op": "authenticate", "token": TOKEN})
            assert socket.receive_json()["event"] == "authenticated"
            socket.send_json({"op": "subscribe", "topics": ["run:r_contract"]})
            assert socket.receive_json()["event"] == "subscribed"
            app.state.bus.publish(
                {
                    "event": "node.status",
                    "run_id": "r_contract",
                    "node_id": "n_00000001",
                    "ts": "2026-01-01T00:00:00+00:00",
                    "data": {"status": "executed"},
                }
            )
            event = socket.receive_json()

    assert event == {
        "topic": "run:r_contract",
        "event": "node.status",
        "ts": "2026-01-01T00:00:00+00:00",
        "data": {
            "status": "executed",
            "run_id": "r_contract",
            "node_id": "n_00000001",
        },
    }


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("REVISION_CONFLICT", 409),
        ("RUN_QUEUE_FULL", 409),
        ("PORT_NOT_EXECUTED", 404),
        ("VALIDATION_ERROR", 400),
    ],
)
def test_error_response_json_schema_contract(code: str, status: int) -> None:
    """US-DES-07/AC-4, US-EXE-06/AC-5: non-2xx errors retain stable machine codes."""
    response = error(code, "可读错误", status)
    payload: Any = json.loads(response.body)

    jsonschema.validate(payload, ERROR_RESPONSE_SCHEMA)
    assert response.status_code == status
    assert payload == {"error": {"code": code, "message": "可读错误", "detail": {}}}
