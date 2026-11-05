from weft_sdk import __version__


def test_sdk_exposes_a_semver_version() -> None:
    """T0.1: the installable SDK exposes its package version."""
    assert __version__ == "0.2.2"
