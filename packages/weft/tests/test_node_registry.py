from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from weft import __version__
from weft.nodes.export import main, render_markdown, render_node_index
from weft.nodes.registry import NodeRegistry, builtin_registry, implementation_hash


def test_builtin_schemas_are_draft_2020_12() -> None:
    """US-DES-04/AC-4: every registered node schema is valid JSON Schema 2020-12."""
    registry = builtin_registry()
    assert registry.get("flow.trigger").type == "flow.trigger"
    for node in registry.all():
        assert node.params_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        jsonschema.Draft202012Validator.check_schema(node.params_schema)
        assert node.description
        for prop in node.params_schema.get("properties", {}).values():
            assert prop.get("description")


def test_custom_nodes_can_be_registered_and_exported() -> None:
    """T1.3: registry declarations flow into the generated node index."""
    registry = NodeRegistry()
    registry.register(builtin_registry().get("flow.trigger").__class__)
    exported = json.loads(render_node_index(registry))
    assert exported["nodes"][0]["type"] == "flow.trigger"
    assert exported["nodes"][0]["params_schema"]["type"] == "object"


def test_node_implementation_hash_has_versioned_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T7.10: nodes retain deterministic cache keys when Python source is unavailable."""
    monkeypatch.setattr(
        "weft.nodes.registry.inspect.getsource", lambda _: (_ for _ in ()).throw(OSError())
    )
    node_type = builtin_registry().get("flow.trigger").__class__
    expected = f"weft.nodes.flow.TriggerNode@{__version__}".encode()
    assert (
        implementation_hash(node_type)
        == f"sha256:{__import__('hashlib').sha256(expected).hexdigest()}"
    )


def test_duplicate_node_registration_is_rejected() -> None:
    """T1.3: a registry cannot silently replace an existing node declaration."""
    registry = builtin_registry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(registry.get("flow.trigger").__class__)


def test_generated_markdown_matches_repository(tmp_path: Path) -> None:
    """T1.3: generated node docs are stable and --check detects manual edits."""
    expected = render_markdown(builtin_registry())
    output = tmp_path / "09-nodes-v1.md"
    assert main(["--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == expected
    assert main(["--output", str(output), "--check"]) == 0
    output.write_text(expected + "manual edit\n", encoding="utf-8")
    assert main(["--output", str(output), "--check"]) == 1
