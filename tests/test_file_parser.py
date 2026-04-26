"""Tests for file_parser module."""
import tempfile
from pathlib import Path

import pytest

from file_parser import (
    SUPPORTED_EXTENSIONS,
    parse_file,
    parse_files,
    format_for_agents,
)


@pytest.fixture
def sample_xlsx(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "매물"
    ws.append(["단지명", "면적", "가격"])
    ws.append(["테스트A", 40.0, 45000])
    ws.append(["테스트B", 35.0, 38000])
    path = tmp_path / "test.xlsx"
    wb.save(path)
    return path


class TestSupportedExtensions:
    def test_xlsx(self):
        assert ".xlsx" in SUPPORTED_EXTENSIONS

    def test_pdf(self):
        assert ".pdf" in SUPPORTED_EXTENSIONS


class TestParseExcel:
    def test_basic_parse(self, sample_xlsx):
        text = parse_file(sample_xlsx)
        assert "단지명" in text
        assert "테스트A" in text
        assert "2행 × 3열" in text

    def test_returns_string(self, sample_xlsx):
        result = parse_file(sample_xlsx)
        assert isinstance(result, str)


class TestParseFiles:
    def test_multiple_files(self, sample_xlsx):
        text = parse_files([sample_xlsx, sample_xlsx])
        assert text.count("단지명") == 2


class TestParseFileErrors:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_file("/nonexistent/file.xlsx")

    def test_unsupported_extension(self, tmp_path):
        p = tmp_path / "test.docx"
        p.write_text("hello")
        with pytest.raises(ValueError, match="지원하지 않는"):
            parse_file(p)


class TestFormatForAgents:
    def test_wraps_with_header(self):
        result = format_for_agents([("test.xlsx", "content here")])
        assert "업로드된 파일 데이터" in result
        assert "test.xlsx" in result

    def test_empty_returns_empty(self):
        assert format_for_agents([]) == ""
