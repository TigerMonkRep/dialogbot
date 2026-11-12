"""Knowledge from an uploaded file or pasted text (document-extract-v1): safe text extraction per file type, limits and
refusals, chunking, grounding (nothing invented), dedup against existing knowledge / the website import, conflicts,
drafts only (nothing live before approval), batch approval, tenant isolation, roles, rate limit and the migration."""
from __future__ import annotations

import io
import os
import zipfile

import pytest
from sqlalchemy import select, text

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import AiUsage, KnowledgeVersion, SourceImport
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.modules.knowledge import doc_import, documents, importer
from app.modules.knowledge.documents import Section
from tests.test_website_import import fake_fetch

DOC = """Rebotti – håndbog for kunder

Gulvafslibning: Afslibning af trægulve med støvsugeranlæg. Fra 160 kr. pr. m² inkl. moms.
Lakering: Tre lag slidstærk lak på nyslebne gulve. 95 kr. pr. m² inkl. moms.
Åbningstider: hverdage 7-15
Afbestilling: Afbestilling skal ske senest 48 timer før aftalt tid, ellers opkræves 500 kr.
Spørgsmål: Skal vi flytte møblerne selv?
Svar: Ja, rummet skal være tømt, når vi kommer.
Vi dækker: Aarhus, Silkeborg, Skanderborg
Vi må ikke love en fast pris uden besigtigelse.
Kontakt: info@rebotti.dk"""


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    ai_provider.set_provider_override(FakeProvider(get_settings()))
    monkeypatch.setattr(importer, "fetch", fake_fetch)
    yield
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


# --------------------------------------------------------------------------- tiny fixtures, built in memory

