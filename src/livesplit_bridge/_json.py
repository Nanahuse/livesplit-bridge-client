"""JSON decoding shared by the two WebSocket transports."""

import json
from typing import Any


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON property: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def decode_object(payload: str | bytes) -> dict[str, Any]:
    # recv_data() returns UTF-8 bytes even for Text messages.
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    value = json.loads(payload, object_pairs_hook=_object, parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value
