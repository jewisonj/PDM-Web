"""Build Book PDF generation -- phase 2 of the shop-floor Build Book.

Takes the BuildBook JSON computed by the frontend (frontend/src/utils/buildBook.ts,
the single source of truth for packages/kits/milestones) and renders a
letter-portrait PDF:

  1. Cover (project summary, milestones, hours by area, stock pulls, reference docs)
  2. Reference document prints (csd items) bound right behind the cover
  3. Day-by-day station loading calendar
  4. Work packages (sequence order, checkboxes, sign-off lines)
  5. Kit & weld sheets, each followed by its prints -- assembly drawing first,
     then part prints, each print bound once at its first use in the book

Prints are pulled fresh from the files table / storage at generation time, same
machinery as print_packet.py. Result is uploaded to the print-packets bucket as
{project_code}/{project_code}_build_book.pdf and returned as a signed URL.
"""

import concurrent.futures
import io
import logging
from datetime import datetime

import httpx
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from .supabase import get_supabase_admin

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = letter  # 612 x 792 portrait
MARGIN = 40
INK = colors.HexColor("#16181a")
RULE = colors.HexColor("#9aa0a5")
RULE_LT = colors.HexColor("#c9cdd1")
SHADE = colors.HexColor("#f1f2f3")
SHADE_MD = colors.HexColor("#e4e6e8")


# ============================================================================
# PDF fetch helpers (mirrors print_packet.py conventions)
# ============================================================================

def _fetch_pdf_paths(supabase, item_numbers: list[str]) -> dict[str, str]:
    """item_number -> newest PDF file_path ('bucket/path/file.pdf')."""
    if not item_numbers:
        return {}
    items = (
        supabase.table("items")
        .select("id, item_number")
        .in_("item_number", item_numbers)
        .execute()
    )
    id_by_num = {r["item_number"]: r["id"] for r in (items.data or [])}
    if not id_by_num:
        return {}
    files = (
        supabase.table("files")
        .select("item_id, file_path, updated_at")
        .in_("item_id", list(id_by_num.values()))
        .eq("file_type", "PDF")
        .not_.is_("file_path", "null")
        # updated_at, NOT created_at: files rows are updated in place on
        # same-filename re-upload, so created_at goes stale for them.
        # nullsfirst=False: a legacy NULL updated_at must not win "newest".
        .order("updated_at", desc=True, nullsfirst=False)
        .execute()
    )
    path_by_id: dict[str, str] = {}
    for row in files.data or []:
        path_by_id.setdefault(row["item_id"], row["file_path"])  # newest wins
    return {num: path_by_id[iid] for num, iid in id_by_num.items() if iid in path_by_id}


def _download_pdf(supabase, file_path: str) -> bytes | None:
    """Download a PDF given 'bucket/path/inside/bucket.pdf'."""
    try:
        parts = file_path.split("/", 1)
        if len(parts) != 2:
            logger.warning(f"Build book: unparseable file_path {file_path}")
            return None
        bucket, storage_path = parts
        signed = supabase.storage.from_(bucket).create_signed_url(storage_path, 300)
        url = signed.get("signedURL") or signed.get("signedUrl")
        if not url:
            logger.warning(f"Build book: no signed URL for {file_path}")
            return None
        with httpx.Client(timeout=30) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning(f"Build book: failed to download {file_path}: {e}")
        return None


# ============================================================================
# Drawing primitives
# ============================================================================

class Page:
    """Cursor-managed letter-portrait canvas with automatic page breaks."""

    def __init__(self):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=letter)
        self.y = PAGE_H - MARGIN
        self.footer_note = ""

    def need(self, height: float):
        if self.y - height < MARGIN + 14:
            self.new_page()

    def new_page(self):
        self._draw_footer()
        self.c.showPage()
        self.y = PAGE_H - MARGIN

    def _draw_footer(self):
        if self.footer_note:
            self.c.setFont("Helvetica", 6.5)
            self.c.setFillColor(INK)
            self.c.drawCentredString(PAGE_W / 2, 22, self.footer_note)

    def finish(self) -> PdfReader:
        self._draw_footer()
        self.c.save()
        self.buf.seek(0)
        return PdfReader(self.buf)


