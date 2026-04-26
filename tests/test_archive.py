"""Tests for archive module."""
from datetime import datetime

from archive import (
    build_frontmatter,
    parse_frontmatter,
    save_session,
    load_session,
    delete_session,
    list_sessions,
    build_context_block,
    MeetingRecord,
)


class TestFrontmatter:
    def test_build_and_parse_roundtrip(self):
        dt = datetime(2026, 4, 17, 14, 30)
        fm = build_frontmatter(topic="테스트 안건", started_at=dt)
        meta, body = parse_frontmatter(fm + "\n# 본문")
        assert meta["topic"] == "테스트 안건"
        assert meta["date"] == "2026-04-17"
        assert meta["time"] == "14:30"
        assert "본문" in body

    def test_parse_no_frontmatter(self):
        meta, body = parse_frontmatter("# Just a heading\nSome text")
        assert meta == {}
        assert "Just a heading" in body

    def test_tags_are_list(self):
        dt = datetime(2026, 1, 1)
        fm = build_frontmatter(topic="t", started_at=dt, tags=["a", "b"])
        meta, _ = parse_frontmatter(fm)
        assert isinstance(meta["tags"], list)
        assert "a" in meta["tags"]


class TestSessionCheckpoint:
    def test_save_and_load(self):
        data = {"topic": "test", "value": 42}
        save_session("_test_session", data)
        loaded = load_session("_test_session")
        assert loaded["topic"] == "test"
        assert loaded["value"] == 42
        delete_session("_test_session")

    def test_load_nonexistent(self):
        assert load_session("_nonexistent_session_xyz") is None

    def test_delete(self):
        save_session("_test_del", {"x": 1})
        assert delete_session("_test_del")
        assert load_session("_test_del") is None

    def test_delete_nonexistent(self):
        assert not delete_session("_nonexistent_xyz")


class TestBuildContextBlock:
    def test_empty_returns_empty(self):
        assert build_context_block([]) == ""

    def test_contains_meeting_info(self):
        from pathlib import Path
        record = MeetingRecord(
            path=Path("/tmp/test.md"),
            topic="테스트 회의",
            date="2026-04-01",
            time="10:00",
            tags=["meeting"],
            summary="요약 텍스트",
        )
        text = build_context_block([record])
        assert "테스트 회의" in text
        assert "요약 텍스트" in text
        assert "과거 회의 맥락" in text
