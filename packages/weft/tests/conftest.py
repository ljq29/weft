from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def mock_llm() -> Iterator[Any]:
    path = Path(__file__).parent / "fixtures" / "mock_llm.py"
    spec = importlib.util.spec_from_file_location("weft_mock_llm", path)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load mock LLM")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with module.MockLLM() as server:
        yield server
