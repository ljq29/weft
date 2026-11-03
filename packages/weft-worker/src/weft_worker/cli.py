"""Worker command-line entry point."""

import argparse
from collections.abc import Sequence

from weft_worker import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weft-worker")
    parser.add_argument("command", nargs="?", choices=["serve"], help="run the stdio worker")
    parser.add_argument("--version", action="store_true", help="show the worker version")
    args = parser.parse_args(argv)
    if args.version:
        print(f"weft-worker {__version__}")
        return 0
    if args.command == "serve":
        from weft_worker.runtime import serve

        return serve()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