def pdf_bytes(pages: list[str]) -> bytes:
    """A minimal valid PDF with one text line per page (Helvetica, WinAnsi)."""
    objs: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font_no = 3 + 2 * n
    for i, t in enumerate(pages):
        lines = t.split("\n")
        ops = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(
            "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for ln in lines) + " ET"
        stream = ops.encode("cp1252")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font_no} 0 R >> >> >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def docx_bytes() -> bytes:
    import docx

    d = docx.Document()
    d.add_heading("Priser", level=1)
    d.add_paragraph("Gulvafslibning: Afslibning af trægulve. Fra 160 kr. pr. m² inkl. moms.")
    d.add_heading("Afbestilling", level=1)
    d.add_paragraph("Afbestilling skal ske senest 48 timer før.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Ydelse", "Pris"
    t.cell(1, 0).text, t.cell(1, 1).text = "Olie", "80 kr"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def xlsx_bytes() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prisliste"
    ws.append(["Ydelse", "Pris", "Enhed"])
    ws.append(["Gulvafslibning", "160 kr", "m²"])
    ws.append(["Lakering", "=10*9.5", "m²"])  # a formula is never evaluated (no cached value → empty)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def zip_with(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
    return buf.getvalue()


# --------------------------------------------------------------------------- extraction per file type

def test_pdf_text_per_page_with_page_refs():
    secs = documents.read_document(pdf_bytes(["Gulvafslibning: 160 kr. pr. m2", "Afbestilling senest 48 timer"]),
                                   "prisliste.pdf")
    assert [s.ref for s in secs] == ["prisliste.pdf · side 1", "prisliste.pdf · side 2"]
    assert "160 kr" in secs[0].text and "48 timer" in secs[1].text


def test_docx_sections_by_heading_and_tables():
    secs = documents.read_document(docx_bytes(), "håndbog.docx")
    refs = [s.ref for s in secs]
    assert refs == ["håndbog.docx · Priser", "håndbog.docx · Afbestilling"]
    assert "160 kr" in secs[0].text and "Olie | 80 kr" in secs[1].text


def test_xlsx_rows_with_header_no_formula_evaluation():
    secs = documents.read_document(xlsx_bytes(), "priser.xlsx")
    assert secs[0].ref == "priser.xlsx · Prisliste · rækker 2–3"
    assert "Ydelse: Gulvafslibning; Pris: 160 kr; Enhed: m²" in secs[0].text
    assert "95" not in secs[0].text  # the formula was not run


def test_csv_and_txt_and_markdown():
    csv_secs = documents.read_document("Ydelse;Pris\nLakering;95 kr\n".encode("cp1252"), "p.csv")
    assert csv_secs[0].text == "Ydelse: Lakering; Pris: 95 kr"
    md = documents.read_document(b"# Om os\nVi er et gulvfirma.\n\n# Priser\nLak 95 kr", "noter.md")
    assert [s.ref for s in md] == ["noter.md · Om os", "noter.md · Priser"]
    assert documents.read_document(b"\xef\xbb\xbfHej med jer", "x.txt")[0].text == "Hej med jer"


@pytest.mark.parametrize("data,name,msg", [
    (b"", "tom.pdf", "tom"),
    (b"\xd0\xcf\x11\xe0" + b"\x00" * 100, "gammel.doc", ".docx"),
    (b"MZ\x90\x00\x03\x00\x00\x00", "virus.pdf", "understøttes ikke"),
    (b"\x89PNG\r\n\x1a\n\x00\x00", "billede.png", "understøttes ikke"),
    (zip_with({"a.txt": b"x"}), "fil.docx", "understøttes ikke"),
    (zip_with({"word/document.xml": b"<x/>", "word/vbaProject.bin": b"x"}), "makro.docm", "makroer"),
    (zip_with({"xl/workbook.xml": b"<x/>", "bomb.xml": b"\x00" * 60_000_000}), "bombe.xlsx", "pakkes ud"),
    (b"%PDF-1.4\nnot really a pdf", "brudt.pdf", "beskadiget"),
])
def test_wrong_or_dangerous_files_are_refused(data, name, msg):
    with pytest.raises(ValidationFailed) as e:
        documents.read_document(data, name)
    assert msg in e.value.message


def test_size_and_page_limits(monkeypatch):
    with pytest.raises(ValidationFailed, match="10 MB"):
        documents.sniff(b"%PDF-" + b"x" * documents.MAX_FILE_BYTES, "stor.pdf")
    monkeypatch.setattr(documents, "MAX_PDF_PAGES", 2)
    with pytest.raises(ValidationFailed, match="3 sider"):
        documents.read_document(pdf_bytes(["a", "b", "c"]), "lang.pdf")
    monkeypatch.setattr(documents, "MAX_TEXT_CHARS", 50)
    secs = documents.read_document(("ord " * 100).encode(), "a.txt")
    assert sum(len(s.text) for s in secs) == 50
    assert documents.safe_name("../../etc/passwd\x00") == "passwd"


def test_chunking_keeps_refs_and_order():
    secs = [Section("a · side 1", "x" * 5000), Section("a · side 2", "y" * 5000), Section("a · side 3", "z" * 5000),
            Section("a · side 4", ("lang afsnit " * 300 + "\n\n") * 6)]
    chunks = documents.chunk(secs, size=12_000)
    assert [s.ref for s in chunks[0]] == ["a · side 1", "a · side 2"]
    assert all(sum(len(s.text) for s in c) <= 12_000 for c in chunks)
    flat = [s.ref for c in chunks for s in c]
    assert flat[2] == "a · side 3" and flat[3].startswith("a · side 4 (del 1)") and flat[-1].startswith("a · side 4 (del")
    assert documents.chunk([Section("t", "x" * 30_000)], size=12_000)[0][0].text == "x" * 12_000  # hard split


def test_grounding_and_numbers():
    t = "Gulvafslibning: Fra 1.200,50 kr. pr. m² inkl. moms."
    assert doc_import.grounded("fra 1.200,50 kr. pr. m²", t)
    assert not doc_import.grounded("Fra 1.400 kr. pr. m²", t)  # a number not in the text
    assert not doc_import.grounded("", t)
    assert doc_import._numbers("1.200,50 kr og 450,- og 12.5%") == [1200.5, 450.0, 12.5]


# --------------------------------------------------------------------------- the whole pipeline through the API

def _upload(api, tok, ws, data: bytes, name: str):
    return api.c.post(f"{api.base}/workspaces/{ws}/knowledge/import/file", params={"name": name}, content=data,
                      headers=api.h(tok, **{"content-type": "application/octet-stream"}))


def _latest(api, tok, ws):
    return api.get(tok, f"/workspaces/{ws}/knowledge/imports/latest").json()["import"]


def test_text_import_categorises_into_drafts_only(api, two_workspaces, fake_ai, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    r = api.post(tok, f"/workspaces/{ws}/knowledge/import/text", {"text": DOC + "\nHALLUCINER"})
    assert r.status_code == 202, r.text
    assert r.json()["source_type"] == "text"
    imp = _latest(api, tok, ws)
    assert imp["status"] == "done", imp
    kinds = {(c["category"], c["kind"]) for c in imp["created_items"]}
    assert kinds >= {("service", "service"), ("opening_hours", "opening_hours"), ("policy", "fact"),
                     ("faq", "known_answer"), ("coverage_area", "coverage_area"), ("rule", "unknown_answer"),
                     ("contact", "fact")}
    titles = {c["title"] for c in imp["created_items"]}
    assert "Opfundet ydelse" not in titles  # its quote is not in the text: dropped, counted
    s = imp["summary"]
    assert s["unverified"] == 1 and s["new"] == len(imp["created_items"]) and s["conflicts"] == 0
    assert s["by_category"]["service"] == 2
    versions = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.workspace_id == ws)).all()
    assert {v.status for v in versions} == {"draft"} and {v.source_type for v in versions} == {"extraction"}
    slib = next(v for v in versions if v.title == "Gulvafslibning")
    assert slib.content["price_net_minor"] is None  # never a guessed number
    assert '"160 kr. pr. m² inkl. moms"' in slib.content["description"]
    assert slib.source_ref == "Indsat tekst" and slib.review_note["relation"] == "new"
    hours = next(v for v in versions if v.title == "Åbningstider")
    assert hours.content["weekly"] == [{"days": ["mon", "tue", "wed", "thu", "fri"], "open": "07:00", "close": "15:00"}]
    assert api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["items"] == []  # nothing live
    usage = db.scalars(select(AiUsage).where(AiUsage.purpose == "source_import")).all()
    assert [u.prompt_version for u in usage] == ["document-extract-v1"]
    # the review queue shows the note; batch approval makes the whole category live in one go
    items = api.get(tok, f"/workspaces/{ws}/knowledge/items?limit=200").json()["items"]
    svc = [i["open_draft"]["id"] for i in items if i["kind"] == "service"]
    assert all(i["open_draft"]["review_note"]["category"] for i in items)
    r = api.post(tok, f"/workspaces/{ws}/knowledge/versions/approve-batch", {"version_ids": svc})
    assert r.status_code == 200 and r.json()["approved"] == 2
    live = api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["items"]
    assert sorted(i["title"] for i in live) == ["Gulvafslibning", "Lakering"]
    # the other workspace sees nothing and cannot approve these drafts
    assert _latest(api, t["tok_b"], t["ws_b"]) is None
    r = api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/knowledge/versions/approve-batch", {"version_ids": svc})
    assert r.status_code == 404


