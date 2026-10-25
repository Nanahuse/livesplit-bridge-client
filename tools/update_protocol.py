# /// script
# requires-python = ">=3.11"
# dependencies = ["datamodel-code-generator==0.86.0", "ruff==0.16.4"]
# ///

"""Generate Pydantic v2 wire models from the pinned official Bridge JSON schemas."""

from __future__ import annotations

import argparse
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


def normalize_run_icons(definitions: dict[str, Any]) -> None:
    """Express only RunIcons' null-array exclusion for codegen's unsupported if/then."""
    icons = definitions["RunIcons"]
    if "if" not in icons and "then" not in icons:
        return
    if (
        icons.get("if")
        != {"properties": {"segment_icons": {"const": None}}, "required": ["segment_icons"]}
        or icons.get("then") != {"properties": {"segment_icons": {"$ref": "#/$defs/ListOfString"}}}
        or definitions["ListOfString"].get("type") != "array"
        or icons["properties"]["segment_icons"].get("type") != ["null", "array"]
        or "else" in icons
    ):
        raise ValueError("Unsupported RunIcons conditional; review the upstream schema")
    icons["properties"]["segment_icons"]["type"] = "array"
    del icons["if"], icons["then"]


def combine(schemas: dict[str, Any]) -> dict[str, Any]:
    """Merge named definitions and preserve each official root union."""
    definitions: dict[str, Any] = {}
    roots = []
    for schema in schemas.values():
        for name, definition in schema["$defs"].items():
            if name in definitions and definitions[name] != definition:
                raise ValueError(f"Official definitions disagree: {name}")
            definitions[name] = definition
        name = schema["title"]
        root = {key: value for key, value in schema.items() if key not in ("$schema", "$defs")}
        if name in definitions:
            raise ValueError(f"Root name conflicts with an official definition: {name}")
        definitions[name] = root
        roots.append({"$ref": f"#/$defs/{name}"})
    normalize_run_icons(definitions)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": definitions,
        "anyOf": roots,
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
    prepared.write_text(json.dumps(combine(schemas), indent=2), encoding="utf-8")
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
            "--use-title-as-name",
            "--use-type-alias",
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
