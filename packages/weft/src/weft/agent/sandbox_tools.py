from __future__ import annotations

from pathlib import Path
from typing import Any

from weft.agent.settings import SettingsStore
from weft.agent.tools import ToolRejectedError
from weft.sandbox.base import create_sandbox
from weft.sandbox.review import ChangeReviewStore


class SandboxedTool:
    def __init__(
        self,
        name: str,
        sandbox: Any,
        cwd: Path,
        timeout: float = 60,
        max_output_chars: int = 20000,
        requires_confirmation: bool = False,
        confirm: Any = None,
        run_id: str = "",
        agent_node: str = "",
    ) -> None:
        self.name = name
        self.sandbox = sandbox
        self.cwd = cwd
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.requires_confirmation = requires_confirmation
        self.confirm = confirm
        self.run_id = run_id
        self.agent_node = agent_node
        self.lane = "sandboxed"
        self.description = f"Sandboxed {name} tool"
        self.parameters = self._parameters(name)

    @staticmethod
    def _parameters(name: str) -> dict[str, Any]:
        properties: dict[str, Any] = {"path": {"type": "string"}}
        if name == "read":
            properties.update(
                {
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1},
                }
            )
        elif name == "write":
            properties["content"] = {"type": "string"}
        elif name == "edit":
            properties.update({"old_string": {"type": "string"}, "new_string": {"type": "string"}})
        elif name == "list":
            properties["pattern"] = {"type": "string"}
        elif name == "bash":
            properties = {"command": {"type": "string"}, "timeout": {"type": "number"}}
        required = ["path"] if name != "bash" else ["command"]
        if name in {"write", "edit"}:
            required.append("content" if name == "write" else "old_string")
        if name == "edit":
            required.append("new_string")
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def _confirm(self, args: dict[str, Any]) -> dict[str, Any]:
        import asyncio

        if self.confirm is None:
            raise ToolRejectedError("Tool call requires confirmation")
        decision = asyncio.run(
            self.confirm(
                {
                    "run_id": self.run_id,
                    "node_id": self.agent_node,
                    "tool": self.name,
                    "args": args,
                }
            )
        )
        if not isinstance(decision, dict) or decision.get("approved") is not True:
            raise ToolRejectedError("Tool call was rejected")
        updated = decision.get("args", args)
        if not isinstance(updated, dict):
            raise ToolRejectedError("Modified tool args must be an object")
        return updated

    def invoke(self, args: dict[str, Any]) -> str:
        if self.requires_confirmation:
            args = self._confirm(args)
        if self.name == "read":
            content = self.sandbox.read_file(self.cwd / args["path"]).decode("utf-8")
            offset = args.get("offset", 0)
            limit = args.get("limit", 200)
            return "".join(content.splitlines(keepends=True)[offset : offset + limit])
        if self.name == "write":
            self.sandbox.write_file(self.cwd / args["path"], args["content"].encode("utf-8"))
            return f"Wrote {args['path']}"
        if self.name == "edit":
            self.sandbox.edit_file(self.cwd / args["path"], args["old_string"], args["new_string"])
            return f"Edited {args['path']}"
        if self.name == "list":
            entries = self.sandbox.list_dir(self.cwd / args["path"], args.get("pattern"))
            return "\n".join(entry.path for entry in entries)
        if self.name == "bash":
            process = self.sandbox.spawn(
                ["cmd.exe", "/d", "/s", "/c", args["command"]],
                self.cwd,
                {},
                args.get("timeout", self.timeout),
            )
            code = process.wait(timeout=args.get("timeout", self.timeout))
            stdout, stderr = process.output()
            text: str = (stdout + stderr).decode("utf-8", errors="replace")
            if len(text) > self.max_output_chars:
                text = text[: self.max_output_chars] + "\n...[truncated]"
            return text + f"\nExit code: {code}"
        raise ValueError(f"Unknown sandbox tool: {self.name}")


class SandboxManager:
    def __init__(self, settings: SettingsStore | None = None) -> None:
        self.settings = settings or SettingsStore()
        self.confirmation_handler: Any = None
        self.sandboxes: dict[str, Any] = {}

    def validate(self, mode: str) -> None:
        if mode == "none" and not self.settings.read().get("sandbox", {}).get(
            "allow_none_sandbox", False
        ):
            raise PermissionError("NoneSandbox is disabled in settings")

    def get(self, prepared: Any, mode: str) -> Any:
        self.validate(mode)
        run_id = prepared.record.run_id
        if run_id not in self.sandboxes:
            self.sandboxes[run_id] = create_sandbox(prepared.root, run_id, mode, self.settings)
        return self.sandboxes[run_id]

    def create(
        self, prepared: Any, descriptor: dict[str, Any], agent_node: str = ""
    ) -> SandboxedTool:
        mode = descriptor["binding"].get("sandbox", "inherit")
        run_id = prepared.record.run_id
        self.get(prepared, mode)
        name = descriptor["name"]
        confirmation = descriptor.get("require_confirmation", name in {"write", "edit", "bash"})
        return SandboxedTool(
            name,
            self.sandboxes[run_id],
            Path(descriptor["binding"].get("cwd", prepared.root)),
            descriptor.get("bash_timeout", 60),
            descriptor.get("max_output_chars", 20000),
            confirmation,
            self.confirmation_handler,
            run_id,
            agent_node,
        )

    def finish(self, prepared: Any) -> None:
        sandbox = self.sandboxes.pop(prepared.record.run_id, None)
        if sandbox is None:
            return
        terminate = getattr(sandbox, "terminate_owned", None)
        if terminate is not None:
            terminate()
        changeset = sandbox.collect_changes()
        if prepared.workflow.settings.sandbox.auto_apply_in_root:
            ChangeReviewStore(prepared.root, prepared.record.run_id).auto_apply()
        prepared.engine._event(
            prepared,
            "changes.ready",
            "",
            {"count": len(changeset.changes), "audit_complete": changeset.audit_complete},
        )

    def close(self) -> None:
        for sandbox in self.sandboxes.values():
            terminate = getattr(sandbox, "terminate_owned", None)
            if terminate is not None:
                terminate()
        self.sandboxes.clear()