def _wrap(c, text: str, font: str, size: float, max_w: float) -> list[str]:
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _trunc(c, text: str, font: str, size: float, max_w: float) -> str:
    text = text or ""
    if c.stringWidth(text, font, size) <= max_w:
        return text
    while text and c.stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text + "…"


def _sec_title(p: Page, title: str, sub: str = ""):
    p.need(26)
    c = p.c
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGIN, p.y - 10, title)
    if sub:
        c.setFont("Helvetica", 6.5)
        c.drawRightString(PAGE_W - MARGIN, p.y - 10, sub)
    c.setLineWidth(1.5)
    c.setStrokeColor(INK)
    c.line(MARGIN, p.y - 14, PAGE_W - MARGIN, p.y - 14)
    p.y -= 22


def _checkbox(c, x: float, y: float, size: float = 8, done: bool = False):
    c.setLineWidth(1)
    c.setStrokeColor(INK)
    if done:
        c.setFillColor(INK)
        c.rect(x, y, size, size, fill=1, stroke=1)
    else:
        c.setFillColor(colors.white)
        c.rect(x, y, size, size, fill=1, stroke=1)


def _simple_table(p: Page, headers: list[tuple[str, float]], rows: list[list[str]],
                  row_h: float = 13, font_size: float = 7.5):
    """headers: [(label, width)]. Draws header + rows with page-break support."""
    c = p.c

    def draw_header():
        p.need(row_h + 4)
        x = MARGIN
        c.setFillColor(SHADE)
        c.rect(MARGIN, p.y - row_h, sum(w for _, w in headers), row_h, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 6.5)
        for label, w in headers:
            c.drawString(x + 3, p.y - row_h + 4, label)
            x += w
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(MARGIN, p.y - row_h, MARGIN + sum(w for _, w in headers), p.y - row_h)
        p.y -= row_h

    draw_header()
    for row in rows:
        if p.y - row_h < MARGIN + 14:
            p.new_page()
            draw_header()
        x = MARGIN
        c.setFont("Helvetica", font_size)
        c.setFillColor(INK)
        for (label, w), cell in zip(headers, row):
            c.drawString(x + 3, p.y - row_h + 4, _trunc(c, str(cell), "Helvetica", font_size, w - 6))
            x += w
        c.setStrokeColor(RULE_LT)
        c.setLineWidth(0.5)
        c.line(MARGIN, p.y - row_h, MARGIN + sum(w for _, w in headers), p.y - row_h)
        p.y -= row_h


# ============================================================================
# Sections
# ============================================================================

