from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    spec_path, stdout_path, stderr_path = map(Path, args[:3])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            result = subprocess.run(
                spec["cmd"],
                cwd=spec["cwd"],
                env=spec["env"],
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
            return result.returncode
        except Exception as exception:
            stderr.write(f"{type(exception).__name__}: {exception}".encode())
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
