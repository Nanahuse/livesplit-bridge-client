"""Check CI's difference detection, without fetching schemas or testing codegen's models."""

from pathlib import Path

import pytest

from tools.update_protocol import synchronize_generated


@pytest.mark.parametrize("change", ["edit", "missing", "extra"])
def test_generation_check_detects_differences_without_rewriting(
    tmp_path: Path, change: str
) -> None:
    regenerated = {"protocol.py": "# fresh output\n", "__init__.py": "# package\n"}
    synchronize_generated(regenerated, tmp_path, check=False)
    synchronize_generated(regenerated, tmp_path, check=True)
    if change == "edit":
        (tmp_path / "protocol.py").write_text("# stale output\n", encoding="utf-8")
    elif change == "missing":
        (tmp_path / "protocol.py").unlink()
    else:
        (tmp_path / "obsolete.py").write_text("# stale module\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(RuntimeError, match="Generated models differ"):
        synchronize_generated(regenerated, tmp_path, check=True)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    synchronize_generated(regenerated, tmp_path, check=False)
    synchronize_generated(regenerated, tmp_path, check=True)
