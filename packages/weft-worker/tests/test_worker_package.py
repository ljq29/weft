from weft_sdk import __version__ as sdk_version
from weft_worker import __version__


def test_worker_and_sdk_versions_are_aligned() -> None:
    """T0.1: workspace packages start from one aligned version."""
    assert __version__ == sdk_version == "0.2.0"