def test_file_upload_dedups_against_website_and_flags_price_conflict(api, two_workspaces, fake_ai, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    # the website import first: Gulvafslibning «Fra 145 kr. pr. m² inkl. moms», Lakering, hours 8-16 (drafts)
    api.post(tok, f"/workspaces/{ws}/knowledge/import", {"url": "https://fjordgulv.dk/"})
    site = _latest(api, tok, ws)
    assert site["status"] == "done" and site["source_type"] == "website"
    lak = next(c for c in site["created_items"] if c["title"] == "Lakering")
    api.approve(tok, ws, lak["version_id"])  # Lakering is live, the rest still awaits review
    before = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.id == lak["version_id"]))
    r = _upload(api, tok, ws, pdf_bytes(DOC.split("\n\n")), "Rebotti håndbog.pdf")
    assert r.status_code == 202, r.text
    imp = _latest(api, tok, ws)
    assert imp["status"] == "done" and imp["source_type"] == "file" and imp["source_name"] == "Rebotti håndbog.pdf"
    s = imp["summary"]
    # Gulvafslibning (website draft, 145 kr) vs the PDF (160 kr): no second draft – a conflict on the website draft
    slib = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.workspace_id == ws,
                                                     KnowledgeVersion.title == "Gulvafslibning")).all()
    assert len(slib) == 1
    db.refresh(slib[0])
    assert "160 kr" in slib[0].review_note["conflicts"][0]["text"] and "145" in slib[0].review_note["conflicts"][0]["text"]
    assert slib[0].review_note["conflicts"][0]["source"].startswith("Rebotti håndbog.pdf · side")
    # Lakering is approved: the PDF's different text becomes an UPDATE draft of the same item, not a duplicate
    upd = next(c for c in imp["created_items"] if c["title"] == "Lakering")
    assert upd["relation"] == "update" and upd["item_id"] == lak["item_id"]
    v = db.get(KnowledgeVersion, upd["version_id"])
    assert v.version_no == 2 and v.status == "draft" and v.source_ref.startswith("Rebotti håndbog.pdf · side")
    # hours: website 8-16 (draft) vs PDF 7-15 → conflict note, still one opening_hours item
    hrs = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.workspace_id == ws,
                                                    KnowledgeVersion.title == "Åbningstider")).all()
    assert len(hrs) == 1 and hrs[0].review_note["conflicts"][0]["text"].startswith("Andre åbningstider")
    assert s["conflicts"] == 2 and s["updates"] == 1 and s["pending"] == 2
    # the approved version is untouched until the update is approved
    db.refresh(before)
    assert before.status == "approved"
    # running the same file again creates nothing new (all overlap)
    _upload(api, tok, ws, pdf_bytes(DOC.split("\n\n")), "Rebotti håndbog.pdf")
    again = _latest(api, tok, ws)
    assert again["created_items"] == [] and again["summary"]["duplicates"] + again["summary"]["pending"] == \
        again["summary"]["found"]


