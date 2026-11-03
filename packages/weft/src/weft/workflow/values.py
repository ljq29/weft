from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from weft.workflow.models import WorkflowModel

JSON_INLINE_LIMIT = 256 * 1024


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class ValueRef(WorkflowModel):
    kind: Literal["table", "json", "none"]
    path: Path | None = None
    inline: Any = None
    hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    rows: int | None = Field(default=None, ge=0)
    cols: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_storage(self) -> ValueRef:
        if self.kind == "table":
            if self.path is None or self.hash is None or self.rows is None or self.cols is None:
                raise ValueError("Table ValueRef requires path, hash, rows and cols")
        elif self.kind == "json":
            if self.hash is None or (self.path is None) == (self.inline is None):
                raise ValueError("JSON ValueRef requires exactly one of inline or path and a hash")
        elif self.path is not None or self.inline is not None or self.hash is not None:
            raise ValueError("None ValueRef cannot contain a value")
        return self

    @classmethod
    def from_json(cls, value: Any, directory: Path | None = None) -> ValueRef:
        data = canonical_json_bytes(value)
        digest = content_hash(data)
        if len(data) <= JSON_INLINE_LIMIT:
            return cls(kind="json", inline=value, hash=digest)
        if directory is None:
            raise ValueError("A directory is required for JSON values larger than 256 KB")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "value.json"
        path.write_bytes(data)
        return cls(kind="json", path=path, hash=digest)
