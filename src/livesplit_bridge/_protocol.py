from __future__ import annotations

import atexit
import importlib
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from types import ModuleType

from grpc_tools import protoc

_lock = threading.Lock()
_modules: tuple[ModuleType, ModuleType] | None = None
_generated_directory: Path | None = None
_module_names = (
    "livesplit",
    "livesplit.bridge",
    "livesplit.bridge.v1",
    "livesplit.bridge.v1.common_pb2",
    "livesplit.bridge.v1.bridge_pb2",
)


class ProtocolGenerationError(RuntimeError):
    """Raised when Python bindings cannot be generated from the bundled proto files."""


def _source_proto_root() -> Path:
    packaged = Path(__file__).resolve().parent / "proto"
    if packaged.is_dir():
        return packaged

    checkout = Path(__file__).resolve().parents[2] / "external" / "LiveSplit.Bridge" / "proto"
    if checkout.is_dir():
        return checkout

    raise ProtocolGenerationError(
        "LiveSplit.Bridge proto files were not found. If running from a source checkout, "
        "initialize submodules with `git submodule update --init`."
    )


def _remove_generated_directory() -> None:
    global _generated_directory
    if _generated_directory is None:
        return
    shutil.rmtree(_generated_directory, ignore_errors=True)
    _generated_directory = None


def load_protocol() -> tuple[ModuleType, ModuleType]:
    """Generate and load protobuf modules in a process-local temporary directory."""
    global _generated_directory, _modules
    if _modules is not None:
        return _modules

    with _lock:
        if _modules is not None:
            return _modules

        proto_root = _source_proto_root()
        proto_files = sorted(proto_root.rglob("*.proto"))
        if not proto_files:
            raise ProtocolGenerationError(f"No proto files found below {proto_root}")

        generated_directory = Path(tempfile.mkdtemp(prefix="livesplit-bridge-proto-"))
        result = protoc.main(
            [
                "grpc_tools.protoc",
                f"-I{proto_root}",
                f"--python_out={generated_directory}",
                *[str(path) for path in proto_files],
            ]
        )
        if result:
            shutil.rmtree(generated_directory, ignore_errors=True)
            raise ProtocolGenerationError(f"protoc exited with status {result}")

        for module_name in _module_names[-2:]:
            if module_name in sys.modules:
                shutil.rmtree(generated_directory, ignore_errors=True)
                raise ProtocolGenerationError(
                    f"Cannot load the bundled schema because {module_name} is already loaded"
                )

        existing_modules = set(sys.modules)
        sys.path.insert(0, str(generated_directory))
        try:
            importlib.invalidate_caches()
            common = importlib.import_module("livesplit.bridge.v1.common_pb2")
            bridge = importlib.import_module("livesplit.bridge.v1.bridge_pb2")
            for module in (common, bridge):
                module_file = module.__file__
                if module_file is None or not Path(module_file).resolve().is_relative_to(
                    generated_directory
                ):
                    raise ProtocolGenerationError(
                        f"Generated module resolved outside {generated_directory}"
                    )
        except Exception:
            for module_name in reversed(_module_names):
                if module_name not in existing_modules:
                    sys.modules.pop(module_name, None)
            shutil.rmtree(generated_directory, ignore_errors=True)
            raise
        finally:
            sys.path.remove(str(generated_directory))

        _generated_directory = generated_directory
        _modules = bridge, common
        return _modules


atexit.register(_remove_generated_directory)
