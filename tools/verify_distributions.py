# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

REQUIRED_SUFFIXES = (
    "livesplit/bridge/v1/bridge.proto",
    "livesplit/bridge/v1/common.proto",
    "livesplit/bridge/v1/bridge_pb2.py",
    "livesplit/bridge/v1/bridge_pb2.pyi",
    "livesplit/bridge/v1/common_pb2.py",
    "livesplit/bridge/v1/common_pb2.pyi",
    "livesplit_bridge/py.typed",
    "livesplit/bridge/v1/py.typed",
)


def verify(entries: list[str], archive: Path) -> None:
    for suffix in REQUIRED_SUFFIXES:
        if not any(entry.endswith(suffix) for entry in entries):
            raise RuntimeError(f"{suffix} is missing from {archive.name}")
    if any(entry.endswith("uv.lock") for entry in entries):
        raise RuntimeError(f"uv.lock was included in {archive.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    wheels = list(directory.glob("*.whl"))
    sdists = list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        parser.error("expected exactly one wheel and one source distribution")

    with zipfile.ZipFile(wheels[0]) as archive:
        verify(archive.namelist(), wheels[0])
    with tarfile.open(sdists[0], "r:gz") as archive:
        verify(archive.getnames(), sdists[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
