# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "grpcio-tools==1.75.1",
#   "protobuf>=6.31,<7",
# ]
# ///

from __future__ import annotations

import argparse
from pathlib import Path

from grpc_tools import protoc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[1]
    proto_root = project_root / "external" / "LiveSplit.Bridge" / "proto"
    proto_files = [
        proto_root / "livesplit" / "bridge" / "v1" / "common.proto",
        proto_root / "livesplit" / "bridge" / "v1" / "bridge.proto",
    ]
    return protoc.main(
        [
            "grpc_tools.protoc",
            f"--proto_path={proto_root}",
            f"--pyi_out={output}",
            *(str(proto_file) for proto_file in proto_files),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
