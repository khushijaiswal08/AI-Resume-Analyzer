"""Turn uploaded bytes into plain text.

The file type is detected from the first bytes of the file ("magic bytes"), never from the
file name, because a name is just a user-supplied label and can lie.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")

# A DOCX is a compressed ZIP, so a 5 MB upload can inflate to gigabytes (a "ZIP bomb").
# These caps are checked against the sizes the archive declares, before anything is
# decompressed. Python's zipfile never returns more bytes than an entry declares.
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_XML_BYTES = 10 * 1024 * 1024  # word/document.xml of a real resume is far smaller

# Control characters that do not appear in real text files (tab, newlines, vertical tab and
# form feed are allowed). Used to reject binary data that happens to decode.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x9f]")
CP1252_WARNING = (
    "The text file is not UTF-8, so it was read as Windows-1252 (ANSI). "
    "If some characters look wrong, save it as UTF-8 and upload it again."
)


class ParseError(Exception):
    """Base class for input problems. `status_code` maps directly to the HTTP response."""

    status_code = 422


class FileTooLargeError(ParseError):
    """File is over the byte limit or the PDF has too many pages."""

    status_code = 413


class UnsupportedFileTypeError(ParseError):
    """Bytes are not a PDF, DOCX or plain-text file."""

    status_code = 415


class UnreadableFileError(ParseError):
    """File looks like a supported type but no text could be extracted from it."""

    status_code = 422


@dataclass
class ParsedDocument:
    """Text extracted from an upload plus a little metadata for warnings/logging."""

    text: str
    file_type: str
    pages: int | None = None
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


def detect_file_type(data: bytes) -> str:
    """Return "pdf", "docx" or "txt" based on content, or raise UnsupportedFileTypeError."""
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data.startswith(ZIP_MAGIC):
        # DOCX is a ZIP archive; other ZIPs (xlsx, plain .zip) must be rejected.
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
        raise UnsupportedFileTypeError("ZIP archive is not a Word (.docx) document.")
    if decode_text(data) is not None:
        return "txt"
    raise UnsupportedFileTypeError("Unsupported file type. Upload a PDF, DOCX or TXT file.")


def decode_text(data: bytes) -> tuple[str, str] | None:
    """Decode a plain-text upload, returning (text, encoding), or None if it is not text.

    UTF-8 is tried first. Windows editors also save UTF-16 ("Unicode" in Notepad, which
    starts with a byte-order mark) and Windows-1252 ("ANSI", e.g. for an accented name),
    so those are accepted too.
    """
    if data.startswith(UTF16_BOMS):
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return None
        return (text, "utf-16") if _plausible_text(text) else None
    # Binary formats almost always contain NUL bytes; text files never should.
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1252")
    except UnicodeDecodeError:  # cp1252 leaves a few bytes undefined; binary often has them
        return None
    return (text, "cp1252") if _plausible_text(text) else None


def _plausible_text(text: str) -> bool:
    """Sanity check for the fallback decodings, which accept almost any byte sequence.

    Real text has spaces or line breaks and no control characters; random binary rarely
    passes both checks.
    """
    return not _CONTROL_CHARS.search(text) and any(char.isspace() for char in text)


def extract_text(
    data: bytes,
    *,
    max_bytes: int,
    max_pdf_pages: int,
    max_chars: int,
) -> ParsedDocument:
    """Extract text from PDF/DOCX/TXT bytes, enforcing size, page and character limits."""
    if len(data) > max_bytes:
        raise FileTooLargeError(f"File is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    if not data:
        raise UnreadableFileError("The uploaded file is empty.")

    file_type = detect_file_type(data)
    pages: int | None = None
    warnings: list[str] = []
    if file_type == "pdf":
        text, pages = _pdf_to_text(data, max_pdf_pages)
    elif file_type == "docx":
        text = _docx_to_text(data)
    else:
        text, encoding = decode_text(data)  # never None here: detect_file_type checked it
        text = text.lstrip("﻿")
        if encoding == "cp1252":
            warnings.append(CP1252_WARNING)

    text = _normalise(text)
    if not text.strip():
        if file_type == "pdf":
            message = "No text could be extracted. Scanned/image-only PDFs are not supported."
        else:
            message = "The document contains no text."
        raise UnreadableFileError(message)

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return ParsedDocument(
        text=text, file_type=file_type, pages=pages, truncated=truncated, warnings=warnings
    )


def _pdf_to_text(data: bytes, max_pages: int) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UnreadableFileError("Password-protected PDFs are not supported.")
        page_count = len(reader.pages)
        if page_count > max_pages:
            raise FileTooLargeError(f"PDF has {page_count} pages; the limit is {max_pages}.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except ParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise UnreadableFileError("The PDF could not be read; it may be corrupted.") from exc
    return text, page_count


def _docx_to_text(data: bytes) -> str:
    # Imported lazily: python-docx pulls in lxml, which is only needed for DOCX uploads.
    from docx import Document

    _check_docx_size(data)
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises several unrelated exception types
        raise UnreadableFileError("The DOCX file could not be read; it may be corrupted.") from exc

    lines = [paragraph.text for paragraph in document.paragraphs]
    # Many resume templates put content in tables, so read those cells too.
    for table in document.tables:
        for row in table.rows:
            lines.extend(cell.text for cell in row.cells)
    return "\n".join(lines)


def _check_docx_size(data: bytes) -> None:
    """Reject a DOCX that would inflate past the caps, before python-docx unpacks it."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:  # valid: detect_file_type opened it
        entries = archive.infolist()
    total = sum(entry.file_size for entry in entries)
    body = sum(entry.file_size for entry in entries if entry.filename == "word/document.xml")
    if total > MAX_DOCX_UNCOMPRESSED_BYTES or body > MAX_DOCX_XML_BYTES:
        raise FileTooLargeError("The DOCX file expands to too much data to process safely.")


def _normalise(text: str) -> str:
    """Unify line endings and strip trailing spaces so later regexes see consistent input."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()
