from weft.cli import main


def test_version_command(capsys) -> None:
    """T0.1: the installed CLI reports the service version."""
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "weft 0.0.0"
