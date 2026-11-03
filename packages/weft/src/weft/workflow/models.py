from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CURRENT_SCHEMA_VERSION = 1


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(WorkflowModel):
    x: float
    y: float


class Size(WorkflowModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class SandboxSettings(WorkflowModel):
    mode: Literal["inherit", "sandboxie", "none"] = "inherit"
    auto_apply_in_root: bool = False


class WorkflowSettings(WorkflowModel):
    concurrency_policy: Literal["queue", "drop", "cancel_previous"] = "queue"
    sandbox: SandboxSettings = SandboxSettings()


class VariableDefinition(WorkflowModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["str", "int", "float", "bool", "path", "list"]
    value: Any


class Node(WorkflowModel):
    id: str = Field(pattern=r"^n_[0-9a-f]{8}$")
    type: str
    node_version: int = Field(ge=1)
    name: str = Field(min_length=1)
    position: Position
    comment: str = ""
    params: dict[str, Any] = {}


class PortManifest(WorkflowModel):
    name: str = Field(min_length=1)
    kind: Literal["table", "excel", "variable", "message", "tool", "flow"]
    direction: Literal["input", "output"]


class NodeManifest(WorkflowModel):
    node_id: str = Field(pattern=r"^n_[0-9a-f]{8}$")
    node_type: str
    node_version: int = Field(ge=1)
    ports: list[PortManifest]
    user_code_hash: str | None = None


class Edge(WorkflowModel):
    id: str = Field(pattern=r"^e_[0-9a-f]{8}$")
    source: str = Field(pattern=r"^n_[0-9a-f]{8}$")
    sourcePort: str = Field(min_length=1)
    target: str = Field(pattern=r"^n_[0-9a-f]{8}$")
    targetPort: str = Field(min_length=1)
    order: int = Field(ge=0)


class Note(WorkflowModel):
    id: str = Field(min_length=1)
    position: Position
    size: Size
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    markdown: str


class Viewport(WorkflowModel):
    x: float
    y: float
    zoom: float = Field(ge=0.25, le=2)


class WorkflowDocument(WorkflowModel):
    schema_version: int = CURRENT_SCHEMA_VERSION
    revision: int = Field(ge=1)
    id: str = Field(pattern=r"^wf_[0-9a-f]+$")
    name: str = Field(min_length=1)
    description: str = ""
    created_at: datetime
    modified_at: datetime
    settings: WorkflowSettings = WorkflowSettings()
    variables: list[VariableDefinition] = []
    nodes: list[Node]
    edges: list[Edge] = []
    notes: list[Note] = []
    viewport: Viewport = Viewport(x=0, y=0, zoom=1)

    @model_validator(mode="after")
    def validate_unique_identity(self) -> WorkflowDocument:
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]
        variable_names = [variable.name for variable in self.variables]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Node ids must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("Edge ids must be unique")
        if len(variable_names) != len(set(variable_names)):
            raise ValueError("Variable names must be unique")
        if sum(node.type == "flow.trigger" for node in self.nodes) != 1:
            raise ValueError("Workflow must contain exactly one Trigger")
        return self

    def structural_fingerprint(self) -> dict[str, Any]:
        return {
            "nodes": [node.model_dump(exclude={"position", "comment"}) for node in self.nodes],
            "edges": [edge.model_dump() for edge in self.edges],
        }
