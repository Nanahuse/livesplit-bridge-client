# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def run(*command: str, cwd: Path | None = None) -> None:
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    tests = project_root / "tests"
    with tempfile.TemporaryDirectory(prefix="livesplit-bridge-consumer-") as directory:
        consumer = Path(directory)
        run("uv", "init", "--bare", str(consumer))
        run(
            "uv",
            "add",
            "--project",
            str(consumer),
            str(project_root),
            "pytest>=8,<10",
        )
        run(
            "uv",
            "run",
            "--project",
            str(consumer),
            "python",
            "-c",
            "import livesplit_bridge as b; assert 'site-packages' in b.__file__, b.__file__",
        )
        run("uv", "run", "--project", str(consumer), "pytest", "-q", str(tests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