def _render_cover(p: Page, book: dict):
    c = p.c
    proj = book["project"]
    summ = book["summary"]

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN, p.y - 8, "MANUFACTURING BUILD BOOK")
    p.y -= 16
    title = proj["project_code"]
    if proj.get("description"):
        title += f" -- {proj['description'].upper()}"
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, p.y - 18, _trunc(c, title, "Helvetica-Bold", 20, PAGE_W - 2 * MARGIN))
    p.y -= 26
    gen = book.get("generatedAt", "")[:16].replace("T", " ")
    meta = (
        f"Customer {proj.get('customer') or '--'}   -   Start {str(book.get('startDate') or '--')[:10]}"
        f"   -   Ship {proj.get('due_date') or '--'}   -   Generated {gen}"
    )
    c.setFont("Helvetica", 8.5)
    c.drawString(MARGIN, p.y - 8, meta)
    p.y -= 18

    # governing note
    c.setLineWidth(1.25)
    c.setStrokeColor(INK)
    c.rect(MARGIN, p.y - 24, PAGE_W - 2 * MARGIN, 22, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(MARGIN + 6, p.y - 11, "WORK THE PACKAGES IN ORDER -- PKG NUMBERS GOVERN, PRINTED DAYS ARE THE PLAN.")
    c.drawString(MARGIN + 6, p.y - 20, "SOLID BOXES WERE ALREADY RECORDED COMPLETE IN THE SYSTEM WHEN THIS BOOK WAS GENERATED.")
    p.y -= 34

    # stat strip
    stats = [
        (str(summ["totalHours"]), "EST HOURS"),
        (str(summ["totalDays"]), "WORK DAYS"),
        (str(summ["packageCount"]), "PACKAGES"),
        (str(summ["fabParts"]), "FAB PARTS"),
        (str(summ["assemblies"]), "WELD/ASSY"),
        (str(summ["purchased"]), "PURCHASED"),
    ]
    box_w = (PAGE_W - 2 * MARGIN - 5 * 6) / 6
    x = MARGIN
    for val, label in stats:
        c.setLineWidth(1.25)
        c.rect(x, p.y - 34, box_w, 32, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(x + box_w / 2, p.y - 18, val)
        c.setFont("Helvetica-Bold", 5.5)
        c.drawCentredString(x + box_w / 2, p.y - 29, label)
        x += box_w + 6
    p.y -= 46

    _sec_title(p, "MILESTONES", "PLAN FROM SCHEDULE - WRITE ACTUAL")
    _simple_table(
        p,
        [("OP", 30), ("MILESTONE", 300), ("PLAN", 70), ("ACTUAL", 70), ("INIT", 62)],
        [[m["op"], m["title"], m.get("plan") or "--", m.get("actual") or "", ""] for m in book["milestones"]],
    )
    p.y -= 8

    docs = book.get("referenceDocs") or []
    if docs:
        _sec_title(p, "REFERENCE PRINTS -- READ FIRST", "BOUND BEHIND THIS PAGE")
        _simple_table(
            p,
            [("DOC #", 90), ("TITLE", 300), ("REV", 60), ("PDF", 82)],
            [[d["item_number"], d["name"], d.get("revision") or "--", "YES" if d.get("hasPrint") else "--"] for d in docs],
        )
        p.y -= 8

    _sec_title(p, "HOURS BY AREA")
    _simple_table(
        p,
        [("AREA", 200), ("EST HOURS", 100)],
        [[g["group"], g["hours"]] for g in summ.get("byGroup", [])],
    )
    p.y -= 8

    stock = book.get("stock") or []
    if stock:
        _sec_title(p, "STOCK PULL SUMMARY")
        _simple_table(
            p,
            [("RAW MATERIAL", 330), ("TOTAL QTY", 100), ("PARTS", 102)],
            [[s["description"], s["qty"], s["parts"]] for s in stock],
        )


def _render_calendar(p: Page, book: dict):
    cal = book.get("calendar") or {}
    stations = cal.get("stations") or []
    days = cal.get("days") or []
    if not stations or not days:
        return
    p.new_page()
    _sec_title(p, "DAY-BY-DAY STATION LOADING", "HOURS PER STATION - #N = PACKAGE")
    day_w = 86
    col_w = min(46, (PAGE_W - 2 * MARGIN - day_w) / max(1, len(stations)))
    headers = [("DAY", day_w)] + [(s["abbrev"], col_w) for s in stations]
    rows = []
    for d in days:
        row = [f"D{d['day'] + 1} - {d['date']}"]
        for cell in d["cells"]:
            if cell:
                txt = f"{cell['hours']}h"
                if cell.get("pkgs"):
                    txt += " " + " ".join(pk.replace("PKG ", "#") for pk in cell["pkgs"])
                row.append(txt)
            else:
                row.append("")
        rows.append(row)
    _simple_table(p, headers, rows, row_h=12, font_size=6.5)


def _render_packages(p: Page, book: dict):
    c = p.c
    p.new_page()
    _sec_title(p, "PART I -- WORK PACKAGES", "WORK IN ORDER - CHECK OFF LINES - SIGN EACH PACKAGE")

    for pkg in book.get("packages", []):
        lines = pkg.get("lines", [])
        stock = pkg.get("stockPull", [])
        est_h = round(pkg.get("estMin", 0) / 60, 1)
        card_h = 18 + (12 * len(stock) if stock else 0) + 12 + 11 * len(lines) + 16
        p.need(min(card_h, 300))

        top = p.y
        # header band
        c.setFillColor(SHADE_MD if pkg.get("done") else INK)
        c.rect(MARGIN, top - 15, PAGE_W - 2 * MARGIN, 15, fill=1, stroke=0)
        c.setFillColor(INK if pkg.get("done") else colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        hdr = f"{pkg['id']}   {pkg['stationName'].upper()}"
        c.drawString(MARGIN + 5, top - 11, hdr)
        meta = f"DAY {pkg['day'] + 1}"
        if pkg.get("date"):
            meta += f" - {pkg['date']}"
        meta += f" - EST {est_h} H"
        if pkg.get("done"):
            meta += "   * RECORDED COMPLETE"
        c.setFont("Helvetica-Bold", 7)
        c.drawRightString(PAGE_W - MARGIN - 5, top - 11, meta)
        p.y -= 15

        if stock:
            c.setFillColor(SHADE)
            c.rect(MARGIN, p.y - 12, PAGE_W - 2 * MARGIN, 12, fill=1, stroke=0)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 6.5)
            pull = " - ".join(f"{s['qty']} -- {s['description']} ({s['parts']}p)" for s in stock)
            c.drawString(MARGIN + 5, p.y - 9, _trunc(c, "PULL STOCK:  " + pull, "Helvetica-Bold", 6.5, PAGE_W - 2 * MARGIN - 10))
            p.y -= 12

        # line rows
        c.setFont("Helvetica-Bold", 6)
        c.setFillColor(INK)
        y0 = p.y
        cols = [(16, ""), (78, "PART #"), (190, "DESCRIPTION"), (28, "QTY"), (34, "MIN"), (56, "NEXT ->"), (130, "FOR KIT")]
        x = MARGIN
        for w, label in cols:
            if label:
                c.drawString(x + 3, y0 - 8, label)
            x += w
        p.y -= 10
        for ln in lines:
            if p.y - 11 < MARGIN + 14:
                p.new_page()
            x = MARGIN
            _checkbox(c, x + 4, p.y - 9, 8, bool(ln.get("done")))
            x += 16
            c.setFont("Helvetica-Bold", 7)
            c.drawString(x + 3, p.y - 9, _trunc(c, ln.get("displayNumber") or ln["item_number"], "Helvetica-Bold", 7, 72))
            x += 78
            c.setFont("Helvetica", 7)
            c.drawString(x + 3, p.y - 9, _trunc(c, ln.get("name", ""), "Helvetica", 7, 184))
            x += 190
            c.setFont("Helvetica-Bold", 7)
            c.drawString(x + 3, p.y - 9, str(ln["qty"]))
            x += 28
            c.setFont("Helvetica", 7)
            c.drawString(x + 3, p.y - 9, str(ln.get("estMin", "")))
            x += 34
            c.drawString(x + 3, p.y - 9, ln.get("next") or "-- last")
            x += 56
            c.drawString(x + 3, p.y - 9, _trunc(c, ", ".join(ln.get("feeds", [])), "Helvetica", 7, 124))
            c.setStrokeColor(RULE_LT)
            c.setLineWidth(0.5)
            c.line(MARGIN, p.y - 11, PAGE_W - MARGIN, p.y - 11)
            p.y -= 11

        # footer
        c.setFont("Helvetica-Bold", 6.5)
        stage = ", ".join(pkg.get("stageFor", []))
        if stage:
            c.drawString(MARGIN + 5, p.y - 10, f"STAGE KITS: {stage}")
        c.drawRightString(PAGE_W - MARGIN - 5, p.y - 10, "COMPLETED BY ______________  DATE ____ / ____")
        c.setStrokeColor(INK)
        c.setLineWidth(1)
        c.rect(MARGIN, p.y - 14, PAGE_W - 2 * MARGIN, (top - (p.y - 14)), fill=0, stroke=1)
        p.y -= 22


def _render_kit_sheet(p: Page, kit: dict):
    c = p.c
    p.new_page()
    top = p.y
    c.setFillColor(INK)
    c.rect(MARGIN, top - 18, PAGE_W - 2 * MARGIN, 18, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    title = f"{kit['rid']}   {kit['name']} -- {kit['item_number']}"
    if kit.get("qty", 1) > 1:
        title += f"  (×{kit['qty']})"
    c.drawString(MARGIN + 6, top - 13, _trunc(c, title, "Helvetica-Bold", 10, 380))
    meta = ""
    if kit.get("startDay") is not None:
        meta += f"PLAN D{kit['startDay'] + 1}–D{(kit.get('endDay') or kit['startDay']) + 1} - "
    meta += f"EST {round(kit.get('estMin', 0) / 60, 1)} H"
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(PAGE_W - MARGIN - 6, top - 13, meta)
    p.y -= 24

    if kit.get("childAsms"):
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7)
        subs = " - ".join(f"{a['rid']} {a['name']}" for a in kit["childAsms"])
        c.drawString(MARGIN, p.y - 8, _trunc(c, "REQUIRES SUB-ASSEMBLIES:  " + subs, "Helvetica-Bold", 7, PAGE_W - 2 * MARGIN))
        p.y -= 14

    parts = kit.get("parts", [])
    if parts:
        _sec_title(p, "KIT -- PARTS REQUIRED")
        rows = []
        for pt in parts:
            ready = f"{pt['readyBy']} - D{(pt.get('readyDay') or 0) + 1}" if pt.get("readyBy") else "--"
            rows.append(["", pt["rid"], pt["item_number"], pt["name"], pt["qty"], ready, "YES" if pt.get("done") else ""])
        _simple_table(
            p,
            [("", 16), ("ID", 34), ("PART #", 80), ("DESCRIPTION", 220), ("QTY", 32), ("READY BY", 90), ("DONE", 60)],
            rows,
        )
        p.y -= 8

    _sec_title(p, "SEQUENCE")
    for i, step in enumerate(kit.get("weldSeq", [])):
        p.need(14)
        _checkbox(c, MARGIN + 4, p.y - 10, 8, bool(step.get("done")))
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(MARGIN + 20, p.y - 10, f"{(i + 1) * 10} -- {step['station']}")
        c.setFont("Helvetica", 8)
        c.drawRightString(PAGE_W - MARGIN - 4, p.y - 10, f"{step.get('estMin', '')} min")
        p.y -= 14
        if step.get("notes"):
            for line in _wrap(c, step["notes"], "Helvetica", 7.5, PAGE_W - 2 * MARGIN - 60):
                p.need(11)
                c.setLineWidth(2)
                c.setStrokeColor(INK)
                c.line(MARGIN + 24, p.y - 9, MARGIN + 24, p.y + 1)
                c.setFont("Helvetica", 7.5)
                c.drawString(MARGIN + 30, p.y - 7, line)
                p.y -= 11
            p.y -= 3

    p.y -= 6
    p.need(20)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(MARGIN, p.y - 9, "INSPECT: welds complete - cleanup - dimensions per print")
    c.drawRightString(PAGE_W - MARGIN, p.y - 9, "INSPECTED BY ______________  DATE ____ / ____")
    p.y -= 16

    prints_n = kit.get("partPrints", 0)
    c.setFont("Helvetica-Bold", 7)
    note = f"PRINTS FOLLOW: assembly {'YES' if kit.get('hasPrint') else '--'} - parts {prints_n}/{len(parts)}"
    c.drawString(MARGIN, p.y - 9, note + "  (each print bound once, at first use)")
    p.y -= 14


# ============================================================================
# Main
# ============================================================================

def generate_build_book(project_id: str, book: dict) -> dict:
    supabase = get_supabase_admin()

    proj = supabase.table("mrp_projects").select("id, project_code").eq("id", project_id).single().execute()
    if not proj.data:
        raise ValueError(f"Project {project_id} not found")
    project_code = proj.data["project_code"]

    # collect item numbers whose prints we bind
    doc_nums = [d["item_number"] for d in book.get("referenceDocs", [])]
    kit_nums: list[str] = []
    for kit in book.get("kits", []):
        kit_nums.append(kit["item_number"])
        kit_nums.extend(pt["item_number"] for pt in kit.get("parts", []))
    pdf_paths = _fetch_pdf_paths(supabase, list(dict.fromkeys(doc_nums + kit_nums)))
    logger.info(f"Build book {project_code}: {len(pdf_paths)} prints resolvable")

    # prefetch all prints in parallel -- sequential downloads of 60+ PDFs take minutes
    pdf_cache: dict[str, bytes] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_download_pdf, supabase, path): num for num, path in pdf_paths.items()}
        for fut in concurrent.futures.as_completed(futures):
            data = fut.result()
            if data:
                pdf_cache[futures[fut]] = data
    logger.info(f"Build book {project_code}: {len(pdf_cache)} prints downloaded")

    writer = PdfWriter()
    prints_bound = 0
    footer = f"BUILD BOOK - {project_code} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    def append_reader(reader: PdfReader):
        for page in reader.pages:
            writer.add_page(page)

    def append_print(item_number: str) -> bool:
        nonlocal prints_bound
        data = pdf_cache.get(item_number)
        if not data:
            return False
        try:
            append_reader(PdfReader(io.BytesIO(data)))
            prints_bound += 1
            return True
        except Exception as e:
            logger.warning(f"Build book: bad PDF for {item_number}: {e}")
            return False

    # 1. cover
    p = Page()
    p.footer_note = footer
    _render_cover(p, book)
    append_reader(p.finish())

    # 2. reference docs bound behind the cover
    bound: set[str] = set()
    for num in doc_nums:
        if num not in bound and append_print(num):
            bound.add(num)

    # 3. calendar + 4. packages
    p = Page()
    p.footer_note = footer
    _render_calendar(p, book)
    _render_packages(p, book)
    append_reader(p.finish())

    # 5. kit chapters, each followed by its prints (first-use dedup)
    for kit in book.get("kits", []):
        p = Page()
        p.footer_note = footer
        _render_kit_sheet(p, kit)
        append_reader(p.finish())
        if kit["item_number"] not in bound and append_print(kit["item_number"]):
            bound.add(kit["item_number"])
        for pt in kit.get("parts", []):
            if pt["item_number"] not in bound and append_print(pt["item_number"]):
                bound.add(pt["item_number"])

    # assemble; the PDF streams back to the caller. Storage is best-effort only --
    # a book with all prints bound can exceed the project-wide upload size limit.
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    pdf_bytes = out.read()

    storage_path = f"{project_code}/{project_code}_build_book.pdf"
    stored = False
    # Supabase project upload limit is ~50MB; attempting an oversized upload wastes
    # minutes pushing bytes that get rejected with 413. Skip early instead.
    max_store = 45 * 1024 * 1024
    if len(pdf_bytes) <= max_store:
        try:
            try:
                supabase.storage.from_("print-packets").remove([storage_path])
            except Exception:
                pass
            supabase.storage.from_("print-packets").upload(
                storage_path, pdf_bytes, file_options={"content-type": "application/pdf"}
            )
            stored = True
        except Exception as e:
            logger.warning(f"Build book {project_code}: not stored ({len(pdf_bytes) // 1048576} MB): {e}")
    else:
        logger.info(
            f"Build book {project_code}: {len(pdf_bytes) // 1048576} MB exceeds storage limit -- streaming only"
        )

    return {
        "pdf": pdf_bytes,
        "project_code": project_code,
        "pages": len(writer.pages),
        "prints_bound": prints_bound,
        "stored_path": storage_path if stored else None,
    }


