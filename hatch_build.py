from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Generate protobuf runtime modules and stubs for distributions only."""

    PLUGIN_NAME = "custom"

    def dependencies(self) -> list[str]:
        if self._is_complete(Path(self.root, "generated")):
            return []
        return ["grpcio-tools==1.75.1"]

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        del version
        generated_root = Path(self.root, "generated")
        if not self._is_complete(generated_root):
            self._temporary_directory = TemporaryDirectory(prefix="livesplit-bridge-protobuf-")
            generated_root = Path(self._temporary_directory.name)
            self._generate(generated_root)

        marker = generated_root / "livesplit" / "bridge" / "v1" / "py.typed"
        marker.touch(exist_ok=True)

        force_include = build_data.setdefault("force_include", {})
        destination_root = "livesplit" if self.target_name == "wheel" else "generated/livesplit"
        for generated_file in Path(generated_root, "livesplit").rglob("*"):
            if generated_file.is_file():
                relative_path = generated_file.relative_to(Path(generated_root, "livesplit"))
                force_include[str(generated_file)] = str(Path(destination_root, relative_path))

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        del version, build_data, artifact_path
        temporary_directory = getattr(self, "_temporary_directory", None)
        if temporary_directory is not None:
            temporary_directory.cleanup()

    @staticmethod
    def _is_complete(root: Path) -> bool:
        protocol_root = root / "livesplit" / "bridge" / "v1"
        return all(
            (protocol_root / filename).is_file()
            for filename in (
                "bridge_pb2.py",
                "bridge_pb2.pyi",
                "common_pb2.py",
                "common_pb2.pyi",
            )
        )

    def _generate(self, output_root: Path) -> None:
        from grpc_tools import protoc

        proto_root = Path(self.root, "external", "LiveSplit.Bridge", "proto")
        proto_files = [
            proto_root / "livesplit" / "bridge" / "v1" / "common.proto",
            proto_root / "livesplit" / "bridge" / "v1" / "bridge.proto",
        ]
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
