import io
import zipfile

import pytest

from resume_analyzer.parsing import (
    FileTooLargeError,
    UnreadableFileError,
    UnsupportedFileTypeError,
    detect_file_type,
    extract_text,
)
from tests.conftest import SAMPLE_RESUME, make_docx, make_pdf

LIMITS = {"max_bytes": 5 * 1024 * 1024, "max_pdf_pages": 10, "max_chars": 50_000}


def parse(data: bytes, **overrides):
    return extract_text(data, **{**LIMITS, **overrides})


def test_txt_is_parsed():
    doc = parse(SAMPLE_RESUME.encode("utf-8"))
    assert doc.file_type == "txt"
    assert "FastAPI" in doc.text


def test_txt_with_bom_and_crlf_is_normalised():
    doc = parse("﻿Line one\r\nLine two  \r\n".encode())
    assert doc.text == "Line one\nLine two"


def test_pdf_is_parsed():
    doc = parse(make_pdf("Skills\nPython and Docker"))
    assert doc.file_type == "pdf"
    assert doc.pages == 1
    assert "Python" in doc.text


def test_docx_paragraphs_and_tables_are_parsed():
    doc = parse(make_docx("Skills\nPython", table_cells=["Kubernetes", "Terraform"]))
    assert doc.file_type == "docx"
    assert "Python" in doc.text
    assert "Terraform" in doc.text


def test_type_is_detected_by_magic_bytes_not_name():
    # PNG signature: binary content must be rejected whatever the file is called.
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    with pytest.raises(UnsupportedFileTypeError) as exc:
        parse(png)
    assert exc.value.status_code == 415


def test_zip_that_is_not_docx_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "hi")
    with pytest.raises(UnsupportedFileTypeError):
        detect_file_type(buffer.getvalue())


def test_non_utf8_binary_is_rejected():
    with pytest.raises(UnsupportedFileTypeError):
        parse(bytes([0xFF, 0xFE, 0xFA, 0x81]) * 10)


@pytest.mark.parametrize("data", [b"", b"   \n\t  "])
def test_empty_input_is_422(data):
    with pytest.raises(UnreadableFileError) as exc:
        parse(data)
    assert exc.value.status_code == 422


def test_pdf_without_text_is_422():
    with pytest.raises(UnreadableFileError):
        parse(make_pdf(""))


def test_corrupted_pdf_is_422():
    with pytest.raises(UnreadableFileError):
        parse(b"%PDF-1.4\nthis is not really a pdf")


def test_file_over_size_limit_is_413():
    with pytest.raises(FileTooLargeError) as exc:
        parse(b"a" * 101, max_bytes=100)
    assert exc.value.status_code == 413


def test_pdf_over_page_limit_is_413():
    with pytest.raises(FileTooLargeError):
        parse(make_pdf("Python", pages=3), max_pdf_pages=2)


def test_long_text_is_truncated():
    doc = parse(b"word " * 100, max_chars=50)
    assert doc.truncated
    assert len(doc.text) == 50


def test_windows_1252_txt_is_accepted_with_warning():
    # Older Windows editors save "ANSI" text: the accented name and smart quotes are not UTF-8.
    data = "José Sampleton – “fictional”\nSkills\nPython".encode("cp1252")
    doc = parse(data)
    assert doc.file_type == "txt"
    assert doc.text.startswith("José Sampleton")
    assert any("Windows-1252" in warning for warning in doc.warnings)


def test_utf16_txt_with_bom_is_accepted():
    # Notepad's "Unicode" option saves UTF-16 with a byte-order mark (and many NUL bytes).
    data = "José Sampleton\nSkills\nPython".encode("utf-16")
    doc = parse(data)
    assert doc.file_type == "txt"
    assert doc.text == "José Sampleton\nSkills\nPython"
    assert doc.warnings == []


def test_utf8_txt_has_no_encoding_warning():
    assert parse(SAMPLE_RESUME.encode("utf-8")).warnings == []


def test_empty_docx_and_blank_txt_do_not_mention_pdfs():
    for data in (make_docx(""), b"   \n\t  "):
        with pytest.raises(UnreadableFileError) as exc:
            parse(data)
        assert "PDF" not in str(exc.value)
        assert "no text" in str(exc.value)


def test_docx_zip_bomb_is_rejected_before_parsing():
    # A tiny upload whose document.xml inflates to 20 MB must be refused as too large,
    # without python-docx ever decompressing it.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", b" " * (20 * 1024 * 1024))
    data = buffer.getvalue()
    assert len(data) < 100 * 1024
    with pytest.raises(FileTooLargeError) as exc:
        parse(data)
    assert exc.value.status_code == 413


def test_docx_with_huge_total_size_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "<w:document/>")
        archive.writestr("word/media/padding.bin", b"\x00" * (60 * 1024 * 1024))
    with pytest.raises(FileTooLargeError):
        parse(buffer.getvalue())