def test_upload_refusals_roles_rate_limit_and_no_raw_storage(api, two_workspaces, fake_ai, db, monkeypatch):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    r = _upload(api, tok, ws, b"MZ\x90\x00binary", "program.exe")
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "file"
    r = _upload(api, tok, ws, b"x" * (documents.MAX_FILE_BYTES + 1), "stor.txt")
    assert r.status_code == 422 and "10 MB" in r.json()["message"]
    assert db.scalar(select(SourceImport)) is None  # refused before any import row
    assert api.post(tok, f"/workspaces/{ws}/knowledge/import/text", {"text": "x" * 200_001}).status_code == 422
    reader = api.add_member(tok, ws, "reader@testmail.dk", "reader")
    assert _upload(api, reader, ws, b"Hej med jer, vi sliber gulve.", "a.txt").status_code == 403
    assert api.post(reader, f"/workspaces/{ws}/knowledge/import/text", {"text": DOC}).status_code == 403
    staff = api.add_member(tok, ws, "staff@testmail.dk", "staff")
    assert _upload(api, staff, ws, DOC.encode(), "noter.txt").status_code == 202
    ids = [c["version_id"] for c in _latest(api, staff, ws)["created_items"]]
    r = api.post(staff, f"/workspaces/{ws}/knowledge/versions/approve-batch", {"version_ids": ids})
    assert r.status_code == 403  # staff may draft, not publish
    # another tenant cannot upload into this workspace
    assert _upload(api, t["tok_b"], ws, DOC.encode(), "x.txt").status_code in (403, 404)
    # the file is not stored anywhere: only counts, names and drafts
    imp = db.scalar(select(SourceImport).where(SourceImport.source_type == "file"))
    with db.bind.connect() as conn:
        raw = conn.execute(text("select row_to_json(s)::text from source_imports s where id = :i"), {"i": imp.id}).scalar()
    assert "Svar: Ja, rummet" not in raw and "info@rebotti.dk" not in raw
    # rate limit: 20 file/text imports per workspace per hour
    monkeypatch.setattr(doc_import, "UPLOADS_PER_HOUR", 2)
    assert api.post(tok, f"/workspaces/{ws}/knowledge/import/text", {"text": DOC}).status_code == 202
    r = api.post(tok, f"/workspaces/{ws}/knowledge/import/text", {"text": DOC})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"


