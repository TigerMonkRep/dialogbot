"""Read an uploaded document (or pasted text) into plain-text sections – safely, server-side, without storing it.

Accepted: PDF, DOCX, XLSX, CSV, TXT/MD. The type is decided by the file's magic bytes and structure, never by the
name alone. Limits: 10 MB upload, 200 pages (PDF) / 200 sheets×rows-sections, 200 000 characters of extracted text.
Office files (zip) are checked BEFORE a parser sees them: entry count, declared uncompressed size (50 MB) and the
compression ratio (zip bombs), macro parts (vbaProject.bin → refused), and the required main part. No external
references are followed (python-docx/openpyxl never fetch; openpyxl uses defusedxml when installed; lxml in
python-docx runs with resolve_entities=False), and no formulas or macros are evaluated (openpyxl data_only reads the
cached values).

The raw bytes live only in memory for the duration of `read_document`; nothing is written to disk or the database.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass

from app.core.errors import ValidationFailed

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_TEXT_CHARS = 200_000
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 2_000
MAX_ZIP_RATIO = 100  # uncompressed / compressed for any single entry
MAX_ROWS = 5_000  # spreadsheet rows read in total
ROWS_PER_SECTION = 40

KINDS = ("pdf", "docx", "xlsx", "csv", "txt")
LABEL = {"pdf": "PDF", "docx": "Word", "xlsx": "Excel", "csv": "CSV", "txt": "tekst"}


@dataclass
class Section:
    ref: str  # where in the source: "prisliste.pdf · side 3", "håndbog.docx · Afbestilling", "Indsat tekst · afsnit 2"
    text: str


def _bad(msg: str) -> ValidationFailed:
    return ValidationFailed(msg, field_errors=[{"field": "file"}])


def _clean(s: str) -> str:
    s = s.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in s.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def safe_name(name: str | None) -> str:
    """Display name only (never a path): last path segment, control characters removed, max 120 chars."""
    n = re.split(r"[\\/]", (name or "").strip())[-1]
    n = re.sub(r"[\x00-\x1f\x7f]", "", n).strip()
    return n[:120] or "dokument"


# --------------------------------------------------------------------------- type detection

def sniff(data: bytes, name: str) -> str:
    """'pdf' | 'docx' | 'xlsx' | 'csv' | 'txt'. Raises ValidationFailed for anything else (incl. .doc/.xls, macros)."""
    if not data:
        raise _bad("Filen er tom.")
    if len(data) > MAX_FILE_BYTES:
        raise _bad("Filen er for stor. Højst 10 MB.")
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        raise _bad("Gamle Word/Excel-filer (.doc/.xls) kan ikke læses. Gem filen som .docx eller .xlsx, og prøv igen.")
    if data.startswith(b"PK\x03\x04"):
        return _zip_kind(data)
    if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):  # binary, not text
        raise _bad("Filtypen understøttes ikke. Brug PDF, Word (.docx), Excel (.xlsx), CSV eller tekst (.txt/.md).")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext in ("exe", "dll", "zip", "png", "jpg", "jpeg", "gif", "doc", "xls", "rtf", "html", "htm", "js"):
        raise _bad("Filtypen understøttes ikke. Brug PDF, Word (.docx), Excel (.xlsx), CSV eller tekst (.txt/.md).")
    return "csv" if ext == "csv" else "txt"


def _zip_kind(data: bytes) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = z.infolist()
    except (zipfile.BadZipFile, ValueError) as e:
        raise _bad("Filen er beskadiget og kan ikke læses.") from e
    if len(infos) > MAX_ZIP_ENTRIES:
        raise _bad("Filen indeholder for mange dele til at blive læst sikkert.")
    total = 0
    names = set()
    for i in infos:
        total += i.file_size
        names.add(i.filename)
        if i.file_size > MAX_UNZIPPED_BYTES or total > MAX_UNZIPPED_BYTES:
            raise _bad("Filen fylder for meget, når den pakkes ud, til at blive læst sikkert.")
        if i.compress_size and i.file_size / i.compress_size > MAX_ZIP_RATIO and i.file_size > 1_000_000:
            raise _bad("Filen fylder for meget, når den pakkes ud, til at blive læst sikkert.")
        if i.flag_bits & 0x1:
            raise _bad("Filen er krypteret. Fjern adgangskoden, og prøv igen.")
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise _bad("Filen indeholder makroer. Gem den uden makroer (.docx/.xlsx), og prøv igen.")
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    raise _bad("Filtypen understøttes ikke. Brug PDF, Word (.docx), Excel (.xlsx), CSV eller tekst (.txt/.md).")


# --------------------------------------------------------------------------- readers

def _decode(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


PDF_LIMITS = {  # pypdf's own resource ceilings, lowered; and never the external jbig2dec program
    "maximum_declared_stream_length": 20_000_000, "zlib_maximum_output_length": 20_000_000,
    "lzw_maximum_output_length": 20_000_000, "run_length_maximum_output_length": 20_000_000,
    "brotli_maximum_output_length": 20_000_000, "jbig2_maximum_output_length": 20_000_000,
    "array_based_stream_maximum_output_length": 20_000_000, "image_maximum_buffer_size": 20_000_000,
    "stream_decoding_work_maximum_length": 60_000_000, "page_tree_maximum_entries": 5_000,
    "jbig2dec_binary": None,
}


def _pdf(data: bytes, name: str) -> list[Section]:
    import pypdf

    with pypdf.apply_configuration(**PDF_LIMITS):
        return _pdf_read(pypdf, data, name)


def _pdf_read(pypdf, data: bytes, name: str) -> list[Section]:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise _bad("PDF'en er beskyttet med adgangskode. Fjern beskyttelsen, og prøv igen.")
        n = len(reader.pages)
    except ValidationFailed:
        raise
    except Exception as e:  # noqa: BLE001 - any parser error is "cannot read"
        raise _bad("PDF'en er beskadiget og kan ikke læses.") from e
    if n > MAX_PDF_PAGES:
        raise _bad(f"PDF'en har {n} sider. Højst {MAX_PDF_PAGES} sider ad gangen – del den op, og prøv igen.")
    out, total = [], 0
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = _clean(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - one unreadable page does not stop the rest
            continue
        if text:
            out.append(Section(f"{name} · side {i}", text))
            total += len(text)
            if total > MAX_TEXT_CHARS:
                break
    return out


def _docx(data: bytes, name: str) -> list[Section]:
    import docx

    try:
        d = docx.Document(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise _bad("Word-filen er beskadiget og kan ikke læses.") from e
    out: list[Section] = []
    heading, buf, total = "", [], 0

    def flush():
        nonlocal buf
        text = _clean("\n".join(buf))
        if text:
            out.append(Section(f"{name} · {heading[:80]}" if heading else f"{name} · afsnit {len(out) + 1}", text))
        buf = []

    body = d.element.body
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, d)
            txt = p.text.strip()
            style = (p.style.name if p.style is not None else "") or ""
            if txt and style.lower().startswith(("heading", "overskrift", "title", "titel")):
                flush()
                heading = txt
                buf.append(f"## {txt}")
            elif txt:
                buf.append(txt)
            total += len(txt)
        elif tag == "tbl":
            for row in Table(child, d).rows:
                cells = []
                for c in row.cells:
                    t = c.text.strip()
                    if t and (not cells or cells[-1] != t):  # merged cells repeat
                        cells.append(t)
                if cells:
                    buf.append(" | ".join(cells))
                    total += len(buf[-1])
        if total > MAX_TEXT_CHARS:
            break
    flush()
    return out


def _rows_to_sections(rows: list[list[str]], ref: str) -> list[Section]:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [c.strip() for c in rows[0]]
    while header and not header[-1]:
        header.pop()
    has_header = len(rows) > 1 and bool(header) and all(header) and \
        not any(re.fullmatch(r"[\d.,\s-]+", c) for c in header)
    body = rows[1:] if has_header else rows
    out = []
    for start in range(0, len(body), ROWS_PER_SECTION):
        chunk = body[start:start + ROWS_PER_SECTION]
        lines = []
        for r in chunk:
            cells = [c.strip() for c in r]
            if has_header:
                lines.append("; ".join(f"{h}: {v}" for h, v in zip(header, cells, strict=False) if v))
            else:
                lines.append(" | ".join(c for c in cells if c))
        first = start + (2 if has_header else 1)
        out.append(Section(f"{ref} · rækker {first}–{first + len(chunk) - 1}", "\n".join(lines)))
    return out


def _csv(data: bytes, name: str) -> list[Section]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for i, r in enumerate(csv.reader(io.StringIO(text), dialect)):
        if i >= MAX_ROWS:
            break
        rows.append([c[:2000] for c in r[:50]])
    return _rows_to_sections(rows, name)


def _xlsx(data: bytes, name: str) -> list[Section]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
    except Exception as e:  # noqa: BLE001
        raise _bad("Excel-filen er beskadiget og kan ikke læses.") from e
    out: list[Section] = []
    budget = MAX_ROWS
    try:
        for ws in wb.worksheets[:50]:
            rows = []
            for r in ws.iter_rows(values_only=True, max_col=50):
                if budget <= 0:
                    break
                budget -= 1
                rows.append(["" if v is None else str(v)[:2000] for v in r])
            out += _rows_to_sections(rows, f"{name} · {ws.title}")
    finally:
        wb.close()
    return out


def _txt(data: bytes, name: str) -> list[Section]:
    return split_text(_decode(data), name)


def split_text(text: str, ref: str) -> list[Section]:
    """Plain/markdown text → sections by markdown heading, else by blank-line paragraphs (grouped ~3 000 chars)."""
    text = _clean(text)
    if not text:
        return []
    parts = re.split(r"\n(?=#{1,4} )", text)
    if len(parts) > 1:
        out = []
        for p in parts:
            head = p.split("\n", 1)[0].lstrip("#").strip()
            if p.strip():
                out.append(Section(f"{ref} · {head[:80]}" if p.startswith("#") else f"{ref} · indledning", p.strip()))
        return out
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, buf, n = [], [], 1
    for p in paras:
        buf.append(p.strip())
        if sum(len(b) for b in buf) >= 3000:
            out.append(Section(f"{ref} · afsnit {n}", "\n\n".join(buf)))
            buf, n = [], n + 1
    if buf:
        out.append(Section(f"{ref} · afsnit {n}" if out else ref, "\n\n".join(buf)))
    return out


READERS = {"pdf": _pdf, "docx": _docx, "xlsx": _xlsx, "csv": _csv, "txt": _txt}


def read_document(data: bytes, name: str, kind: str | None = None) -> list[Section]:
    """Bytes → sections (≤ MAX_TEXT_CHARS in total). Raises ValidationFailed with a message for the owner."""
    name = safe_name(name)
    kind = kind or sniff(data, name)
    sections = READERS[kind](data, name)
    out, total = [], 0
    for s in sections:
        if total >= MAX_TEXT_CHARS:
            break
        s.text = s.text[: MAX_TEXT_CHARS - total]
        total += len(s.text)
        out.append(s)
    if not out:
        raise _bad("Der blev ikke fundet nogen tekst i filen. Er det et scannet billede? Så indsæt teksten i stedet.")
    return out


# --------------------------------------------------------------------------- chunking

CHUNK_CHARS = 12_000
MAX_CHUNKS = 20


def chunk(sections: list[Section], size: int = CHUNK_CHARS) -> list[list[Section]]:
    """Group sections into AI-sized chunks (≤ `size` chars each). A section longer than `size` is split at paragraph
    (then line, then hard) boundaries; every piece keeps its section's reference. Order is preserved."""
    pieces: list[Section] = []
    for s in sections:
        if len(s.text) <= size:
            pieces.append(s)
            continue
        part, n = "", 1
        for para in re.split(r"(\n\s*\n|\n)", s.text):
            while len(para) > size:  # one enormous paragraph
                if part:
                    pieces.append(Section(f"{s.ref} (del {n})", part.strip()))
                    part, n = "", n + 1
                pieces.append(Section(f"{s.ref} (del {n})", para[:size]))
                para, n = para[size:], n + 1
            if len(part) + len(para) > size and part.strip():
                pieces.append(Section(f"{s.ref} (del {n})", part.strip()))
                part, n = "", n + 1
            part += para
        if part.strip():
            pieces.append(Section(f"{s.ref} (del {n})" if n > 1 else s.ref, part.strip()))
    chunks: list[list[Section]] = []
    cur: list[Section] = []
    cur_len = 0
    for p in pieces:
        if cur and cur_len + len(p.text) > size:
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += len(p.text)
    if cur:
        chunks.append(cur)
    return chunks[:MAX_CHUNKS]
