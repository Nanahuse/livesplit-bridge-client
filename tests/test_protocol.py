from __future__ import annotations

from livesplit_bridge import common_pb2, run_pb2


def test_timer_snapshot_exposes_run_revision() -> None:
    snapshot = common_pb2.TimerSnapshot(run_revision=123)

    assert snapshot.run_revision == 123


def test_run_snapshot_is_constructible() -> None:
    snapshot = run_pb2.RunSnapshot(session_id=1, run_revision=2)

    assert snapshot.session_id == 1
    assert snapshot.run_revision == 2


def test_segment_info_is_constructible() -> None:
    segment = run_pb2.SegmentInfo(index=0, name="Segment 1")

    assert segment.index == 0
    assert segment.name == "Segment 1"


def test_run_snapshot_optional_presence() -> None:
    snapshot = run_pb2.RunSnapshot()

    assert not snapshot.HasField("file_path")

    snapshot.file_path = "test.lss"

    assert snapshot.HasField("file_path")
