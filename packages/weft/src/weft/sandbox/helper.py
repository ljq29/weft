from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["read", "write", "edit", "list", "delete"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--old")
    parser.add_argument("--new")
    parser.add_argument("--pattern")
    args = parser.parse_args(argv)
    path = args.path
    if args.operation == "read":
        sys.stdout.buffer.write(path.read_bytes())
    elif args.operation == "write":
        if args.input is None:
            raise ValueError("write requires --input")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".weft-tmp")
        temporary.write_bytes(args.input.read_bytes())
        os.replace(temporary, path)
    elif args.operation == "edit":
        text = path.read_text(encoding="utf-8")
        if text.count(args.old or "") != 1:
            raise ValueError("edit old_string must match exactly once")
        path.write_text(text.replace(args.old or "", args.new or "", 1), encoding="utf-8")
    elif args.operation == "delete":
        path.unlink()
    else:
        entries = [
            {
                "path": str(item),
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size,
            }
            for item in path.iterdir()
            if not args.pattern or fnmatch.fnmatch(item.name, args.pattern)
        ]
        sys.stdout.write(json.dumps(entries, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
