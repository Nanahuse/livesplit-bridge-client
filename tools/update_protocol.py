# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "grpcio-tools==1.75.1",
#   "protobuf>=6.31,<7",
# ]
# ///

"""Regenerate the checked-in protobuf Python code from a pinned LiveSplit.Bridge revision."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from grpc_tools import protoc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = PROJECT_ROOT / "protocol-source.json"
OUTPUT_ROOT = PROJECT_ROOT / "src"

PROTO_FILES = (
    "livesplit/bridge/v1/common.proto",
    "livesplit/bridge/v1/run.proto",
    "livesplit/bridge/v1/bridge.proto",
)

GENERATED_FILES = (
    "livesplit/bridge/v1/common_pb2.py",
    "livesplit/bridge/v1/common_pb2.pyi",
    "livesplit/bridge/v1/run_pb2.py",
    "livesplit/bridge/v1/run_pb2.pyi",
    "livesplit/bridge/v1/bridge_pb2.py",
    "livesplit/bridge/v1/bridge_pb2.pyi",
)


def run(command: list[str], *, cwd: Path, check: bool = True) -> str:
    result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        detail = f"\n{result.stdout}\n{result.stderr}"
        raise RuntimeError(f"command failed ({result.returncode}): {command}{detail}")
    return result.stdout


def fetch_proto(repository: str, revision: str, destination: Path) -> None:
    clone = ["git", "clone", "--filter=blob:none", "--no-checkout", repository, str(destination)]
    run(clone, cwd=PROJECT_ROOT)
    run(["git", "sparse-checkout", "set", "proto"], cwd=destination)
    run(["git", "checkout", revision], cwd=destination)


def generate(proto_root: Path, output_root: Path) -> None:
    proto_files = [(proto_root / proto_file).resolve() for proto_file in PROTO_FILES]
    output_root.mkdir(parents=True, exist_ok=True)
    result = protoc.main(
        [
            "grpc_tools.protoc",
            f"--proto_path={proto_root}",
            f"--python_out={output_root}",
            f"--pyi_out={output_root}",
            *(str(proto_file) for proto_file in proto_files),
        ]
    )
    if result != 0:
        raise RuntimeError(f"protoc exited with status {result}")


def main() -> int:
    source = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    repository = source["repository"]
    revision = source["revision"]

    temporary_directory = tempfile.TemporaryDirectory(prefix="livesplit-bridge-protocol-")
    try:
        checkout = Path(temporary_directory.name) / "LiveSplit.Bridge"
        fetch_proto(repository, revision, checkout)
        generate(checkout / "proto", OUTPUT_ROOT)
    finally:
        temporary_directory.cleanup()

    for generated_file in GENERATED_FILES:
        path = OUTPUT_ROOT / generated_file
        if not path.is_file():
            raise RuntimeError(f"generated file is missing: {path}")

    print(f"Successfully generated protobuf files from {repository}@{revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
