# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Synchronize the official JSON v4 schemas from the pinned Bridge revision."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = PROJECT_ROOT / "protocol-source.json"
SCHEMA_FILES = ("rpc-request.schema.json", "rpc-response.schema.json", "bridge-event.schema.json")


def run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command, cwd=cwd, check=False, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(f"command failed: {command}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def synchronize(checkout: Path, revision: str, *, check: bool) -> None:
    actual = run(["git", "rev-parse", "HEAD"], cwd=checkout).strip()
    if actual != revision:
        raise RuntimeError(f"Expected Bridge revision {revision}, got {actual}")
    files = {f"schemas/v4/{name}": PROJECT_ROOT / "schemas/v4" / name for name in SCHEMA_FILES}
    files["tools/schema/samples/validation-cases.json"] = (
        PROJECT_ROOT / "tests/fixtures/validation-cases.json"
    )
    for upstream_path, path in files.items():
        # Read the committed blob so local changes cannot contaminate the contract.
        content = run(["git", "show", f"{revision}:{upstream_path}"], cwd=checkout)
        json.loads(content)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise RuntimeError(f"Contract differs from pinned Bridge revision: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without rewriting files")
    parser.add_argument("--source", type=Path, help="use an existing pinned Bridge checkout")
    args = parser.parse_args()
    source = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    revision = source["revision"]
    if args.source is not None:
        synchronize(args.source.resolve(), revision, check=args.check)
    else:
        with tempfile.TemporaryDirectory(prefix="livesplit-bridge-schema-") as directory:
            checkout = Path(directory) / "Bridge"
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
            run(["git", "checkout", "--detach", revision], cwd=checkout)
            synchronize(checkout, revision, check=args.check)
    print(f"Schemas {'verified' if args.check else 'synchronized'} from Bridge@{revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
