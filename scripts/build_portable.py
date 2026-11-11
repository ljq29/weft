from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from weft import __version__

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUNDLE = DIST / "weft-windows-x64"
PYTHON_VERSION = "3.12"


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def wheel_name(distribution: str) -> str:
    return f"{distribution.replace('-', '_')}-{__version__}-py3-none-any.whl"


def write_application_project(app: Path) -> None:
    app.mkdir(parents=True)
    (app / "VERSION").write_text(f"{__version__}\n", encoding="utf-8")
    (app / "pyproject.toml").write_text(
        f"""[project]
name = "weft-application"
version = "{__version__}"
requires-python = ">=3.12,<3.13"
dependencies = [
    "weft=={__version__}",
    "weft-worker=={__version__}",
    "weft-sdk=={__version__}",
]

[tool.uv]
package = false

[tool.uv.sources]
weft = {{ path = "../wheels/{wheel_name("weft")}" }}
weft-worker = {{ path = "../wheels/{wheel_name("weft-worker")}" }}
weft-sdk = {{ path = "../wheels/{wheel_name("weft-sdk")}" }}

[tool.uv.workspace]
""",
        encoding="utf-8",
    )


def write_manifest() -> None:
    files = {
        str(path.relative_to(BUNDLE)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(BUNDLE.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    (BUNDLE / "app" / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": __version__,
                "python": PYTHON_VERSION,
                "entrypoint": "weft.cmd",
                "first_run_download": True,
                "files": files,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def copy_distribution() -> None:
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    (BUNDLE / "tools").mkdir(parents=True)
    (BUNDLE / "wheels").mkdir()
    shutil.copy2(ROOT / "packaging" / "weft.cmd", BUNDLE / "weft.cmd")
    shutil.copy2(ROOT / "packaging" / "bootstrap-index.ps1", BUNDLE / "bootstrap-index.ps1")
    shutil.copy2(shutil.which("uv") or "uv", BUNDLE / "tools" / "uv.exe")
    for distribution in ("weft", "weft-worker", "weft-sdk"):
        shutil.copy2(DIST / wheel_name(distribution), BUNDLE / "wheels" / wheel_name(distribution))
    app = BUNDLE / "app"
    write_application_project(app)
    environment = os.environ.copy()
    environment.setdefault("UV_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")
    run([shutil.which("uv") or "uv", "lock"], cwd=app, env=environment)
    shutil.copy2(ROOT / "LICENSE", BUNDLE / "LICENSE.txt")
    (BUNDLE / "LICENSE-uv.txt").write_text(
        "MIT License\n\nCopyright (c) uv developers\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
        'of this software and associated documentation files (the "Software"), to deal\n'
        "in the Software without restriction, including without limitation the rights\n"
        "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
        "copies of the Software, and to permit persons to whom the Software is\n"
        "furnished to do so, subject to the following conditions:\n\n"
        "The above copyright notice and this permission notice shall be included in all\n"
        "copies or substantial portions of the Software.\n\n"
        'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
        "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
        "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
        "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
        "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
        "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
        "SOFTWARE.\n",
        encoding="utf-8",
    )
    (BUNDLE / "README.txt").write_text(
        f"Weft {__version__} - Windows x64\n\n"
        "Run weft.cmd. The first application run downloads managed CPython and locked\n"
        "dependencies with the bundled uv; no host Python or uv is required.\n"
        "Before downloading, choose the official PyPI index, a configured pip index, or\n"
        "the Tsinghua index. Failed probes include details; choice 4 forces the configured\n"
        "index. Use --china, --index-url or --force-configured-index for unattended setup.\n\n"
        "Examples:\n"
        "  weft.cmd serve\n"
        "  weft.cmd --china serve\n"
        "  weft.cmd --bootstrap-help\n\n"
        "Excel, Sandboxie-Plus and optional Node.js/pi remain separate dependencies.\n",
        encoding="utf-8",
    )
    write_manifest()


def write_archive() -> Path:
    archive = DIST / "weft-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(DIST))
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-frontend-build", action="store_true")
    parser.add_argument("--skip-wheel-build", action="store_true")
    args = parser.parse_args()
    if not args.skip_frontend_build:
        run([shutil.which("pnpm") or "pnpm", "-C", "frontend", "build"])
    if not args.skip_wheel_build:
        for package in ("weft-sdk", "weft-worker", "weft"):
            run(
                [
                    shutil.which("uv") or "uv",
                    "build",
                    "--wheel",
                    "--out-dir",
                    "dist",
                    f"packages/{package}",
                ]
            )
    copy_distribution()
    archive = write_archive()
    print(f"Portable bundle: {BUNDLE}")
    print(f"Portable archive: {archive}")


if __name__ == "__main__":
    main()
