"""Build the pinned official v4 Bridge TestHost and run real WebSocket tests (Windows)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, help="existing Bridge checkout at the pinned revision"
    )
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("The official Bridge TestHost requires Windows and .NET 10 SDK")
    source = json.loads((ROOT / "protocol-source.json").read_text())
    checkout = (args.source or ROOT / ".tmp" / "bridge-integration").resolve()
    if not checkout.exists():
        run("git", "clone", "--no-checkout", source["repository"], str(checkout))
        run("git", "checkout", "--detach", source["revision"], cwd=checkout)
    run(sys.executable, "tools/update_protocol.py", "--check", "--source", str(checkout))
    run("git", "submodule", "update", "--init", "--depth", "1", "external/LiveSplit", cwd=checkout)
    run(
        "git",
        "submodule",
        "update",
        "--init",
        "--depth",
        "1",
        "lib/SpeedrunComSharp",
        cwd=checkout / "external" / "LiveSplit",
    )
    project = checkout / "tests/LiveSplit.Bridge.TestHost/LiveSplit.Bridge.TestHost.csproj"
    run("dotnet", "build", str(project), "--configuration", "Release", "--nologo")
    output = ROOT / ".tmp" / "contract-samples"
    samples_project = (
        checkout / "tools/schema/ContractSamples/LiveSplit.Bridge.ContractSamples.csproj"
    )
    run(
        "dotnet",
        "run",
        "--project",
        str(samples_project),
        "--configuration",
        "Release",
        "--",
        str(output),
    )
    env = os.environ.copy()
    env["BRIDGE_TEST_HOST"] = str(
        project.parent / "bin/Release/net4.8.1/LiveSplit.Bridge.TestHost.exe"
    )
    env["BRIDGE_CSHARP_CASES"] = str(output / "csharp-serialized-cases.json")
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "integration"], cwd=ROOT, env=env, check=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
