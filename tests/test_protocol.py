from __future__ import annotations

from pathlib import Path

from livesplit_bridge import bridge_pb2, common_pb2


def test_runtime_modules_and_stubs_are_installed() -> None:
    assert bridge_pb2.__file__ is not None
    assert common_pb2.__file__ is not None
    bridge_path = Path(bridge_pb2.__file__).resolve()
    common_path = Path(common_pb2.__file__).resolve()

    assert bridge_path.name == "bridge_pb2.py"
    assert common_path.name == "common_pb2.py"
    assert bridge_path.with_suffix(".pyi").is_file()
    assert common_path.with_suffix(".pyi").is_file()


def test_protocol_descriptors_point_to_upstream_proto_names() -> None:
    assert bridge_pb2.DESCRIPTOR.name == "livesplit/bridge/v1/bridge.proto"
    assert common_pb2.DESCRIPTOR.name == "livesplit/bridge/v1/common.proto"
