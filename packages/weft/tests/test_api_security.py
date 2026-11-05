from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from weft.api.app import create_app

TOKEN = "test-session-token"
HOST = "127.0.0.1:7788"


def client() -> TestClient:
    return TestClient(create_app(token=TOKEN), base_url=f"http://{HOST}")


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_api_requires_session_token_and_valid_host_origin() -> None:
    """US-SBX-09/AC-4,5: local APIs enforce token, Host and Origin boundaries."""
    with client() as api:
        assert api.get("/api/system/version").status_code == 401
        assert api.get("/api/system/version", headers=auth()).status_code == 200
        bad_host = api.get("/api/system/version", headers={**auth(), "Host": "evil.example"})
        assert bad_host.status_code == 403
        bad_origin = api.get(
            "/api/system/version",
            headers={**auth(), "Origin": "http://evil.example"},
        )
        assert bad_origin.status_code == 403
        assert bad_origin.json()["error"]["code"] == "FORBIDDEN"


def test_websocket_requires_authentication_before_subscribe() -> None:
    """US-EXE-05/AC-5: unauthenticated WS subscriptions are closed without events."""
    with client() as api:
        with api.websocket_connect("/api/ws") as socket:
            socket.send_json({"op": "subscribe", "topics": ["run:r_1"]})
            response = socket.receive_json()
            assert response["error"]["code"] == "UNAUTHORIZED"


def test_websocket_disconnect_before_authentication_is_clean() -> None:
    """US-EXE-05/AC-5: a client may disconnect before authentication without a server error."""
    with client() as api:
        with api.websocket_connect("/api/ws") as socket:
            assert socket.accepted_subprotocol is None


def test_websocket_authenticate_subscribe_and_receive() -> None:
    """US-EXE-05/AC-1,5: authenticated subscribers receive matching run events."""
    app = create_app(token=TOKEN)
    with TestClient(app, base_url=f"http://{HOST}") as api:
        with api.websocket_connect("/api/ws") as socket:
            socket.send_json({"op": "authenticate", "token": TOKEN})
            socket.send_json({"op": "subscribe", "topics": ["run:r_1"]})
            acknowledgement = socket.receive_json()
            assert acknowledgement["event"] == "subscribed"
            app.state.bus.publish(
                {
                    "event": "node.status",
                    "run_id": "r_1",
                    "node_id": "n_1",
                    "ts": "now",
                    "data": {"status": "executed"},
                }
            )
            event = socket.receive_json()
            assert event["event"] == "node.status"
            assert event["data"]["run_id"] == "r_1"


def test_workflow_crud_run_and_error_contract(tmp_path: Path) -> None:
    """US-DES-01/AC-1,2, US-DES-07/AC-4, US-EXE-06/AC-3: CRUD, runs and JSON ports."""
    with client() as api:
        created = api.post(
            "/api/workflows",
            json={"name": "demo", "parent_dir": str(tmp_path)},
            headers=auth(),
        )
        assert created.status_code == 201
        workflow_id = created.json()["id"]
        duplicate = api.post(
            "/api/workflows",
            json={"name": "demo", "parent_dir": str(tmp_path)},
            headers=auth(),
        )
        assert duplicate.status_code == 409
        document = api.get(f"/api/workflows/{workflow_id}", headers=auth()).json()
        assert document["nodes"][0]["type"] == "flow.trigger"
        for asset in ("weft-mark.svg", "weft-logo.svg"):
            branded = api.get(f"/{asset}")
            assert branded.status_code == 200
            assert branded.headers["content-type"].startswith("image/svg+xml")
            assert b"<svg" in branded.content
        document["description"] = "changed"
        saved = api.put(
            f"/api/workflows/{workflow_id}",
            json=document,
            headers={**auth(), "X-Weft-Client": "ui"},
        )
        assert saved.status_code == 200
        assert saved.json()["revision"] == 2
        stale = api.put(
            f"/api/workflows/{workflow_id}",
            json=document,
            headers={**auth(), "X-Weft-Client": "ui"},
        )
        assert stale.status_code == 409
        patched = api.patch(
            f"/api/workflows/{workflow_id}",
            json={"revision": 2, "description": "patched"},
            headers={**auth(), "X-Weft-Client": "ui"},
        )
        assert patched.status_code == 200
        assert patched.json()["revision"] == 3
        duplicated = api.post(
            f"/api/workflows/{workflow_id}/duplicate",
            json={"name": "copy", "parent_dir": str(tmp_path)},
            headers=auth(),
        )
        assert duplicated.status_code == 201
        assert duplicated.json()["id"] != workflow_id
        env = api.get(f"/api/workflows/{workflow_id}/env", headers=auth())
        assert env.status_code == 200
        assert env.json()["status"] == "missing"
        nodes = api.get("/api/nodes/types", headers=auth())
        assert nodes.status_code == 200
        assert any(item["type"] == "flow.trigger" for item in nodes.json())
        running = api.post(f"/api/workflows/{workflow_id}/runs", json={}, headers=auth())
        assert running.status_code == 202
        run_id = running.json()["run_id"]
        for _ in range(100):
            record = api.get(f"/api/runs/{run_id}", headers=auth()).json()
            if record["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert record["status"] == "succeeded"
        variable = api.get(f"/api/runs/{run_id}/nodes/n_00000001/ports/variable", headers=auth())
        message = api.get(f"/api/runs/{run_id}/nodes/n_00000001/ports/message", headers=auth())
        assert variable.json()["source"] == "manual"
        assert message.json() == []
        missing_port = api.get(
            f"/api/runs/{run_id}/nodes/n_00000001/ports/missing",
            headers=auth(),
        )
        assert missing_port.status_code == 404
        assert missing_port.json()["error"]["code"] == "PORT_NOT_EXECUTED"


def test_workflow_update_requires_ui_auth_and_rejects_active_run(tmp_path: Path) -> None:
    """US-AGT-11/AC-2: graph updates enforce UI auth and reject active Runs."""
    from types import SimpleNamespace

    with client() as api:
        created = api.post(
            "/api/workflows",
            json={"name": "graph-security", "parent_dir": str(tmp_path)},
            headers=auth(),
        )
        workflow_id = created.json()["id"]
        document = api.get(f"/api/workflows/{workflow_id}", headers=auth()).json()
        assert api.put(f"/api/workflows/{workflow_id}", json=document).status_code == 401
        assert (
            api.put(f"/api/workflows/{workflow_id}", json=document, headers=auth()).status_code
            == 403
        )
        api.app.state.coordinator.active[workflow_id] = "r_active"
        api.app.state.engine.runs["r_active"] = SimpleNamespace(
            record=SimpleNamespace(status="running")
        )
        document["nodes"].append(
            {
                "id": "n_00000002",
                "type": "flow.wait",
                "node_version": 1,
                "name": "Wait",
                "position": {"x": 200, "y": 0},
                "params": {"duration_seconds": 0},
            }
        )
        active = api.put(
            f"/api/workflows/{workflow_id}",
            json=document,
            headers={**auth(), "X-Weft-Client": "ui"},
        )
        assert active.status_code == 409
