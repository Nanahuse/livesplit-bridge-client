# /// script
# requires-python = ">=3.11"
# dependencies = ["datamodel-code-generator==0.86.0", "ruff==0.16.4"]
# ///

"""Generate Pydantic v2 wire models from the pinned official Bridge JSON schemas."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = PROJECT_ROOT / "protocol-source.json"
OUTPUT = PROJECT_ROOT / "src/livesplit_bridge/_generated"
SCHEMA_FILES = ("rpc-request.schema.json", "rpc-response.schema.json", "bridge-event.schema.json")
GENERATOR_VERSION = "0.86.0"
RUFF_VERSION = "0.16.4"


def run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command, cwd=cwd, check=False, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(f"command failed: {command}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def resolve(node: Any, scope: dict[str, Any]) -> Any:
    """Inline document-local references, respecting each nested schema's $id scope."""
    if isinstance(node, list):
        return [resolve(value, scope) for value in node]
    if not isinstance(node, dict):
        return node
    if "$id" in node:
        scope = node
    if "$ref" in node:
        reference = node["$ref"]
        if not reference.startswith("#/") or set(node) != {"$ref"}:
            raise ValueError(f"Unsupported upstream reference: {reference}")
        target = scope
        for part in reference[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return resolve(target, scope)
    return {key: resolve(value, scope) for key, value in node.items() if key != "$defs"}


def normalize(node: Any) -> Any:
    """Resolve the upstream null-exclusion idiom; never invent fields or constraints."""
    if isinstance(node, list):
        return [normalize(value) for value in node]
    if not isinstance(node, dict):
        return node
    node = copy.deepcopy(node)
    if "$ref" in node:
        raise ValueError("Upstream references need resolution before extracting named definitions")
    if "if" in node or "then" in node or "else" in node:
        # if a required property is null, then it must have a non-null type. That
        # branch is impossible, so remove null from the property's allowed types.
        # This preserves nullable ARRAY ITEMS, unlike intersecting the whole 'then'.
        condition, consequence = node.get("if", {}), node.get("then", {})
        keys = list(condition.get("properties", {}))
        if len(keys) != 1:
            raise ValueError("Unsupported upstream conditional")
        key = keys[0]
        expected = {"properties": {key: {"const": None}}, "required": [key]}
        target = consequence.get("properties", {}).get(key, {})
        target_type = target.get("type")
        types = node.get("properties", {}).get(key, {}).get("type")
        if (
            condition != expected
            or set(consequence) != {"properties"}
            or set(consequence["properties"]) != {key}
            or "else" in node
            or not isinstance(target_type, str)
            or target_type == "null"
            or not isinstance(types, list)
            or set(types) != {"null", target_type}
        ):
            raise ValueError("Unsupported upstream conditional; do not silently drop constraints")
        node["properties"][key]["type"] = target_type
        del node["if"], node["then"]
    # Enums in the C# schemas omit a redundant JSON type. Supply it so codegen
    # emits StrEnum rather than an untyped Enum. Values still come only from C#.
    if "enum" in node and all(isinstance(value, str) for value in node["enum"]):
        node.setdefault("type", "string")
    return {key: normalize(value) for key, value in node.items() if key not in ("$id", "$schema")}


def prepare(schemas: dict[str, Any]) -> dict[str, Any]:
    names = json.loads((PROJECT_ROOT / "tools/protocol_names.json").read_text())
    definitions: dict[str, Any] = {}
    for filename, schema in schemas.items():
        seen: set[str] = set()

        def extract(value: Any, pointer: str = "") -> Any:
            if isinstance(value, list):
                return [extract(item, f"{pointer}/{i}") for i, item in enumerate(value)]
            if not isinstance(value, dict):
                return value
            result = {key: extract(item, f"{pointer}/{key}") for key, item in value.items()}
            name = names[filename].get(pointer)
            if name is None:
                return result
            seen.add(pointer)
            nullable = isinstance(result.get("type"), list) and "null" in result["type"]
            if nullable:
                kinds = [kind for kind in result["type"] if kind != "null"]
                result["type"] = kinds[0] if len(kinds) == 1 else kinds
            if name in definitions and definitions[name] != result:
                raise ValueError(f"Named definitions disagree: {name} at {filename}{pointer}")
            definitions[name] = result
            reference = {"$ref": f"#/$defs/{name}"}
            return {"anyOf": [reference, {"type": "null"}]} if nullable else reference

        extract(normalize(resolve(schema, schema)))
        if seen != set(names[filename]):
            raise ValueError(f"Stale naming hints in {filename}: {set(names[filename]) - seen}")

    def discriminator_values(branches: list[dict[str, Any]], field: str) -> list[str]:
        values: list[str] = []
        for branch in branches:
            discriminator = branch["properties"][field]
            for value in discriminator.get("enum", [discriminator.get("const")]):
                if not isinstance(value, str):
                    raise ValueError(f"Expected string discriminator: {field}")
                if value not in values:
                    values.append(value)
        return values

    # Public convenience enums are unions of the schema's discriminator values.
    definitions["EventType"] = {
        "type": "string",
        "enum": discriminator_values(schemas["bridge-event.schema.json"]["oneOf"], "type"),
    }
    game_requests = [
        variant
        for variant in schemas["rpc-request.schema.json"]["oneOf"]
        if variant["properties"]["method"].get("const") == "game_time_operation"
    ]
    definitions["GameTimeOperation"] = {
        "type": "string",
        "enum": discriminator_values(
            [variant["properties"]["params"] for variant in game_requests], "operation"
        ),
    }
    request_refs = definitions["RpcRequest"]["oneOf"]
    definitions["GameTimeRequest"] = {
        "oneOf": [
            ref
            for ref in request_refs
            if definitions[ref["$ref"].rsplit("/", 1)[1]]["properties"]["method"].get("const")
            == "game_time_operation"
        ]
    }
    response_refs = definitions["RpcResponse"]["oneOf"]
    definitions["SuccessResponse"] = {
        "oneOf": [
            ref
            for ref in response_refs
            if "result" in definitions[ref["$ref"].rsplit("/", 1)[1]]["properties"]
        ]
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": definitions,
        "anyOf": [
            {"$ref": f"#/$defs/{name}"}
            for name in (
                "RpcRequest",
                "RpcResponse",
                "BridgeEvent",
                "EventType",
                "GameTimeOperation",
                "GameTimeRequest",
                "SuccessResponse",
            )
        ],
    }


def generate(checkout: Path, revision: str, directory: Path) -> dict[str, str]:
    actual = run(["git", "rev-parse", "HEAD"], cwd=checkout).strip()
    if actual != revision:
        raise RuntimeError(f"Expected Bridge revision {revision}, got {actual}")
    schemas = {}
    for name in SCHEMA_FILES:
        # Use committed blobs; local edits cannot change the generation input.
        content = run(["git", "show", f"{revision}:schemas/v4/{name}"], cwd=checkout)
        path = directory / name
        path.write_text(content, encoding="utf-8")
        schemas[name] = json.loads(content)
    prepared = directory / "protocol.schema.json"
    prepared.write_text(json.dumps(prepare(schemas), indent=2), encoding="utf-8")
    # Give the supported Ruff formatters the same pinned project configuration.
    (directory / "pyproject.toml").write_text(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    output = directory / "protocol.py"
    header = (
        f"# Generated from LiveSplit.Bridge@{revision}\n"
        f"# datamodel-code-generator {GENERATOR_VERSION}; Ruff {RUFF_VERSION}.\n"
        "# DO NOT EDIT. Run: uv run tools/update_protocol.py"
    )
    run(
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            str(prepared),
            "--input-file-type",
            "jsonschema",
            "--output",
            str(output),
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--target-python-version",
            "3.11",
            "--target-pydantic-version",
            "2.11",
            "--disable-timestamp",
            "--strict-types",
            "str",
            "int",
            "bool",
            "--field-constraints",
            "--use-standard-collections",
            "--use-union-operator",
            "--use-annotated",
            "--use-subclass-enum",
            "--use-field-description",
            "--capitalise-enum-members",
            "--extra-fields",
            "forbid",
            "--strict-nullable",
            "--formatters",
            "ruff-check",
            "ruff-format",
            "--custom-file-header",
            header,
            "--ignore-pyproject",
        ],
        cwd=PROJECT_ROOT,
    )
    return {
        "protocol.py": output.read_text(encoding="utf-8"),
        "__init__.py": "# Generated package. Do not edit; run tools/update_protocol.py.\n",
    }


def synchronize_generated(generated: dict[str, str], destination: Path, *, check: bool) -> None:
    existing = {path.name for path in destination.glob("*.py")}
    if check:
        if existing != set(generated) or any(
            not (destination / name).is_file()
            or (destination / name).read_text(encoding="utf-8") != content
            for name, content in generated.items()
        ):
            raise RuntimeError("Generated models differ; run uv run tools/update_protocol.py")
        return
    destination.mkdir(parents=True, exist_ok=True)
    for name in existing - set(generated):
        (destination / name).unlink()
    for name, content in generated.items():
        (destination / name).write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="regenerate and fail on differences")
    parser.add_argument("--source", type=Path, help="use an existing pinned Bridge checkout")
    args = parser.parse_args()
    for package, expected in (
        ("datamodel-code-generator", GENERATOR_VERSION),
        ("ruff", RUFF_VERSION),
    ):
        if version(package) != expected:
            raise RuntimeError(f"Use {package}=={expected} for deterministic generation")
    source = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="livesplit-bridge-codegen-") as temporary:
        directory = Path(temporary)
        checkout = args.source.resolve() if args.source else directory / "Bridge"
        if args.source is None:
            run(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    source["repository"],
                    str(checkout),
                ],
                cwd=PROJECT_ROOT,
            )
            run(["git", "checkout", "--detach", source["revision"]], cwd=checkout)
        generated = generate(checkout, source["revision"], directory)
        synchronize_generated(generated, OUTPUT, check=args.check)
    print(f"Models {'verified' if args.check else 'generated'} from Bridge@{source['revision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
