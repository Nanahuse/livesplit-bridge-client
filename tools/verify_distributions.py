# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

REQUIRED_SUFFIXES = (
    "livesplit_bridge/__init__.py",
    "livesplit_bridge/models.py",
    "livesplit_bridge/_generated/__init__.py",
    "livesplit_bridge/_generated/protocol.py",
    "livesplit_bridge/_api.py",
    "livesplit_bridge/_json.py",
    "livesplit_bridge/rpc.py",
    "livesplit_bridge/events.py",
    "livesplit_bridge/client.py",
    "livesplit_bridge/py.typed",
)


def verify(entries: list[str], archive: Path) -> None:
    for suffix in REQUIRED_SUFFIXES:
        if not any(entry.endswith(suffix) for entry in entries):
            raise RuntimeError(f"{suffix} is missing from {archive.name}")
    forbidden = ("_pb2.py", "_pb2.pyi", ".proto", "uv.lock", "livesplit_bridge/protocol.py")
    if any(entry.endswith(forbidden) or "livesplit/bridge/" in entry for entry in entries):
        raise RuntimeError(f"obsolete protocol code or lockfile was included in {archive.name}")
    if any("schemas/" in entry or entry.endswith(".schema.json") for entry in entries):
        raise RuntimeError(f"A JSON schema was included in {archive.name}")
    if not archive.name.endswith(".whl"):
        required = (
            "protocol-source.json",
            "tests/fixtures/csharp-serialized-cases.json",
            "tests/fixtures/validation-cases.json",
            "tools/update_protocol.py",
            "tools/protocol_names.json",
            "tools/run_integration.py",
            "tools/verify_distributions.py",
        )
        for suffix in required:
            if not any(entry.endswith(suffix) for entry in entries):
                raise RuntimeError(f"{suffix} is missing from {archive.name}")


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
        metadata_path = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_path).decode("utf-8")
        requirements = Parser().parsestr(metadata).get_all("Requires-Dist", [])
        if not any(requirement.startswith("pydantic") for requirement in requirements):
            raise RuntimeError("The wheel is missing the Pydantic runtime dependency")
        development = ("protobuf", "grpcio", "datamodel-code-generator", "jsonschema")
        if any(name in item.lower() for item in requirements for name in development):
            raise RuntimeError(
                "A development or obsolete protocol dependency is present at runtime"
            )
    with tarfile.open(sdists[0], "r:gz") as archive:
        verify(archive.getnames(), sdists[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
