# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "grpcio-tools==1.75.1",
#   "protobuf>=6.31,<7",
#   "pytest>=8,<10",
#   "pyzmq>=26,<28",
#   "ty==0.0.74",
# ]
# ///

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from grpc_tools import protoc


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    proto_root = project_root / "external" / "LiveSplit.Bridge" / "proto"
    proto_files = [
        proto_root / "livesplit" / "bridge" / "v1" / "common.proto",
        proto_root / "livesplit" / "bridge" / "v1" / "bridge.proto",
    ]
    with tempfile.TemporaryDirectory(prefix="livesplit-bridge-typecheck-") as directory:
        result = protoc.main(
            [
                "grpc_tools.protoc",
                f"--proto_path={proto_root}",
                f"--pyi_out={directory}",
                *(str(proto_file) for proto_file in proto_files),
            ]
        )
        if result != 0:
            return result
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
