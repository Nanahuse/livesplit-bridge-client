"""Protobuf modules generated at runtime from the bundled LiveSplit.Bridge schema."""

from ._protocol import load_protocol

bridge_pb2, common_pb2 = load_protocol()

__all__ = ["bridge_pb2", "common_pb2"]
