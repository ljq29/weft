import subprocess
import sys

import pytest
import weft
import weft_sdk
import weft_worker


@pytest.mark.integration
def test_workspace_entry_points_run_as_installed_packages() -> None:
    """T0.1: all three distributions are importable and their CLIs execute."""
    assert weft.__version__ == weft_worker.__version__ == weft_sdk.__version__
    for module, expected in (("weft", "weft 0.1.0"), ("weft_worker.cli", "weft-worker 0.1.0")):
        result = subprocess.run(
            [sys.executable, "-m", module, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == expected
        assert result.stderr == ""