def test_a_running_import_blocks_a_second_and_failures_are_stored(api, two_workspaces, fake_ai, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    db.add(SourceImport(workspace_id=ws, source_type="website", url="https://x.dk", status="running"))
    db.commit()
    r = api.post(tok, f"/workspaces/{ws}/knowledge/import/text", {"text": DOC})
    assert r.status_code == 409 and r.json()["code"] == "import_running"
    db.execute(text("update source_imports set status = 'done'"))
    db.commit()
    r = _upload(api, tok, ws, pdf_bytes(["", ""]), "scannet.pdf")  # no text layer
    assert r.status_code == 202
    imp = _latest(api, tok, ws)
    assert imp["status"] == "failed" and "ikke fundet nogen tekst" in imp["error"]


def test_ai_output_is_validated_against_the_text():
    chunk = [Section("f.pdf · side 2", "Olie: 80 kr pr m². 10 % rabat i januar. Vi dækker Aarhus.")]
    data = {"items": [
        {"category": "service", "title": "Olie", "text": "Olie på gulve.", "price_text": "95 kr", "quote": "Olie: 80 kr pr m²",
         "source": "findes ikke"},
        {"category": "offer", "title": "Januar", "text": "Rabat i januar", "discount_percent": 25, "quote": "10 % rabat i januar"},
        {"category": "coverage_area", "title": "Område", "zones": ["Aarhus", "Odense"], "quote": "Vi dækker Aarhus"},
        {"category": "weird", "title": "x", "quote": "Olie"},
        {"category": "fact", "title": "Opfundet", "text": "Grundlagt 1890", "quote": "Grundlagt i 1890 af Hans"},
    ]}
    out, dropped = doc_import.suggestions(data, chunk)
    by = {s["category"]: s for s in out}
    assert dropped == 1
    assert "95" not in by["service"]["content"]["description"]  # a price not in the text is not passed on
    assert by["service"]["source"] == "f.pdf · side 2"
    assert by["offer"]["kind"] == "fact"  # 25 % is not in the text → not an offer with a number
    assert by["coverage_area"]["content"] == {"zones": ["Aarhus"]}


def test_migration_down_and_up(db):
    from alembic.config import Config

    from alembic import command

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    db.close()
    command.downgrade(cfg, "a16e24b7c9d1")
    try:
        with db.bind.connect() as conn:
            cols = {r[0] for r in conn.execute(text("select column_name from information_schema.columns "
                                                    "where table_name = 'source_imports'"))}
            assert "source_type" not in cols and "summary" not in cols
    finally:
        command.upgrade(cfg, "head")
    with db.bind.connect() as conn:
        cols = {r[0] for r in conn.execute(text("select column_name from information_schema.columns "
                                                "where table_name in ('source_imports', 'knowledge_versions')"))}
    assert {"source_type", "source_name", "summary", "review_note"} <= cols
