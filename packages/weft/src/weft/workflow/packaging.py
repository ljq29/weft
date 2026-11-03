from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import jsonschema
from pydantic import ValidationError

from weft.agent.settings import SettingsStore
from weft.engine.scheduler import schema_with_variables
from weft.nodes.registry import NodeRegistry
from weft.worker.environment import WorkflowEnvironment
from weft.workflow.store import WorkflowStore
from weft.workflow.validation import ValidationIssue, _walk_params, validate_workflow

EXCLUDED_DIRECTORIES = {".git", ".runs", ".venv", "__pycache__"}
HIGH_ENTROPY_KEY = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{20,}|(?:api[_-]?key|token|secret)\s*[=:]\s*['\"][A-Za-z0-9_./+\-]{20,})",
    re.IGNORECASE,
)


class PackError(ValueError):
    def __init__(self, report: PackPreflight) -> None:
        super().__init__("打包预检失败")
        self.report = report


class UnpackError(ValueError):
    pass


@dataclass(frozen=True)
class PackPreflight:
    errors: tuple[dict[str, Any], ...]
    warnings: tuple[dict[str, Any], ...]
    abs_paths: tuple[dict[str, str], ...]
    size_estimate: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "abs_paths": list(self.abs_paths),
            "size_estimate": self.size_estimate,
        }


def _issue(issue: ValidationIssue) -> dict[str, Any]:
    return {"code": issue.code, "message": issue.message, "node_id": issue.node_id}


def _included_files(root: Path, exclude_data: bool) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if exclude_data and relative.parts and relative.parts[0] == "data":
            continue
        if path.is_symlink() or not path.is_file() or path.suffix == ".pyc":
            continue
        files.append(path)
    return sorted(files)


def _secrets() -> list[bytes]:
    settings = SettingsStore().read()
    values = []
    for config in settings.get("llm", {}).values():
        value = config.get("api_key", "")
        if isinstance(value, str) and value and value != "***":
            values.append(value.encode("utf-8"))
    return values


def preflight(root: Path, registry: NodeRegistry, exclude_data: bool = False) -> PackPreflight:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    abs_paths: list[dict[str, str]] = []
    files = _included_files(root, exclude_data)
    try:
        document = WorkflowStore(root).load()
    except (OSError, ValueError, ValidationError) as exception:
        return PackPreflight(
            ({"code": "WORKFLOW_INVALID", "message": str(exception), "node_id": None},),
            (),
            (),
            sum(path.stat().st_size for path in files),
        )
    declarations = {}
    for node in document.nodes:
        try:
            declarations[node.type] = registry.declaration(node.type, node.params)
        except KeyError:
            pass
        except ValueError as exception:
            errors.append(
                {
                    "code": "NODE_UNCONFIGURED",
                    "message": f"节点 {node.name} 参数不完整：{exception}",
                    "node_id": node.id,
                }
            )
    report = validate_workflow(document, declarations)
    errors.extend(_issue(issue) for issue in report.errors)
    warnings.extend(_issue(issue) for issue in report.warnings)
    for node in document.nodes:
        try:
            declaration = registry.get(node.type)
        except KeyError:
            errors.append(
                {"code": "UNKNOWN_NODE", "message": f"未知节点类型 {node.type}", "node_id": node.id}
            )
            continue
        try:
            jsonschema.validate(node.params, schema_with_variables(declaration.params_schema))
        except jsonschema.ValidationError as exception:
            errors.append(
                {
                    "code": "NODE_UNCONFIGURED",
                    "message": f"节点 {node.name} 参数不完整：{exception.message}",
                    "node_id": node.id,
                }
            )
        for param_path, value, kind in _walk_params(node.params):
            if kind == "path":
                abs_paths.append({"node_id": node.id, "param": param_path, "value": value})
    for name in ("workflow.json", "pyproject.toml", "uv.lock"):
        if not (root / name).is_file():
            errors.append({"code": "REQUIRED_FILE_MISSING", "message": f"缺少 {name}"})
    secrets = _secrets()
    for path in files:
        content = path.read_bytes()
        if any(secret in content for secret in secrets):
            errors.append(
                {
                    "code": "SECRET_DETECTED",
                    "message": f"文件包含用户配置中的密钥：{path.relative_to(root)}",
                }
            )
        if path.suffix == ".py":
            text = content.decode("utf-8", errors="replace")
            if HIGH_ENTROPY_KEY.search(text):
                warnings.append(
                    {
                        "code": "POSSIBLE_HARDCODED_SECRET",
                        "message": f"文件可能包含硬编码密钥：{path.relative_to(root)}",
                    }
                )
    return PackPreflight(
        tuple(errors), tuple(warnings), tuple(abs_paths), sum(path.stat().st_size for path in files)
    )


def pack_workflow(
    root: Path,
    output: Path | None = None,
    exclude_data: bool = False,
    confirm_warnings: bool = False,
    registry: NodeRegistry | None = None,
) -> Path:
    root = root.resolve()
    if registry is None:
        from weft.nodes.registry import builtin_registry

        registry = builtin_registry()
        registry.load_directory(root / "nodes")
    report = preflight(root, registry, exclude_data)
    if report.errors or (report.warnings and not confirm_warnings):
        raise PackError(report)
    document = WorkflowStore(root).load()
    output = output or root.parent / f"{document.name}-{datetime.now():%Y%m%d}.weft.zip"
    output = output.resolve()
    files = _included_files(root, exclude_data)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in ("nodes", "prompts"):
            if (root / directory).is_dir():
                archive.writestr(f"{root.name}/{directory}/", b"")
        for path in files:
            archive.write(path, f"{root.name}/{path.relative_to(root).as_posix()}")
    return output


def _archive_root(archive: zipfile.ZipFile) -> str:
    roots = set()
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if path.is_absolute() or PureWindowsPath(name).drive or ".." in path.parts:
            raise UnpackError("压缩包包含 Root 外路径")
        if not path.parts or (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise UnpackError("压缩包包含无效路径或符号链接")
        roots.add(path.parts[0])
    if len(roots) != 1:
        raise UnpackError("压缩包根必须只有一个工作流目录")
    return next(iter(roots))


def unpack_workflow(zip_path: Path, dest_dir: Path, sync: bool = True) -> Path:
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        root_name = _archive_root(archive)
        root = dest_dir / root_name
        if root.exists():
            raise UnpackError(f"目标目录已存在：{root}")
        root.mkdir()
        try:
            for info in archive.infolist():
                relative = PurePosixPath(info.filename.replace("\\", "/"))
                target = root.joinpath(*relative.parts[1:])
                if not target.resolve().is_relative_to(root.resolve()):
                    raise UnpackError("压缩包包含 Root 外路径")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
            WorkflowStore(root).load()
            if sync:
                WorkflowEnvironment(root).sync()
            return root
        except Exception:
            shutil.rmtree(root)
            raise
