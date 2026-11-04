from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from weft import __version__

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUNDLE = DIST / "weft-windows-x64"


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def compile_nuitka() -> Path:
    output = ROOT / "build" / "nuitka"
    output.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-m",
            "nuitka",
            "--standalone",
            "--assume-yes-for-downloads",
            "--jobs=4",
            "--lto=no",
            f"--output-dir={output}",
            "--output-filename=weft.exe",
            "--company-name=Weft",
            "--product-name=Weft",
            f"--file-version={__version__}",
            f"--product-version={__version__}",
            "--file-description=Local-first visual workflow tool",
            "--include-package=weft",
            "--include-package=weft_worker",
            "--include-package=weft_sdk",
            "--nofollow-import-to=pytest",
            "--nofollow-import-to=mypy",
            "--include-package-data=weft",
            "--include-package-data=weft_worker",
            "--include-package-data=weft_sdk",
            "packages/weft/src/weft/__main__.py",
        ]
    )
    return output / "__main__.dist"


def copy_runtime(destination: Path) -> Path:
    runtime = destination / "runtime" / "python"
    shutil.copytree(
        Path(sys.base_prefix),
        runtime,
        ignore=shutil.ignore_patterns("site-packages", "__pycache__", "*.pyc"),
    )
    python = runtime / "python.exe"
    environment = os.environ.copy()
    environment.setdefault("UV_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")
    run(
        [
            shutil.which("uv") or "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--find-links",
            str(DIST),
            f"weft=={__version__}",
            f"weft-worker=={__version__}",
            f"weft-sdk=={__version__}",
        ],
        env=environment,
    )
    return python


def copy_distribution(compiled: Path) -> None:
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    shutil.copytree(compiled, BUNDLE)
    copy_runtime(BUNDLE)
    tools = BUNDLE / "tools"
    tools.mkdir()
    shutil.copy2(shutil.which("uv") or "uv", tools / "uv.exe")
    wheels = BUNDLE / "wheels"
    wheels.mkdir()
    for name in (
        f"weft-{__version__}-py3-none-any.whl",
        f"weft_worker-{__version__}-py3-none-any.whl",
        f"weft_sdk-{__version__}-py3-none-any.whl",
    ):
        shutil.copy2(DIST / name, wheels / name)
    shutil.copy2(ROOT / "LICENSE", BUNDLE / "LICENSE.txt")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, BUNDLE / "LICENSE-Python.txt")
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
    compiled = compile_nuitka()
    copy_distribution(compiled)
    archive = write_archive()
    print(f"Portable bundle: {BUNDLE}")
    print(f"Portable archive: {archive}")


if __name__ == "__main__":
    main()