# ============================================================================
# Section print sets -- small on-demand bundles instead of the full bound book
# ============================================================================

def _fmt_qty(qty) -> str:
    if qty is None:
        return ""
    return str(int(qty)) if float(qty) == int(qty) else str(qty)


def _stamp_qty(page, qty, label: str):
    """White-backed QTY box in the top-right margin of a print page."""
    try:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        bw, bh = 108, 36
        x, y = w - bw - 14, h - bh - 12
        c.setFillColor(colors.white)
        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        c.rect(x, y, bw, bh, fill=1, stroke=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(x + bw / 2, y + bh - 17, f"QTY {_fmt_qty(qty)}")
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(x + bw / 2, y + 5, label[:34].upper())
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    except Exception as e:
        logger.warning(f"Section prints: qty stamp failed: {e}")


def generate_section_prints(project_id: str, label: str, items: list[dict]) -> dict:
    """Combined PDF of one book section's prints, each stamped with its quantity.

    items: [{item_number, qty (or null for reference docs)}] in book order.
    """
    supabase = get_supabase_admin()

    proj = supabase.table("mrp_projects").select("id, project_code").eq("id", project_id).single().execute()
    if not proj.data:
        raise ValueError(f"Project {project_id} not found")
    project_code = proj.data["project_code"]

    # dedupe by item_number, summing quantities, keeping first-seen order
    ordered: list[dict] = []
    by_num: dict[str, dict] = {}
    for it in items:
        num = it.get("item_number")
        if not num:
            continue
        if num in by_num:
            if it.get("qty") is not None:
                by_num[num]["qty"] = (by_num[num].get("qty") or 0) + it["qty"]
        else:
            entry = {"item_number": num, "qty": it.get("qty")}
            by_num[num] = entry
            ordered.append(entry)

    nums = [it["item_number"] for it in ordered]
    pdf_paths = _fetch_pdf_paths(supabase, nums)
    pdf_cache: dict[str, bytes] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_download_pdf, supabase, path): num for num, path in pdf_paths.items()}
        for fut in concurrent.futures.as_completed(futures):
            data = fut.result()
            if data:
                pdf_cache[futures[fut]] = data

    missing = [it["item_number"] for it in ordered if it["item_number"] not in pdf_cache]

    # cover page: what this set is, what's in it, what has no print on file
    p = Page()
    p.footer_note = f"PRINT SET - {project_code} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    c = p.c
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN, p.y - 8, "PRINT SET")
    p.y -= 16
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, p.y - 16, _trunc(c, f"{project_code} -- {label}", "Helvetica-Bold", 18, PAGE_W - 2 * MARGIN))
    p.y -= 24
    c.setFont("Helvetica", 8.5)
    c.drawString(MARGIN, p.y - 8, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} - qty stamped top-right of each print")
    p.y -= 20
    _simple_table(
        p,
        [("PART #", 120), ("QTY", 50), ("PRINT", 60)],
        [[it["item_number"], _fmt_qty(it["qty"]), "YES" if it["item_number"] in pdf_cache else "MISSING"] for it in ordered],
    )

    writer = PdfWriter()
    for page in p.finish().pages:
        writer.add_page(page)

    prints_bound = 0
    for it in ordered:
        data = pdf_cache.get(it["item_number"])
        if not data:
            continue
        try:
            reader = PdfReader(io.BytesIO(data))
            for i, page in enumerate(reader.pages):
                if i == 0 and it.get("qty") is not None:
                    _stamp_qty(page, it["qty"], f"{label} - {it['item_number']}")
                writer.add_page(page)
            prints_bound += 1
        except Exception as e:
            logger.warning(f"Section prints: bad PDF for {it['item_number']}: {e}")
            missing.append(it["item_number"])

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return {
        "pdf": out.read(),
        "project_code": project_code,
        "pages": len(writer.pages),
        "prints_bound": prints_bound,
        "missing": missing,
    }



