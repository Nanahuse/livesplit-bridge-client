# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "protobuf>=6.31,<7",
#   "pytest>=8,<10",
#   "pyzmq>=26,<28",
#   "ty==0.0.74",
# ]
# ///

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        parser.error(f"wheel does not exist: {wheel}")

    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="livesplit-bridge-typecheck-") as directory:
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                if member.filename.startswith("livesplit/"):
                    archive.extract(member, directory)
        return subprocess.run(
            [
                "ty",
                "check",
                "--python",
                sys.executable,
                "--extra-search-path",
                directory,
                "--ignore",
                "unused-ignore-comment",
                "--error-on-warning",
            ],
            cwd=project_root,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
