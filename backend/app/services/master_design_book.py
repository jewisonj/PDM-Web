"""Master Design Book service — rev-controlled section booklets.

Implements Documentation/36-MASTER-DESIGN-BOOK-PLAN.md sections 4-7:

  - Semantic content hashing (canonical JSON, never rendered PDF bytes)
  - Identity-keyed diff engine with section rev letters (A..Z, AA..)
  - Section renderers (spine / work package / kit / design ref / general ref)
    consuming the frontend descriptor payloads (masterDesignBook.ts), so a
    stored `source` can re-render headlessly
  - Update algorithm with write-ahead change records, archive-on-supersede,
    and ordering invariants replacing transactions (DB never leads storage;
    book_rev bump is the commit point; re-running update always converges)
  - Change notice PDFs (immutable, zero-padded), manifest.json export
  - Full merged book by byte-concatenation of the stored section PDFs

Rendering constraints (load-bearing):
  - ASCII only through reportlab Helvetica (WinAnsi): every dynamic string
    passes the _ascii() chokepoint (routing notes contain unicode dashes etc.)
  - Never reuse a parsed PdfReader page across bindings (stamps mutate pages)
  - PDF responses upstream must be plain Response, never StreamingResponse
"""

import concurrent.futures
import hashlib
import io
import json
import logging
import math
from datetime import datetime, timezone

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from .supabase import get_supabase_admin
from .build_book import _download_pdf

logger = logging.getLogger(__name__)

BUCKET = "design-books"
HASH_SCHEMA = 1
# storage guard: bucket/file cap is 50MB; leave headroom like build_book.py
MAX_STORE_BYTES = 45 * 1024 * 1024

PAGE_W, PAGE_H = letter  # 612 x 792 portrait
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN  # 532
INK = colors.HexColor("#16181a")
RULE = colors.HexColor("#9aa0a5")
RULE_LT = colors.HexColor("#c9cdd1")
SHADE = colors.HexColor("#f1f2f3")
SHADE_MD = colors.HexColor("#e4e6e8")


class BookNotFound(Exception):
    """Unknown book_code (route maps to 404)."""


class BookConflict(Exception):
    """expected_book_rev mismatch — concurrent update (route maps to 409)."""


class QtyGateError(Exception):
    """Flat-vs-BOM-rollup quantity mismatches without allow_qty_mismatch (400)."""

    def __init__(self, mismatches: list[dict]):
        self.mismatches = mismatches
        super().__init__(f"{len(mismatches)} quantity mismatch(es)")


# ============================================================================
# ASCII chokepoint — WinAnsi Helvetica cannot render arbitrary unicode
# ============================================================================

_ASCII_MAP = {
    "—": "--", "–": "-", "▸": ">", "×": "x", "…": "...",
    "°": " deg", "±": "+/-", "Ø": "dia ", "∅": "dia ",
    "‘": "'", "’": "'", "“": '"', "”": '"', "→": "->",
    "·": "-", "•": "-", "½": "1/2", "¼": "1/4", "¾": "3/4",
}


def _ascii(text) -> str:
    """Transliterate/strip any string to WinAnsi-safe ASCII."""
    if text is None:
        return ""
    out = []
    for ch in str(text):
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append(_ASCII_MAP.get(ch, ""))
    return "".join(out)


def dayLabel(day) -> str:
    """0-indexed schedule day -> 'D1'.. (mirrors buildBook.ts dayLabel)."""
    return f"D{int(day) + 1}"


# ============================================================================
# Revision letters — A..Z, AA, AB.. (Excel column style)
# ============================================================================

def _rev_to_int(rev: str) -> int:
    n = 0
    for ch in rev.strip().upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def _int_to_rev(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def next_rev(rev: str | None) -> str:
    if not rev:
        return "A"
    return _int_to_rev(_rev_to_int(rev) + 1)


# ============================================================================
# Canonical hashing — semantic inputs, never rendered bytes
# ============================================================================

# completion-state keys are stripped defensively even though the frontend
# master engine already blanks them (Documentation/36 4.1)
_EXCLUDED_KEYS = {"done", "rowDone", "ordDone", "rcvDone", "rcvPartial"}


def _clean(obj):
    """Recursively strip excluded keys and normalize whole floats to ints."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if k not in _EXCLUDED_KEYS}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj


def canonical_json(obj) -> str:
    return json.dumps(_clean(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_hash(hash_input: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(hash_input).encode("utf-8")).hexdigest()


def build_hash_input(descriptor: dict, prints: list[dict], renderer_version: int) -> dict:
    """The full semantic hash input — also stored as design_book_sections.source."""
    return {
        "hash_schema": HASH_SCHEMA,
        "renderer_version": renderer_version,
        "kind": descriptor["kind"],
        "section_code": descriptor["section_code"],
        "title": descriptor.get("title") or "",
        "identity": descriptor.get("identity") or {},
        "display": descriptor.get("display"),
        "payload": descriptor.get("payload") or {},
        "prints": prints,
    }


def _identity_key(identity: dict) -> str:
    return canonical_json(identity or {})


# ============================================================================
# Print resolution — newest PDF per item, staleness tuple (file_id, rev, iter)
# ============================================================================

def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _fetch_print_files(supabase, item_numbers: list[str]) -> dict[str, dict]:
    """item_number -> newest PDF file row {file_id, file_path, revision, iteration}.

    Ordered by updated_at (NOT created_at): files rows are UPDATED IN PLACE on
    same-filename re-upload (files.py), so created_at is stale for them.
    Queries are chunked so no request can silently hit PostgREST's 1000-row
    default cap (review finding m6); nullsfirst=False guards legacy rows with
    NULL updated_at from winning "newest" under desc ordering.
    """
    if not item_numbers:
        return {}
    id_by_num: dict[str, str] = {}
    for chunk in _chunks(item_numbers, 100):
        items = (
            supabase.table("items")
            .select("id, item_number")
            .in_("item_number", chunk)
            .execute()
        )
        for r in items.data or []:
            id_by_num[r["item_number"]] = r["id"]
    if not id_by_num:
        return {}
    row_by_item: dict[str, dict] = {}
    for chunk in _chunks(list(id_by_num.values()), 40):
        files = (
            supabase.table("files")
            .select("id, item_id, file_path, revision, iteration, updated_at")
            .in_("item_id", chunk)
            .eq("file_type", "PDF")
            .not_.is_("file_path", "null")
            .order("updated_at", desc=True, nullsfirst=False)
            .execute()
        )
        for row in files.data or []:
            row_by_item.setdefault(row["item_id"], row)  # newest wins
    out = {}
    for num, iid in id_by_num.items():
        row = row_by_item.get(iid)
        if row:
            out[num] = {
                "file_id": row["id"],
                "file_path": row["file_path"],
                "revision": row.get("revision"),
                "iteration": row.get("iteration"),
            }
    return out


def resolve_prints(descriptor: dict, file_by_num: dict[str, dict]) -> list[dict]:
    """Ordered print bind list for a descriptor (bind order = page order)."""
    prints = []
    for it in descriptor.get("print_items") or []:
        num = it["item_number"]
        f = file_by_num.get(num)
        if f:
            prints.append({"item_number": num, "qty": it.get("qty"), **f})
        else:
            prints.append({"item_number": num, "qty": it.get("qty"), "missing": True})
    return prints


# ============================================================================
# Diff engine
# ============================================================================

def _diff_parts_clause(old_rows: list[dict], new_rows: list[dict]) -> str | None:
    """Compare item lists (lines / kit parts) by item_number: +x / -y / QTY z a->b.

    Reason clauses print on the shop-distributed change notice, so they use
    displayNumber — raw mmc/spn numbers never reach paper (review finding m1).
    """
    old = {r.get("item_number"): r for r in old_rows or []}
    new = {r.get("item_number"): r for r in new_rows or []}

    def disp(num):
        row = new.get(num) or old.get(num) or {}
        return row.get("displayNumber") or num

    bits = []
    for num in new:
        if num not in old:
            bits.append(f"+{disp(num)}")
        elif old[num].get("qty") != new[num].get("qty"):
            bits.append(f"QTY {disp(num)} {old[num].get('qty')}->{new[num].get('qty')}")
    for num in old:
        if num not in new:
            bits.append(f"-{disp(num)}")
    if not bits:
        return None
    if len(bits) > 3:
        bits = bits[:3] + [f"+{len(bits) - 3} MORE"]
    return "PARTS: " + ", ".join(bits)


def derive_reasons(old_source: dict | None, new_input: dict, renamed_from: str | None = None) -> list[str]:
    """Mechanical reason derivation from structured hash-input diff (spec 4.4)."""
    reasons: list[str] = []
    if renamed_from:
        reasons.append(f"RENAMED FROM {renamed_from}")
    if old_source is None:
        return reasons + ["NEW"]

    if old_source.get("renderer_version") != new_input.get("renderer_version"):
        return reasons + [
            f"LAYOUT UPDATE (renderer v{old_source.get('renderer_version')}->v{new_input.get('renderer_version')})"
        ]

    # prints diff by item_number
    old_p = {p["item_number"]: p for p in old_source.get("prints") or []}
    new_p = {p["item_number"]: p for p in new_input.get("prints") or []}
    for num, np in new_p.items():
        op = old_p.get(num)
        if op is None:
            reasons.append(f"PRINT BOUND {num}")
        elif op.get("missing") and not np.get("missing"):
            reasons.append(f"PRINT ADDED {num}")
        elif not op.get("missing") and np.get("missing"):
            reasons.append(f"PRINT NOW MISSING {num}")
        elif (op.get("file_id"), op.get("revision"), op.get("iteration")) != (
            np.get("file_id"), np.get("revision"), np.get("iteration")
        ):
            if op.get("revision") != np.get("revision"):
                reasons.append(f"PRINT {num} {op.get('revision') or '?'}->{np.get('revision') or '?'}")
            else:
                reasons.append(f"PRINT {num} UPDATED")
        elif op.get("qty") != np.get("qty"):
            reasons.append(f"QTY {num} {op.get('qty')}->{np.get('qty')}")
    for num in old_p:
        if num not in new_p:
            reasons.append(f"PRINT DROPPED {num}")

    # display diff (moves / resequencing)
    od = old_source.get("display") or {}
    nd = new_input.get("display") or {}
    if od.get("day") is not None and nd.get("day") is not None and od.get("day") != nd.get("day"):
        reasons.append(f"MOVED {dayLabel(od['day'])}->{dayLabel(nd['day'])}")
    if (od.get("startDay"), od.get("endDay")) != (nd.get("startDay"), nd.get("endDay")):
        if nd.get("startDay") is not None and od.get("startDay") is not None:
            reasons.append(
                f"MOVED PLAN {dayLabel(od.get('startDay'))}-{dayLabel(od.get('endDay') or od.get('startDay'))}"
                f"->{dayLabel(nd.get('startDay'))}-{dayLabel(nd.get('endDay') or nd.get('startDay'))}"
            )
    if od.get("pkg_position") is not None and od.get("pkg_position") != nd.get("pkg_position"):
        reasons.append(f"RESEQUENCED PKG {od['pkg_position']}->{nd['pkg_position']}")

    # payload diff, kind-aware
    op_, np_ = old_source.get("payload") or {}, new_input.get("payload") or {}
    kind = new_input.get("kind")
    if canonical_json(op_) != canonical_json(np_):
        if kind == "work_package":
            clause = _diff_parts_clause(op_.get("lines"), np_.get("lines"))
            if clause:
                reasons.append(clause)
            if canonical_json(op_.get("stockPull") or []) != canonical_json(np_.get("stockPull") or []):
                reasons.append("STOCK PULL REVISED")
        elif kind == "assembly":
            clause = _diff_parts_clause(op_.get("parts"), np_.get("parts"))
            if clause:
                reasons.append(clause)
            old_seq, new_seq = op_.get("weldSeq") or [], np_.get("weldSeq") or []
            if [s.get("station") for s in old_seq] != [s.get("station") for s in new_seq]:
                reasons.append("SEQUENCE REVISED")
            elif [s.get("notes") for s in old_seq] != [s.get("notes") for s in new_seq]:
                reasons.append("NOTES REVISED")
        elif kind == "spine":
            reasons.append("TOC/CHECKLIST UPDATED")
        if not reasons:
            reasons.append("TABLE DATA REVISED")

    if not reasons:
        reasons.append("REVISED")
    if len(reasons) > 3:
        reasons = reasons[:3] + [f"+{len(reasons) - 3} MORE"]
    return reasons


def classify_sections(existing_rows: list[dict], incoming: list[dict], rebaseline: bool = False) -> dict:
    """Match incoming {descriptor, hash_input, content_hash} against DB rows by identity.

    Returns {added, changed, unchanged, retired} — each entry carries the row
    (if any), descriptor, hash bits, assigned rev, and derived reasons.
    """
    current_by_id = {}
    retired_by_id = {}
    for row in existing_rows:
        key = _identity_key(row.get("identity") or {})
        if row.get("status") == "current":
            current_by_id[key] = row
        elif row.get("status") == "retired":
            retired_by_id.setdefault(key, row)

    added, changed, unchanged, retired = [], [], [], []
    seen_keys = set()

    for inc in incoming:
        d = inc["descriptor"]
        key = _identity_key(d.get("identity") or {})
        seen_keys.add(key)
        row = current_by_id.get(key)
        if row:
            same_hash = row.get("content_hash") == inc["content_hash"]
            same_code = row.get("section_code") == d["section_code"]
            if same_hash and same_code and not rebaseline:
                unchanged.append({**inc, "row": row, "rev": row["rev"]})
            elif same_hash and same_code and rebaseline:
                # byte refresh only: re-render/upload, keep letter, no notice entry
                unchanged.append({**inc, "row": row, "rev": row["rev"], "refresh": True})
            else:
                renamed_from = None if same_code else row.get("section_code")
                reasons = derive_reasons(row.get("source"), inc["hash_input"], renamed_from)
                changed.append({
                    **inc, "row": row, "old_rev": row["rev"],
                    "rev": next_rev(row["rev"]), "reasons": reasons,
                })
        else:
            old = retired_by_id.get(key)
            if old:
                added.append({
                    **inc, "row": old, "rev": next_rev(old["rev"]),
                    "reasons": ["REINSTATED"], "reinstated": True,
                })
            else:
                added.append({**inc, "row": None, "rev": "A", "reasons": ["NEW"]})

    for key, row in current_by_id.items():
        if key not in seen_keys:
            retired.append({"row": row, "descriptor": None, "rev": row["rev"], "reasons": ["RETIRED"]})

    return {"added": added, "changed": changed, "unchanged": unchanged, "retired": retired}


# ============================================================================
# Rendering primitives
# ============================================================================

class _Body:
    """Cursor-managed letter-portrait canvas; footers are stamped later."""

    def __init__(self):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=letter)
        self.y = PAGE_H - MARGIN

    def need(self, height: float):
        if self.y - height < MARGIN + 18:  # keep clear of the footer strip
            self.c.showPage()
            self.y = PAGE_H - MARGIN

    def finish(self) -> PdfReader:
        self.c.save()
        self.buf.seek(0)
        return PdfReader(self.buf)


def _trunc(c, text, font: str, size: float, max_w: float) -> str:
    text = _ascii(text)
    if c.stringWidth(text, font, size) <= max_w:
        return text
    while text and c.stringWidth(text + "...", font, size) > max_w:
        text = text[:-1]
    return text + "..."


def _wrap_ascii(c, text, font: str, size: float, max_w: float) -> list[str]:
    words = _ascii(text).split()
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


def _checkbox(c, x: float, y: float, size: float = 8):
    c.setLineWidth(1)
    c.setStrokeColor(INK)
    c.setFillColor(colors.white)
    c.rect(x, y, size, size, fill=1, stroke=1)


def _sec_title(b: _Body, title: str, sub: str = ""):
    b.need(26)
    c = b.c
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGIN, b.y - 10, _ascii(title))
    if sub:
        c.setFont("Helvetica", 6.5)
        c.drawRightString(PAGE_W - MARGIN, b.y - 10, _ascii(sub))
    c.setLineWidth(1.5)
    c.setStrokeColor(INK)
    c.line(MARGIN, b.y - 14, PAGE_W - MARGIN, b.y - 14)
    b.y -= 22


def _header_band(b: _Body, left: str, right: str):
    c = b.c
    c.setFillColor(INK)
    c.rect(MARGIN, b.y - 18, CONTENT_W, 18, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN + 6, b.y - 13, _trunc(c, left, "Helvetica-Bold", 10, 350))
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(PAGE_W - MARGIN - 6, b.y - 13, _ascii(right))
    b.y -= 24


def _band(b: _Body, text: str, fill=SHADE_MD, bold_size: float = 7):
    c = b.c
    b.need(14)
    c.setFillColor(fill)
    c.rect(MARGIN, b.y - 12, CONTENT_W, 12, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", bold_size)
    c.drawString(MARGIN + 5, b.y - 9, _trunc(c, text, "Helvetica-Bold", bold_size, CONTENT_W - 10))
    b.y -= 14


def _table(b: _Body, headers: list[tuple[str, float]], rows: list[list], row_h: float = 13, font_size: float = 7.5):
    """Shaded-header table with page-break header redraw (build_book style, ASCII)."""
    c = b.c
    total_w = sum(w for _, w in headers)

    def draw_header():
        b.need(row_h + 4)
        x = MARGIN
        c.setFillColor(SHADE)
        c.rect(MARGIN, b.y - row_h, total_w, row_h, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 6.5)
        for label, w in headers:
            c.drawString(x + 3, b.y - row_h + 4, label)
            x += w
        c.setStrokeColor(RULE)
        c.setLineWidth(0.75)
        c.line(MARGIN, b.y - row_h, MARGIN + total_w, b.y - row_h)
        b.y -= row_h

    draw_header()
    for row in rows:
        if b.y - row_h < MARGIN + 18:
            b.c.showPage()
            b.y = PAGE_H - MARGIN
            draw_header()
        x = MARGIN
        c.setFont("Helvetica", font_size)
        c.setFillColor(INK)
        for (label, w), cell in zip(headers, row):
            c.drawString(x + 3, b.y - row_h + 4, _trunc(c, str(cell), "Helvetica", font_size, w - 6))
            x += w
        c.setStrokeColor(RULE_LT)
        c.setLineWidth(0.5)
        c.line(MARGIN, b.y - row_h, MARGIN + total_w, b.y - row_h)
        b.y -= row_h


def _stamp_qty(page, qty, label: str):
    """White-backed QTY box, top-right of a print page (mediabox + /Rotate aware)."""
    try:
        rot = (page.get("/Rotate") or 0) % 360
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.saveState()
        if rot == 90:
            c.translate(w, 0); c.rotate(90); ew, eh = h, w
        elif rot == 180:
            c.translate(w, h); c.rotate(180); ew, eh = w, h
        elif rot == 270:
            c.translate(0, h); c.rotate(270); ew, eh = h, w
        else:
            ew, eh = w, h
        bw, bh = 108, 36
        x, y = ew - bw - 14, eh - bh - 12
        c.setFillColor(colors.white)
        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        c.rect(x, y, bw, bh, fill=1, stroke=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 16)
        q = int(qty) if isinstance(qty, float) and qty.is_integer() else qty
        c.drawCentredString(x + bw / 2, y + bh - 17, f"QTY {q}")
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(x + bw / 2, y + 5, _ascii(label)[:34].upper())
        c.restoreState()
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    except Exception as e:
        logger.warning(f"Design book: qty stamp failed: {e}")


def _stamp_footer(page, left: str, center: str, right: str):
    """Swap-contract footer on every page — mediabox AND /Rotate aware."""
    try:
        rot = (page.get("/Rotate") or 0) % 360
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.saveState()
        if rot == 90:
            c.translate(w, 0); c.rotate(90); ew = h
        elif rot == 180:
            c.translate(w, h); c.rotate(180); ew = w
        elif rot == 270:
            c.translate(0, h); c.rotate(270); ew = h
        else:
            ew = w
        c.setFillColor(colors.white)
        c.rect(0, 0, ew, 15.5, fill=1, stroke=0)
        c.setStrokeColor(RULE_LT)
        c.setLineWidth(0.5)
        c.line(0, 16, ew, 16)
        c.setFillColor(INK)
        c.setFont("Helvetica", 6.5)
        c.drawString(18, 5, _ascii(left))
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(ew / 2, 5, _ascii(center))
        c.setFont("Helvetica", 6.5)
        c.drawRightString(ew - 18, 5, _ascii(right))
        c.restoreState()
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    except Exception as e:
        logger.warning(f"Design book: footer stamp failed: {e}")


def _bind_prints(writer: PdfWriter, prints: list[dict], pdf_cache: dict[str, bytes], stamp_prefix: str) -> int:
    """Append each resolved print (deduped by item_number, qtys summed).

    Fresh PdfReader per binding — stamps mutate page objects, so cached bytes
    are re-parsed for every binding rather than sharing readers.
    """
    ordered: list[dict] = []
    by_num: dict[str, dict] = {}
    for p in prints:
        if p.get("missing"):
            continue
        num = p["item_number"]
        if num in by_num:
            if p.get("qty") is not None:
                by_num[num]["qty"] = (by_num[num].get("qty") or 0) + p["qty"]
        else:
            entry = {"item_number": num, "qty": p.get("qty")}
            by_num[num] = entry
            ordered.append(entry)

    bound = 0
    for entry in ordered:
        data = pdf_cache.get(entry["item_number"])
        if not data:
            continue
        try:
            reader = PdfReader(io.BytesIO(data))
            for i, page in enumerate(reader.pages):
                if i == 0 and entry.get("qty") is not None:
                    _stamp_qty(page, entry["qty"], f"{stamp_prefix} - {entry['item_number']}")
                writer.add_page(page)
            bound += 1
        except Exception as e:
            logger.warning(f"Design book: bad PDF for {entry['item_number']}: {e}")
    return bound


def _finalize_section(writer: PdfWriter, book_code: str, book_rev: int, section_code: str,
                      rev: str, gen_date: str) -> tuple[bytes, int]:
    """Two-pass footer stamp (page count unknown until assembled), then bytes."""
    n = len(writer.pages)
    left = f"MDB {book_code.upper()}  REV {book_rev}"
    center = f"{section_code} REV {rev}"
    for i, page in enumerate(writer.pages):
        _stamp_footer(page, left, center, f"PAGE {i + 1} OF {n}  -  GEN {gen_date}")
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read(), n


# ============================================================================
# Section body renderers (consume descriptor payloads)
# ============================================================================

def _missing_nums(prints: list[dict]) -> list[str]:
    return [p["item_number"] for p in prints if p.get("missing")]


def _render_package_body(b: _Body, code: str, rev: str, d: dict, prints: list[dict]):
    payload = d.get("payload") or {}
    display = d.get("display") or {}
    est_h = round((payload.get("estMin") or 0) / 60, 1)
    day = display.get("day")
    right = f"{dayLabel(day)}  -  EST {est_h} H  -  REV {rev}" if day is not None else f"EST {est_h} H  -  REV {rev}"
    _header_band(b, f"{code}   {payload.get('stationName', '').upper()}", right)

    c = b.c
    c.setFillColor(INK)
    c.setFont("Helvetica", 6.5)
    c.drawString(MARGIN, b.y - 6, "WORK PACKAGE  -  MASTER DOCUMENT, BOXES BLANK  -  ORDER GOVERNED BY 00-SPINE CHECKLIST")
    b.y -= 14

    stock = payload.get("stockPull") or []
    if stock:
        pull = "  -  ".join(f"{s.get('qty')} -- {s.get('description')} ({s.get('parts')}p)" for s in stock)
        _band(b, "PULL STOCK:  " + pull, fill=SHADE, bold_size=6.5)

    cols = [("", 16), ("PART #", 78), ("DESCRIPTION", 190), ("QTY", 28), ("MIN", 34), ("NEXT ->", 56), ("FOR KIT", 130)]

    def pkg_cols_header():
        c.setFont("Helvetica-Bold", 6)
        c.setFillColor(INK)
        hx = MARGIN
        for label, w in cols:
            if label:
                c.drawString(hx + 3, b.y - 8, label)
            hx += w
        b.y -= 10

    card_top = b.y
    pkg_cols_header()
    for ln in payload.get("lines") or []:
        if b.y - 11 < MARGIN + 18:
            # close this page's card segment, restart headers on the next
            # (review finding m4 — overflow pages had unheadered, unboxed rows)
            c.setStrokeColor(INK)
            c.setLineWidth(1)
            c.rect(MARGIN, b.y - 2, CONTENT_W, card_top - (b.y - 2), fill=0, stroke=1)
            c.showPage()
            b.y = PAGE_H - MARGIN
            card_top = b.y
            pkg_cols_header()
        x = MARGIN
        _checkbox(c, x + 4, b.y - 9)
        x += 16
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x + 3, b.y - 9, _trunc(c, ln.get("displayNumber") or ln.get("item_number"), "Helvetica-Bold", 7, 72))
        x += 78
        c.setFont("Helvetica", 7)
        desc = ln.get("name") or ""
        if ln.get("source"):
            desc = f"{desc} -- {ln['source']}"
        c.drawString(x + 3, b.y - 9, _trunc(c, desc, "Helvetica", 7, 184))
        x += 190
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x + 3, b.y - 9, str(ln.get("qty", "")))
        x += 28
        c.setFont("Helvetica", 7)
        c.drawString(x + 3, b.y - 9, str(ln.get("estMin", "")))
        x += 34
        c.drawString(x + 3, b.y - 9, _ascii(ln.get("next") or "-- last"))
        x += 56
        c.drawString(x + 3, b.y - 9, _trunc(c, ", ".join(ln.get("feeds") or []), "Helvetica", 7, 124))
        c.setStrokeColor(RULE_LT)
        c.setLineWidth(0.5)
        c.line(MARGIN, b.y - 11, PAGE_W - MARGIN, b.y - 11)
        b.y -= 11

    c.setFont("Helvetica-Bold", 6.5)
    stage = ", ".join(payload.get("stageFor") or [])
    if stage:
        c.drawString(MARGIN + 5, b.y - 10, _trunc(c, f"STAGE KITS: {stage}", "Helvetica-Bold", 6.5, 300))
    c.drawRightString(PAGE_W - MARGIN - 5, b.y - 10, "COMPLETED BY ______________  DATE ____ / ____")
    c.setStrokeColor(INK)
    c.setLineWidth(1)
    c.rect(MARGIN, b.y - 14, CONTENT_W, card_top - (b.y - 14), fill=0, stroke=1)
    b.y -= 22

    missing = _missing_nums(prints)
    if missing:
        _band(b, f"MISSING PRINTS ({len(missing)}): " + ", ".join(missing) + " -- NO PDF ON FILE, REPORT TO ENGINEERING")
    n_prints = len({p["item_number"] for p in prints if not p.get("missing")})
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(MARGIN, b.y - 10, f"PRINTS FOLLOW ({n_prints}) -- QTY STAMPED TOP RIGHT -- QUANTITIES ARE PER ONE BUILD")
    b.y -= 14


def _render_kit_body(b: _Body, code: str, rev: str, d: dict, prints: list[dict]):
    payload = d.get("payload") or {}
    display = d.get("display") or {}
    qty = payload.get("qty") or 1
    qty_note = f"  (x{qty})" if qty and qty > 1 else ""
    est_h = round((payload.get("estMin") or 0) / 60, 1)
    plan = ""
    if display.get("startDay") is not None:
        plan = f"PLAN {dayLabel(display['startDay'])}-{dayLabel(display.get('endDay') or display['startDay'])}  -  "
    _header_band(
        b,
        f"{code}   {payload.get('name', '').upper()} -- {payload.get('item_number', '').upper()}{qty_note}",
        f"{plan}EST {est_h} H  -  REV {rev}",
    )

    c = b.c
    child_asms = payload.get("childAsms") or []
    if child_asms:
        subs = "  -  ".join(f"{a.get('code')} {a.get('name')}" for a in child_asms)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(MARGIN, b.y - 8, _trunc(c, "REQUIRES SUB-ASSEMBLIES:  " + subs, "Helvetica-Bold", 7, CONTENT_W))
        b.y -= 14

    parts = payload.get("parts") or []
    resolved = {p["item_number"]: p for p in prints}
    if parts:
        _sec_title(b, "KIT -- PARTS REQUIRED")
        cols = [("", 16), ("ID", 34), ("PART #", 80), ("DESCRIPTION", 210), ("QTY", 32), ("READY BY", 100), ("PRINT", 60)]

        def kit_cols_header():
            c.setFillColor(SHADE)
            c.rect(MARGIN, b.y - 13, CONTENT_W, 13, fill=1, stroke=0)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 6.5)
            hx = MARGIN
            for label, w in cols:
                if label:
                    c.drawString(hx + 3, b.y - 13 + 4, label)
                hx += w
            b.y -= 13

        kit_cols_header()
        for pt in parts:
            if b.y - 13 < MARGIN + 18:
                c.showPage()
                b.y = PAGE_H - MARGIN
                kit_cols_header()  # review finding m4
            x = MARGIN
            _checkbox(c, x + 4, b.y - 11)
            x += 16
            c.setFillColor(INK)
            c.setFont("Helvetica", 7.5)
            c.drawString(x + 3, b.y - 9, str(pt.get("rid", "")))
            x += 34
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(x + 3, b.y - 9, _trunc(c, pt.get("displayNumber") or pt.get("item_number"), "Helvetica-Bold", 7.5, 74))
            x += 80
            c.setFont("Helvetica", 7.5)
            desc = pt.get("name") or ""
            if pt.get("source"):
                desc = f"{desc} -- {pt['source']}"
            c.drawString(x + 3, b.y - 9, _trunc(c, desc, "Helvetica", 7.5, 204))
            x += 210
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(x + 3, b.y - 9, str(pt.get("qty", "")))
            x += 32
            c.setFont("Helvetica", 7.5)
            ready = pt.get("readyBy") or "--"
            if pt.get("readyBy") and pt.get("readyDay") is not None:
                ready = f"{pt['readyBy']} - {dayLabel(pt['readyDay'])}"
            c.drawString(x + 3, b.y - 9, _ascii(ready))
            x += 100
            r = resolved.get(pt.get("item_number"))
            print_cell = "--" if r is None else ("MISSING" if r.get("missing") else "YES")
            c.drawString(x + 3, b.y - 9, print_cell)
            c.setStrokeColor(RULE_LT)
            c.setLineWidth(0.5)
            c.line(MARGIN, b.y - 13, MARGIN + CONTENT_W, b.y - 13)
            b.y -= 13
        b.y -= 8

    _sec_title(b, "SEQUENCE")
    for i, step in enumerate(payload.get("weldSeq") or []):
        b.need(14)
        _checkbox(c, MARGIN + 4, b.y - 10)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8)
        dtag = f"  ({dayLabel(step['day'])})" if step.get("day") is not None else ""
        c.drawString(MARGIN + 20, b.y - 10, _ascii(f"{(i + 1) * 10} -- {step.get('station', '').upper()}{dtag}"))
        c.setFont("Helvetica", 8)
        c.drawRightString(PAGE_W - MARGIN - 4, b.y - 10, f"{step.get('estMin', '')} min")
        b.y -= 14
        if step.get("notes"):
            # method notes render fully wrapped, never truncated — EBOM/MBOM deltas live here
            for line in _wrap_ascii(c, step["notes"], "Helvetica", 7.5, CONTENT_W - 60):
                b.need(11)
                c.setLineWidth(2)
                c.setStrokeColor(INK)
                c.line(MARGIN + 24, b.y - 9, MARGIN + 24, b.y + 1)
                c.setFont("Helvetica", 7.5)
                c.setFillColor(INK)
                c.drawString(MARGIN + 30, b.y - 7, line)
                b.y -= 11
            b.y -= 3

    b.y -= 6
    b.need(20)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(INK)
    c.drawString(MARGIN, b.y - 9, "INSPECT: welds complete - cleanup - dimensions per print")
    c.drawRightString(PAGE_W - MARGIN, b.y - 9, "INSPECTED BY ______________  DATE ____ / ____")
    b.y -= 16

    missing = _missing_nums(prints)
    if missing:
        _band(b, f"MISSING PRINTS ({len(missing)}): " + ", ".join(missing) + " -- NO PDF ON FILE, REPORT TO ENGINEERING")
    n_prints = len({p["item_number"] for p in prints if not p.get("missing")})
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(MARGIN, b.y - 10, f"PRINTS FOLLOW ({n_prints}): ASSEMBLY PRINT FIRST, THEN PART PRINTS IN KIT ORDER -- QTY STAMPED")
    b.y -= 14


def _render_ref_body(b: _Body, rev: str, d: dict, prints: list[dict]):
    payload = d.get("payload") or {}
    _header_band(b, "II-REF   DESIGN REFERENCE", f"REV {rev}")
    _sec_title(b, "CONTROLLED REFERENCE DOCUMENTS")
    resolved = {p["item_number"]: p for p in prints}
    rows = []
    for doc in payload.get("docs") or []:
        r = resolved.get(doc.get("item_number"))
        pdf_cell = "MISSING" if (r or {}).get("missing") else ("YES" if r else "--")
        rows.append([doc.get("item_number"), doc.get("name"), doc.get("revision") or "--", pdf_cell])
    _table(b, [("DOC #", 90), ("TITLE", 292), ("DOC REV", 70), ("PDF", 80)], rows)
    b.y -= 10
    c = b.c
    b.need(34)
    c.setLineWidth(1.25)
    c.setStrokeColor(INK)
    c.rect(MARGIN, b.y - 30, CONTENT_W, 28, fill=0, stroke=1)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(MARGIN + 6, b.y - 12, "THESE DOCUMENTS GOVERN OVERALL ENVELOPE AND CRITICAL DIMENSIONS.")
    c.drawString(MARGIN + 6, b.y - 24, "IF ANY SECTION PRINT CONFLICTS: STOP -- CONFIRM WITH ENGINEERING BEFORE CUTTING.")
    b.y -= 40


def _render_general_body(b: _Body, rev: str, d: dict):
    payload = d.get("payload") or {}
    _header_band(b, "III-00   GENERAL REFERENCE", f"REV {rev}")
    c = b.c
    c.setFillColor(INK)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN, b.y - 8, "NOTES AND PHOTOS CAPTURED ON THE FLOOR. LATER SUBSECTIONS (III-01+) ADD INGESTED DOCUMENTS.")
    b.y -= 18

    for _ in range(int(payload.get("notesPages") or 6)):
        c.showPage()
        b.y = PAGE_H - MARGIN
        _sec_title(b, "FLOOR NOTES")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(MARGIN, b.y - 8, "DATE ____________   INITIALS ______   RE: SECTION ____________")
        b.y -= 20
        c.setStrokeColor(RULE_LT)
        c.setLineWidth(0.5)
        y = b.y
        while y > 60:
            c.line(MARGIN, y, PAGE_W - MARGIN, y)
            y -= 24

    for _ in range(int(payload.get("photoPages") or 4)):
        c.showPage()
        b.y = PAGE_H - MARGIN
        _sec_title(b, "BUILD AREA PHOTOS")
        frame_w, frame_h, gutter = 260, 280, 12
        top = b.y - 6
        for row in range(2):
            for col in range(2):
                x = MARGIN + col * (frame_w + gutter)
                y = top - row * (frame_h + 46) - frame_h
                c.setLineWidth(1)
                c.setStrokeColor(INK)
                c.rect(x, y, frame_w, frame_h, fill=0, stroke=1)
                c.setFont("Helvetica", 6.5)
                c.setFillColor(INK)
                c.drawString(x, y - 12, "PHOTO: ______________________________")
                c.drawString(x, y - 24, "NOTE:  ______________________________")
        b.y = 40


def _render_spine_body(b: _Body, book: dict, spine: dict, toc_rows: list[dict], rev_history: list[dict], rev: str):
    payload = spine.get("payload") or {}
    c = b.c

    # ---- cover ----
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN, b.y - 8, "MASTER DESIGN BOOK")
    b.y -= 16
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, b.y - 18, _trunc(c, book.get("title", "").upper(), "Helvetica-Bold", 20, CONTENT_W))
    b.y -= 26
    # no Generated date here — calendar dates live in exactly three places
    # (footer GEN, rev-history ISSUED, notice header); review finding m2
    meta = (
        f"Product {book.get('product_item_number')}  -  Template project {book.get('template_project_code') or '--'}"
        f"  -  Book rev {book.get('book_rev')}"
    )
    c.setFont("Helvetica", 8.5)
    c.drawString(MARGIN, b.y - 8, _ascii(meta))
    b.y -= 18

    c.setLineWidth(1.25)
    c.setStrokeColor(INK)
    c.rect(MARGIN, b.y - 24, CONTENT_W, 22, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(INK)
    c.drawString(MARGIN + 6, b.y - 11, "THIS IS THE MASTER HOW-TO-BUILD-ONE DOCUMENT. ALL CHECKBOXES ARE INTENTIONALLY BLANK.")
    c.drawString(MARGIN + 6, b.y - 20, "DAYS ARE RELATIVE (D1..Dn). FOR A LIVE JOB USE THAT PROJECT'S BUILD BOOK, NOT THIS BOOK.")
    b.y -= 34

    summ = payload.get("summary") or {}
    stats = [
        (str(summ.get("totalHours", "--")), "EST HOURS"),
        (str(summ.get("totalDays", "--")), "WORK DAYS"),
        (str(summ.get("packageCount", "--")), "WORK PKGS"),
        (str(summ.get("fabParts", "--")), "FAB PARTS"),
        (str(summ.get("assemblies", "--")), "WELD/ASSY"),
        (str(summ.get("purchased", "--")), "PURCHASED"),
    ]
    box_w = (CONTENT_W - 5 * 6) / 6
    x = MARGIN
    for val, label in stats:
        c.setLineWidth(1.25)
        c.rect(x, b.y - 34, box_w, 32, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(x + box_w / 2, b.y - 18, val)
        c.setFont("Helvetica-Bold", 5.5)
        c.drawCentredString(x + box_w / 2, b.y - 29, label)
        x += box_w + 6
    b.y -= 46

    _sec_title(b, "HOW TO USE THIS BOOK")
    usage = [
        "1. Sections are standalone booklets. Section I = one booklet per work package (cut/form/receive).",
        "   Section II = one booklet per weldment/assembly, prints included. Work them in checklist order.",
        "2. Every page footer carries BOOK REV (left), SECTION + REV (center), and page X of Y.",
        "   If a page's center footer does not match the section cover, the booklet is mixed -- rebuild it.",
        "3. CHANGE NOTICES: pull and destroy the OLD REV booklets listed, insert the NEW REV booklets,",
        "   replace 00-SPINE (reissued with every change), initial the revision history below.",
        "4. Photocopy checklist / buy-list pages for one-off use. Never write on the master.",
        "5. D1..Dn are working days from job start, not calendar dates.",
    ]
    c.setFont("Helvetica", 7.5)
    c.setFillColor(INK)
    for line in usage:
        b.need(11)
        c.drawString(MARGIN, b.y - 8, line)
        b.y -= 11
    b.y -= 8

    _sec_title(b, "REVISION HISTORY", "INITIAL WHEN FILED")
    hist_rows = []
    for ch in rev_history[:8]:
        n_diff = len(ch.get("diff") or [])
        # to_rev 1 = initial issue (no notice — no holders yet); later rows may
        # still be in-flight (notice not yet uploaded), but the label holds
        label = "(initial issue)" if ch.get("to_rev") == 1 else f"CHANGE-NOTICE-rev{ch.get('to_rev'):03d}"
        hist_rows.append([
            str(ch.get("to_rev")), str(ch.get("created_at", ""))[:10],
            label, f"{n_diff} section(s) affected", "",
        ])
    if not hist_rows:
        hist_rows = [[str(book.get("book_rev")), book.get("gen_date", ""), "(initial issue)", "all sections issued at rev A", ""]]
    _table(b, [("REV", 34), ("ISSUED", 70), ("CHANGE NOTICE", 150), ("SECTIONS AFFECTED", 216), ("FILED", 62)], hist_rows)

    # ---- buy list ----
    buy = payload.get("buyList") or []
    if buy:
        c.showPage()
        b.y = PAGE_H - MARGIN
        _sec_title(b, "BUY LIST -- ORDER BEFORE D1", "PAIRS WITH MILESTONE M10")
        rows = []
        for r in buy:
            rows.append([
                r.get("displayNumber"), r.get("source"), r.get("name"),
                r.get("qty"), "LONG" if r.get("longLead") else "", "[  ]", "[  ]",
            ])
        _table(
            b,
            [("PART #", 100), ("SOURCE", 88), ("DESCRIPTION", 208), ("QTY", 34), ("LEAD", 36), ("ORD", 33), ("RCV", 33)],
            rows,
        )

    # ---- master checklist ----
    c.showPage()
    b.y = PAGE_H - MARGIN
    total_days = summ.get("totalDays")
    _sec_title(
        b,
        f"MASTER DESIGN CHECKLIST -- D1..D{total_days}" if total_days else "MASTER DESIGN CHECKLIST",
        "ALL BOXES BLANK -- PHOTOCOPY PER BUILD",
    )
    ROW_H = 13
    cl_cols = [("", 18), ("DAY", 32), ("STN", 36), ("OPERATION", 300), ("EST H", 50), ("SEE", 96)]

    def cl_header():
        c.setFillColor(SHADE)
        c.rect(MARGIN, b.y - ROW_H, CONTENT_W, ROW_H, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 6.5)
        x = MARGIN
        for label, w in cl_cols:
            if label:
                c.drawString(x + 3, b.y - ROW_H + 4, label)
            x += w
        b.y -= ROW_H

    cl_header()
    last_day = None
    for row in payload.get("checklist") or []:
        if b.y - ROW_H < MARGIN + 18:
            c.showPage()
            b.y = PAGE_H - MARGIN
            cl_header()
            last_day = None
        if row.get("kind") == "milestone":
            c.setFillColor(SHADE_MD)
            c.rect(MARGIN, b.y - ROW_H, CONTENT_W, ROW_H, fill=1, stroke=0)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(PAGE_W / 2, b.y - ROW_H + 4, _ascii(f"M{row.get('op')}  {str(row.get('text', '')).upper()}"))
            b.y -= ROW_H
            continue
        if last_day is not None and row.get("day") != last_day:
            c.setStrokeColor(INK)
            c.setLineWidth(1)
            c.line(MARGIN, b.y, MARGIN + CONTENT_W, b.y)
        last_day = row.get("day")
        x = MARGIN
        _checkbox(c, x + 4, b.y - ROW_H + 2.5)
        x += 18
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x + 3, b.y - ROW_H + 4, dayLabel(row["day"]) if row.get("day", -1) >= 0 else "--")
        x += 32
        c.drawString(x + 3, b.y - ROW_H + 4, _ascii(row.get("stn") or ""))
        x += 36
        c.setFont("Helvetica", 7.5)
        c.drawString(x + 3, b.y - ROW_H + 4, _trunc(c, row.get("text", ""), "Helvetica", 7.5, 294))
        x += 300
        c.drawString(x + 3, b.y - ROW_H + 4, str(row.get("estH") if row.get("estH") is not None else ""))
        x += 50
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x + 3, b.y - ROW_H + 4, _ascii(row.get("see") or ""))
        c.setStrokeColor(RULE_LT)
        c.setLineWidth(0.5)
        c.line(MARGIN, b.y - ROW_H, MARGIN + CONTENT_W, b.y - ROW_H)
        b.y -= ROW_H

    # ---- table of contents ----
    c.showPage()
    b.y = PAGE_H - MARGIN
    _sec_title(b, "TABLE OF CONTENTS", "REVS AND PAGE COUNTS AS OF THIS BOOK REV")
    rows = [["00-SPINE", rev, "MASTER CHECKLIST + TOC", "--", "--", "--"]]
    for t in toc_rows:
        rows.append([
            t["section_code"], t["rev"], t["title"],
            t.get("page_count") if t.get("page_count") is not None else "--",
            t.get("prints", "--"), t.get("ddays", ""),
        ])
    _table(b, [("SECTION", 88), ("REV", 30), ("TITLE", 230), ("PAGES", 44), ("PRINTS", 46), ("D-DAYS", 94)], rows)


def render_section(descriptor: dict, prints: list[dict], pdf_cache: dict[str, bytes],
                   book_meta: dict, rev: str, spine_extra: dict | None = None) -> tuple[bytes, int]:
    """Render one section booklet: body pages + bound prints + footer pass."""
    kind = descriptor["kind"]
    code = descriptor["section_code"]
    b = _Body()

    if kind == "spine":
        _render_spine_body(b, book_meta, descriptor, (spine_extra or {}).get("toc_rows") or [],
                           (spine_extra or {}).get("rev_history") or [], rev)
    elif kind == "work_package":
        _render_package_body(b, code, rev, descriptor, prints)
    elif kind == "assembly":
        _render_kit_body(b, code, rev, descriptor, prints)
    elif kind == "design_reference":
        _render_ref_body(b, rev, descriptor, prints)
    elif kind == "general_reference":
        _render_general_body(b, rev, descriptor)
    else:
        raise ValueError(f"Unknown section kind: {kind}")

    writer = PdfWriter()
    for page in b.finish().pages:
        writer.add_page(page)
    if kind in ("work_package", "assembly", "design_reference"):
        _bind_prints(writer, prints, pdf_cache, code)

    return _finalize_section(
        writer, book_meta["book_code"], book_meta["book_rev"], code, rev, book_meta["gen_date"]
    )


# ============================================================================
# Change notice
# ============================================================================

def render_change_notice(book_meta: dict, from_rev: int, to_rev: int, diff: list[dict]) -> bytes:
    b = _Body()
    c = b.c
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN, b.y - 8, f"CHANGE NOTICE No. {to_rev}")
    b.y -= 16
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, b.y - 16, _trunc(
        c, f"{book_meta.get('title', '').upper()} -- REV {from_rev} TO REV {to_rev}", "Helvetica-Bold", 18, CONTENT_W))
    b.y -= 24
    c.setFont("Helvetica", 8.5)
    c.drawString(MARGIN, b.y - 8, f"Book {book_meta['book_code']}  -  Product {book_meta.get('product_item_number')}  -  Issued {book_meta['gen_date']}")
    b.y -= 20

    c.setLineWidth(1.25)
    c.setStrokeColor(INK)
    c.rect(MARGIN, b.y - 34, CONTENT_W, 32, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(INK)
    c.drawString(MARGIN + 6, b.y - 11, "HOLDERS OF PRINTED COPIES: PULL AND DESTROY the OLD REV booklets listed below. INSERT the")
    c.drawString(MARGIN + 6, b.y - 20, "NEW REV booklets. 00-SPINE IS REISSUED WITH EVERY CHANGE -- ALWAYS REPLACE IT.")
    c.drawString(MARGIN + 6, b.y - 29, "Initial the revision history on the new spine cover when filed. Destroy superseded pages.")
    b.y -= 44

    _sec_title(b, "SECTION ACTIONS")
    rows = []
    order = {"REPLACE": 0, "INSERT": 1, "REMOVE": 2}
    for entry in sorted(diff, key=lambda e: (order.get(e.get("action"), 9), e.get("section_code", ""))):
        rows.append([
            entry.get("action"), entry.get("section_code"), entry.get("title") or "",
            entry.get("old_rev") or "--", entry.get("new_rev") or "--",
            entry.get("page_count") if entry.get("page_count") is not None else "--",
            "; ".join(entry.get("reasons") or []),
        ])
    _table(
        b,
        [("ACTION", 52), ("SECTION", 84), ("TITLE", 130), ("OLD", 30), ("NEW", 30), ("PAGES", 38), ("REASON", 168)],
        rows, row_h=13, font_size=6.5,
    )

    b.y -= 10
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(INK)
    for copy_name in ("SHOP WALL", "OFFICE   ", "SPARE    "):
        b.need(14)
        c.drawString(MARGIN, b.y - 9, f"COPY: {copy_name} __________   FILED BY ______   DATE ____ / ____")
        b.y -= 13

    writer = PdfWriter()
    for page in b.finish().pages:
        writer.add_page(page)
    n = len(writer.pages)
    for i, page in enumerate(writer.pages):
        _stamp_footer(
            page,
            f"MDB {book_meta['book_code'].upper()}  REV {to_rev}",
            f"CHANGE NOTICE No. {to_rev}",
            f"PAGE {i + 1} OF {n}  -  GEN {book_meta['gen_date']}",
        )
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()


# ============================================================================
# Storage + DB helpers
# ============================================================================

def _section_filename(section_code: str) -> str:
    return section_code.lower().replace(" ", "-") + ".pdf"


def _upload(supabase, path: str, data: bytes, content_type: str = "application/pdf"):
    supabase.storage.from_(BUCKET).upload(
        path, data, file_options={"content-type": content_type, "upsert": "true"}
    )


def _archive_object(supabase, book_code: str, storage_path: str, section_code: str, old_rev: str):
    """Best-effort copy of the outgoing section PDF to archive/ before overwrite.

    NEVER overwrites an existing archive object: after a mid-run crash the live
    path already holds the NEW bytes, and re-archiving them under the OLD rev
    would destroy the genuine archive (review finding M3). copy() rejects an
    existing destination — treated as success; the fallback upload does NOT
    upsert for the same reason.
    """
    try:
        dest = f"{book_code}/archive/{_section_filename(section_code).removesuffix('.pdf')}-rev{old_rev}.pdf"
        try:
            supabase.storage.from_(BUCKET).copy(storage_path, dest)
        except Exception as copy_err:
            msg = str(copy_err).lower()
            if "already exists" in msg or "duplicate" in msg or "409" in msg:
                return  # archive already made by a previous (crashed) run — keep it
            data = supabase.storage.from_(BUCKET).download(storage_path)
            if data:
                supabase.storage.from_(BUCKET).upload(
                    dest, data, file_options={"content-type": "application/pdf"}  # no upsert
                )
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "duplicate" in msg or "409" in msg:
            return
        logger.warning(f"Design book: archive of {storage_path} failed (non-fatal): {e}")


def _load_book(supabase, book_code: str) -> dict | None:
    res = supabase.table("design_books").select("*").eq("book_code", book_code).execute()
    return res.data[0] if res.data else None


def _load_sections(supabase, book_id: str) -> list[dict]:
    res = (
        supabase.table("design_book_sections")
        .select("*")
        .eq("book_id", book_id)
        .order("sort_order")
        .execute()
    )
    return res.data or []


def _load_changes(supabase, book_id: str) -> list[dict]:
    res = (
        supabase.table("design_book_changes")
        .select("*")
        .eq("book_id", book_id)
        .order("to_rev", desc=True)
        .execute()
    )
    return res.data or []


def _toc_rows(entries: list[dict]) -> list[dict]:
    """TOC/spine-hash rows from classified non-spine entries, in sort order."""
    rows = []
    for e in entries:
        d = e.get("descriptor")
        if d is None:  # retired
            continue
        display = d.get("display") or {}
        ddays = ""
        if display.get("day") is not None:
            ddays = dayLabel(display["day"])
        elif display.get("startDay") is not None:
            ddays = f"{dayLabel(display['startDay'])}-{dayLabel(display.get('endDay') or display['startDay'])}"
        n_prints = len([p for p in e.get("prints") or [] if not p.get("missing")])
        rows.append({
            "section_code": d["section_code"],
            "kind": d["kind"],
            "title": d.get("title") or "",
            "rev": e["rev"],
            "sort_order": d.get("sort_order", 0),
            # unchanged sections keep their stored page count — without the row
            # fallback the reissued TOC prints '--' for nearly everything on an
            # incremental update (review finding M2)
            "page_count": e.get("page_count") or (e.get("row") or {}).get("page_count"),
            "prints": n_prints,
            "ddays": ddays,
        })
    rows.sort(key=lambda r: r["sort_order"])
    return rows


def _spine_hash_input(spine_desc: dict, toc_rows: list[dict], renderer_version: int) -> dict:
    """Spine hash = its payload + the FINAL rev map of all other sections.

    Page counts are render outputs and are excluded (else /check and /update
    would hash differently); the printed TOC still shows them.
    """
    toc_for_hash = [
        {"section_code": t["section_code"], "kind": t["kind"], "title": t["title"],
         "rev": t["rev"], "sort_order": t["sort_order"]}
        for t in toc_rows
    ]
    hi = build_hash_input(spine_desc, prints=[], renderer_version=renderer_version)
    hi["toc"] = toc_for_hash
    return hi


# ============================================================================
# Qty verification (server-side; mirrors masterDesignBook.ts checkQuantities)
# ============================================================================

def verify_quantities(supabase, template_project_id: str) -> list[dict]:
    parts = (
        supabase.table("mrp_project_parts")
        .select("item_id, quantity, items(item_number)")
        .eq("project_id", template_project_id)
        .execute()
    )
    proj_qty, num_of = {}, {}
    for row in parts.data or []:
        proj_qty[row["item_id"]] = row["quantity"]
        num_of[row["item_id"]] = (row.get("items") or {}).get("item_number", row["item_id"])

    project = (
        supabase.table("mrp_projects").select("top_assembly_id").eq("id", template_project_id).single().execute()
    )
    top_id = (project.data or {}).get("top_assembly_id")
    if not top_id or top_id not in proj_qty:
        return []

    item_ids = list(proj_qty.keys())
    parents: dict[str, list] = {}
    for chunk in _chunks(item_ids, 50):  # bounded per request (finding m6)
        bom = (
            supabase.table("bom")
            .select("parent_item_id, child_item_id, quantity")
            .in_("parent_item_id", chunk)
            .execute()
        )
        for row in bom.data or []:
            if row["parent_item_id"] in proj_qty and row["child_item_id"] in proj_qty:
                parents.setdefault(row["child_item_id"], []).append(
                    {"parent": row["parent_item_id"], "qty": row["quantity"]}
                )

    # memoized usage-per-top — DAG-safe (a walk-down accumulator double-counts
    # grandchildren under multi-path subassemblies)
    memo: dict[str, int] = {}

    def usage(item_id: str, stack: set) -> int:
        if item_id == top_id:
            return proj_qty.get(top_id) or 1
        if item_id in memo:
            return memo[item_id]
        if item_id in stack:
            return 0
        stack.add(item_id)
        total = 0
        for p in parents.get(item_id, []):
            total += usage(p["parent"], stack) * (p["qty"] or 0)
        stack.discard(item_id)
        memo[item_id] = total
        return total

    mismatches = []
    for item_id in proj_qty:
        if item_id == top_id:
            continue
        expected = usage(item_id, set())
        if expected == 0:
            continue  # unreachable from top (manual attach, docs)
        if proj_qty[item_id] != expected:
            mismatches.append({
                "item_number": num_of[item_id],
                "project_qty": proj_qty[item_id],
                "bom_rollup_qty": expected,
            })
    mismatches.sort(key=lambda m: m["item_number"])
    return mismatches


# ============================================================================
# Manifest export
# ============================================================================

def export_manifest(supabase, book: dict, sections: list[dict], changes: list[dict]) -> dict:
    manifest = {
        "manifest_schema": 1,
        "book_code": book["book_code"],
        "title": book["title"],
        "product_item_number": book["product_item_number"],
        "template_project_id": book.get("template_project_id"),
        "book_rev": book["book_rev"],
        "renderer_version": book["renderer_version"],
        "generated_at": book.get("generated_at"),
        "sections": [
            {
                "section_code": s["section_code"], "kind": s["kind"], "title": s["title"],
                "rev": s["rev"], "status": s["status"], "sort_order": s["sort_order"],
                "content_hash": s.get("content_hash"), "storage_path": s.get("storage_path"),
                "page_count": s.get("page_count"), "identity": s.get("identity"),
                "display": s.get("display"), "source": s.get("source"),
            }
            for s in sections
        ],
        "changes": [
            {"from_rev": ch["from_rev"], "to_rev": ch["to_rev"], "created_at": ch.get("created_at"),
             "notice_path": ch.get("notice_storage_path"), "diff": ch.get("diff")}
            for ch in changes
        ],
    }
    try:
        _upload(
            supabase, f"{book['book_code']}/manifest.json",
            json.dumps(manifest, indent=1).encode("utf-8"), content_type="application/json",
        )
    except Exception as e:
        logger.warning(f"Design book: manifest export failed (DB is authoritative): {e}")
    return manifest


# ============================================================================
# Payload preparation shared by /check and /update
# ============================================================================

def _prepare(supabase, book: dict, payload: dict) -> dict:
    """Steps 2-5 of the update algorithm: validate, resolve prints, hash, diff, spine."""
    descriptors = payload.get("sections") or []
    meta = payload.get("meta") or {}

    # -- validation
    codes = [d.get("section_code") for d in descriptors]
    if len(set(codes)) != len(codes):
        raise ValueError("Duplicate section codes in payload")
    identities = [_identity_key(d.get("identity") or {}) for d in descriptors]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate section identities in payload")
    for kind in ("spine", "design_reference", "general_reference"):
        n = sum(1 for d in descriptors if d.get("kind") == kind)
        if n != 1:
            raise ValueError(f"Expected exactly one {kind} section, got {n}")

    # -- server-side qty gate
    qty_mismatches: list[dict] = []
    if book.get("template_project_id"):
        qty_mismatches = verify_quantities(supabase, book["template_project_id"])
        if qty_mismatches and not meta.get("allow_qty_mismatch"):
            raise QtyGateError(qty_mismatches)

    # -- resolve prints once (files table only — zero downloads)
    all_nums = []
    for d in descriptors:
        for it in d.get("print_items") or []:
            all_nums.append(it["item_number"])
    file_by_num = _fetch_print_files(supabase, list(dict.fromkeys(all_nums)))

    renderer_version = book["renderer_version"]
    existing = _load_sections(supabase, book["id"]) if book.get("id") else []

    spine_desc = next(d for d in descriptors if d["kind"] == "spine")
    non_spine = [d for d in descriptors if d["kind"] != "spine"]

    incoming = []
    for d in non_spine:
        prints = resolve_prints(d, file_by_num)
        hi = build_hash_input(d, prints, renderer_version)
        incoming.append({
            "descriptor": d, "prints": prints,
            "hash_input": hi, "content_hash": content_hash(hi),
        })

    diff = classify_sections(
        [r for r in existing if r["section_code"] != spine_desc["section_code"] and r["kind"] != "spine"],
        incoming, rebaseline=bool(meta.get("rebaseline")),
    )

    # -- two-phase spine hash against the FINAL rev map
    non_spine_entries = diff["added"] + diff["changed"] + diff["unchanged"]
    toc = _toc_rows(non_spine_entries)
    spine_hi = _spine_hash_input(spine_desc, toc, renderer_version)
    spine_hash = content_hash(spine_hi)
    spine_row = next((r for r in existing if r["kind"] == "spine"), None)
    if spine_row is None:
        spine_entry = {"descriptor": spine_desc, "prints": [], "hash_input": spine_hi,
                       "content_hash": spine_hash, "row": None, "rev": "A", "reasons": ["NEW"]}
        diff["added"].append(spine_entry)
    elif spine_row.get("content_hash") == spine_hash:
        # identical hash never bumps the letter — a rebaseline just re-renders
        # the same rev (byte refresh), mirroring non-spine sections (finding m3)
        entry = {"descriptor": spine_desc, "prints": [], "hash_input": spine_hi,
                 "content_hash": spine_hash, "row": spine_row, "rev": spine_row["rev"]}
        if meta.get("rebaseline"):
            entry["refresh"] = True
        diff["unchanged"].append(entry)
    else:
        reasons = derive_reasons(spine_row.get("source"), spine_hi)
        diff["changed"].append({"descriptor": spine_desc, "prints": [], "hash_input": spine_hi,
                                "content_hash": spine_hash, "row": spine_row,
                                "old_rev": spine_row["rev"], "rev": next_rev(spine_row["rev"]),
                                "reasons": reasons})

    warnings = []
    for entry in incoming:
        for p in entry["prints"]:
            if p.get("missing"):
                warnings.append({
                    "type": "missing_print",
                    "section_code": entry["descriptor"]["section_code"],
                    "item_number": p["item_number"],
                })
    for m in qty_mismatches:
        warnings.append({"type": "qty_mismatch", **m})

    return {"diff": diff, "toc": toc, "warnings": warnings, "spine_desc": spine_desc}


def _diff_summary(diff: dict) -> dict:
    def brief(entries, with_old=True):
        out = []
        for e in entries:
            d = e.get("descriptor") or {}
            row = e.get("row") or {}
            out.append({
                "section_code": d.get("section_code") or row.get("section_code"),
                "title": d.get("title") or row.get("title"),
                "old_rev": e.get("old_rev") if with_old else None,
                "new_rev": e.get("rev") if d else None,
                "last_rev": row.get("rev") if not d else None,
                "reasons": e.get("reasons") or [],
                "page_count": e.get("page_count"),
            })
        return out

    return {
        "added": brief(diff["added"], with_old=False),
        "changed": brief(diff["changed"]),
        "retired": brief(diff["retired"]),
        "unchanged": [
            (e.get("row") or {}).get("section_code") or (e.get("descriptor") or {}).get("section_code")
            for e in diff["unchanged"]
        ],
    }


# ============================================================================
# Entry points
# ============================================================================

def check_master_book(book_code: str, payload: dict) -> dict:
    """Dry run: hash + diff + reasons. Zero downloads, zero writes."""
    supabase = get_supabase_admin()
    book = _load_book(supabase, book_code)
    meta = payload.get("meta") or {}
    if book is None:
        if not meta.get("create"):
            raise BookNotFound(book_code)
        book = _virtual_book(book_code, meta, supabase)

    prep = _prepare(supabase, book, payload)
    diff = prep["diff"]
    has_changes = bool(diff["added"] or diff["changed"] or diff["retired"])
    return {
        "book_rev": book["book_rev"],
        "next_book_rev": book["book_rev"] + 1 if has_changes else book["book_rev"],
        "would_issue_notice": has_changes and book["book_rev"] > 0,
        **_diff_summary(diff),
        "warnings": prep["warnings"],
    }


def _virtual_book(book_code: str, meta: dict, supabase) -> dict:
    """In-memory book row for first-generation dry runs (nothing persisted)."""
    template_id = None
    if meta.get("template_project_code"):
        res = supabase.table("mrp_projects").select("id").eq(
            "project_code", meta["template_project_code"]).execute()
        template_id = res.data[0]["id"] if res.data else None
    return {
        "id": None, "book_code": book_code,
        "title": meta.get("title") or book_code,
        "product_item_number": meta.get("product_item_number"),
        "template_project_id": template_id,
        "book_rev": 0, "renderer_version": 1, "status": "draft", "generated_at": None,
    }


def update_master_book(book_code: str, payload: dict) -> dict:
    """The full update algorithm (Documentation/36 section 4.3)."""
    supabase = get_supabase_admin()
    meta = payload.get("meta") or {}
    now = datetime.now(timezone.utc)
    gen_date = now.strftime("%Y-%m-%d")

    # 1. load / create book row; optimistic concurrency
    book = _load_book(supabase, book_code)
    if book is None:
        if not meta.get("create"):
            raise BookNotFound(book_code)
        virtual = _virtual_book(book_code, meta, supabase)
        ins = supabase.table("design_books").insert({
            "book_code": book_code,
            "title": virtual["title"],
            "product_item_number": virtual["product_item_number"],
            "template_project_id": virtual["template_project_id"],
            "book_rev": 0,
            "renderer_version": 1,
            "status": "draft",
        }).execute()
        book = ins.data[0]
    elif meta.get("create") and book["book_rev"] > 0:
        raise ValueError(f"Book {book_code} already exists (rev {book['book_rev']})")
    # create:true against an existing rev-0 book = resuming a failed first
    # generation — proceed (idempotent create)
    if meta.get("expected_book_rev") is not None and meta["expected_book_rev"] != book["book_rev"]:
        raise BookConflict(f"expected_book_rev {meta['expected_book_rev']} != current {book['book_rev']}")
    previous_rev = book["book_rev"]  # captured before any mutation

    # 2-5. validate, qty gate, resolve prints, hash, diff, spine
    prep = _prepare(supabase, book, payload)
    diff = prep["diff"]

    # 6. no-op exit (idempotence) — but first: a crash AFTER all section
    # commits and BEFORE the book_rev bump leaves every row already holding
    # the new hashes, so the diff is empty while an open change row dangles.
    # Resume that commit instead of reporting "no changes" (review finding C1).
    refreshes = [e for e in diff["unchanged"] if e.get("refresh")]
    if not (diff["added"] or diff["changed"] or diff["retired"] or refreshes):
        resumed = _resume_open_commit(supabase, book, gen_date, now)
        if resumed:
            resumed["warnings"] = prep["warnings"]
            return resumed
        return {
            "book_rev": book["book_rev"], "previous_rev": book["book_rev"],
            **_diff_summary(diff),
            "change_notice_path": None, "change_notice_url": None,
            "warnings": prep["warnings"],
        }

    new_rev = book["book_rev"] + 1
    is_first = book["book_rev"] == 0

    # 7. write-ahead change record (merge any open row from a crashed run)
    notice_diff = _notice_diff_entries(diff)
    open_rows = (
        supabase.table("design_book_changes").select("*")
        .eq("book_id", book["id"]).gt("to_rev", book["book_rev"]).execute()
    ).data or []
    if open_rows:
        merged = {e["section_code"]: e for e in (open_rows[0].get("diff") or [])}
        for e in notice_diff:
            prev = merged.get(e["section_code"])
            if prev:
                e = {**e, "old_rev": prev.get("old_rev") or e.get("old_rev")}
            merged[e["section_code"]] = e
        notice_diff = list(merged.values())
        supabase.table("design_book_changes").update({
            "from_rev": open_rows[0]["from_rev"], "to_rev": new_rev,
            "diff": notice_diff, "notice_storage_path": None,
        }).eq("id", open_rows[0]["id"]).execute()
        change_row_id = open_rows[0]["id"]
    else:
        ins = supabase.table("design_book_changes").insert({
            "book_id": book["id"], "from_rev": book["book_rev"], "to_rev": new_rev,
            "diff": notice_diff, "notice_storage_path": None,
        }).execute()
        change_row_id = ins.data[0]["id"]

    # 8. download print bytes for sections being rendered
    to_render = diff["added"] + diff["changed"] + refreshes
    to_render.sort(key=lambda e: (e["descriptor"].get("sort_order", 0)))
    needed_paths: dict[str, str] = {}
    for e in to_render:
        for p in e["prints"]:
            if not p.get("missing"):
                needed_paths[p["item_number"]] = p["file_path"]
    pdf_cache: dict[str, bytes] = {}
    if needed_paths:
        from .print_packet import _compress_pdf  # once per unique print, at cache time
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_download_pdf, supabase, path): num for num, path in needed_paths.items()}
            for fut in concurrent.futures.as_completed(futures):
                data = fut.result()
                if data:
                    pdf_cache[futures[fut]] = _compress_pdf(data)
    logger.info(f"Design book {book_code}: rendering {len(to_render)} sections, {len(pdf_cache)} prints cached")

    book_meta = {
        "book_code": book_code, "book_rev": new_rev, "title": book["title"],
        "product_item_number": book["product_item_number"],
        "template_project_code": meta.get("template_project_code"),
        "gen_date": gen_date,
    }
    rev_history = _load_changes(supabase, book["id"])

    # 9. render -> upload -> THEN row upsert, per section (DB never leads storage)
    section_results = []
    spine_entries = [e for e in to_render if e["descriptor"]["kind"] == "spine"]
    normal_entries = [e for e in to_render if e["descriptor"]["kind"] != "spine"]

    # storage paths this run will (re)write — guards rename/retire deletions
    # against clobbering an object another section adopts (review finding M4)
    target_paths = {
        f"{book_code}/{_section_filename(e['descriptor']['section_code'])}" for e in to_render
    }

    # retire FIRST: frees section_codes (partial unique index covers only
    # 'current' rows) and clears old objects before an adopter uploads
    for e in diff["retired"]:
        row = e["row"]
        if row.get("storage_path"):
            _archive_object(supabase, book_code, row["storage_path"], row["section_code"], row["rev"])
            if row["storage_path"] not in target_paths:
                try:
                    supabase.storage.from_(BUCKET).remove([row["storage_path"]])
                except Exception as ex:
                    logger.warning(f"Design book: could not remove retired object {row['storage_path']}: {ex}")
        supabase.table("design_book_sections").update({
            "status": "retired", "storage_path": None,
        }).eq("id", row["id"]).execute()

    for e in normal_entries:
        _render_upload_commit(supabase, book, book_meta, e, pdf_cache, section_results, target_paths)

    # spine LAST — its TOC needs final page counts of everything rendered this run
    toc = _toc_rows(diff["added"] + diff["changed"] + diff["unchanged"])
    for t in toc:  # fill page counts rendered this run
        for e in normal_entries:
            if e["descriptor"]["section_code"] == t["section_code"] and e.get("page_count"):
                t["page_count"] = e["page_count"]
    for e in spine_entries:
        _render_upload_commit(
            supabase, book, book_meta, e, pdf_cache, section_results, target_paths,
            spine_extra={"toc_rows": toc, "rev_history": rev_history},
        )

    # metadata-only sync for unchanged sections whose binder position or title
    # moved without a content change (review finding m7)
    for e in diff["unchanged"]:
        row, d = e.get("row"), e.get("descriptor")
        if not row or not d or e.get("refresh"):
            continue
        if row.get("sort_order") != d.get("sort_order", 0) or row.get("title") != (d.get("title") or ""):
            supabase.table("design_book_sections").update({
                "sort_order": d.get("sort_order", 0), "title": d.get("title") or "",
            }).eq("id", row["id"]).execute()

    # 10. change notice (not on first generation — no holders yet)
    notice_path = None
    if not is_first:
        # enrich notice entries with rendered page counts
        pages_by_code = {r["section_code"]: r["page_count"] for r in section_results}
        for entry in notice_diff:
            if entry.get("section_code") in pages_by_code:
                entry["page_count"] = pages_by_code[entry["section_code"]]
        notice_pdf = render_change_notice(book_meta, book["book_rev"], new_rev, notice_diff)
        notice_path = f"{book_code}/changes/CHANGE-NOTICE-rev{new_rev:03d}.pdf"
        _upload(supabase, notice_path, notice_pdf)
    supabase.table("design_book_changes").update({
        "diff": notice_diff, "notice_storage_path": notice_path,
    }).eq("id", change_row_id).execute()

    # 11. commit point
    supabase.table("design_books").update({
        "book_rev": new_rev, "generated_at": now.isoformat(), "status": "current",
    }).eq("id", book["id"]).execute()

    # 12. manifest export (DB authoritative; manifest is the portable serialization)
    book_after = _load_book(supabase, book_code)
    sections_after = _load_sections(supabase, book["id"])
    changes_after = _load_changes(supabase, book["id"])
    export_manifest(supabase, book_after, sections_after, changes_after)

    notice_url = None
    if notice_path:
        try:
            signed = supabase.storage.from_(BUCKET).create_signed_url(notice_path, 3600)
            notice_url = signed.get("signedURL") or signed.get("signedUrl")
        except Exception:
            pass

    return {
        "book_rev": new_rev, "previous_rev": previous_rev,
        **_diff_summary(diff),
        "sections": section_results,
        "change_notice_path": notice_path,
        "change_notice_url": notice_url,
        "warnings": prep["warnings"],
    }


def _resume_open_commit(supabase, book: dict, gen_date: str, now) -> dict | None:
    """Finish a crashed update whose sections all committed (review finding C1).

    State: section rows carry the new hashes/revs, but design_books.book_rev
    was never bumped and an open design_book_changes row (to_rev > book_rev)
    dangles, possibly without its notice. Resume: notice -> bump -> manifest.
    """
    open_rows = (
        supabase.table("design_book_changes").select("*")
        .eq("book_id", book["id"]).gt("to_rev", book["book_rev"]).execute()
    ).data or []
    if not open_rows:
        return None
    row = open_rows[0]
    new_rev = row["to_rev"]
    book_code = book["book_code"]
    book_meta = {
        "book_code": book_code, "book_rev": new_rev, "title": book["title"],
        "product_item_number": book["product_item_number"], "gen_date": gen_date,
    }
    notice_path = row.get("notice_storage_path")
    if row["from_rev"] > 0 and not notice_path:
        notice_pdf = render_change_notice(book_meta, row["from_rev"], new_rev, row.get("diff") or [])
        notice_path = f"{book_code}/changes/CHANGE-NOTICE-rev{new_rev:03d}.pdf"
        _upload(supabase, notice_path, notice_pdf)
        supabase.table("design_book_changes").update(
            {"notice_storage_path": notice_path}
        ).eq("id", row["id"]).execute()

    supabase.table("design_books").update({
        "book_rev": new_rev, "generated_at": now.isoformat(), "status": "current",
    }).eq("id", book["id"]).execute()

    book_after = _load_book(supabase, book_code)
    sections_after = _load_sections(supabase, book["id"])
    changes_after = _load_changes(supabase, book["id"])
    export_manifest(supabase, book_after, sections_after, changes_after)

    entries = row.get("diff") or []
    by_action = lambda a: [e for e in entries if e.get("action") == a]  # noqa: E731
    logger.info(f"Design book {book_code}: resumed crashed commit -> rev {new_rev}")
    return {
        "book_rev": new_rev, "previous_rev": book["book_rev"], "resumed": True,
        "added": by_action("INSERT"), "changed": by_action("REPLACE"),
        "retired": by_action("REMOVE"), "unchanged": [],
        "change_notice_path": notice_path, "change_notice_url": None,
    }


def _notice_diff_entries(diff: dict) -> list[dict]:
    entries = []
    for e in diff["changed"]:
        entries.append({
            "action": "REPLACE",
            "section_code": e["descriptor"]["section_code"],
            "title": e["descriptor"].get("title"),
            "old_rev": e.get("old_rev"), "new_rev": e["rev"],
            "reasons": e.get("reasons") or [],
        })
    for e in diff["added"]:
        entries.append({
            "action": "INSERT",
            "section_code": e["descriptor"]["section_code"],
            "title": e["descriptor"].get("title"),
            "old_rev": None, "new_rev": e["rev"],
            "reasons": e.get("reasons") or [],
        })
    for e in diff["retired"]:
        row = e["row"]
        entries.append({
            "action": "REMOVE",
            "section_code": row["section_code"], "title": row.get("title"),
            "old_rev": row["rev"], "new_rev": None,
            "reasons": ["RETIRED -- DO NOT REPLACE"],
        })
    return entries


def _render_upload_commit(supabase, book, book_meta, entry, pdf_cache, results, target_paths=None, spine_extra=None):
    """Render one section, upload it, then (and only then) upsert its DB row."""
    d = entry["descriptor"]
    code = d["section_code"]
    pdf_bytes, page_count = render_section(d, entry["prints"], pdf_cache, book_meta, entry["rev"], spine_extra)
    entry["page_count"] = page_count

    storage_path = f"{book_meta['book_code']}/{_section_filename(code)}"
    if len(pdf_bytes) > MAX_STORE_BYTES:
        # fail BEFORE uploading/committing anything for this section — a clear,
        # actionable error beats a mid-run storage rejection (review finding M5)
        raise ValueError(
            f"Section {code} renders to {len(pdf_bytes) / 1048576:.1f} MB, over the "
            f"{MAX_STORE_BYTES / 1048576:.0f} MB storage guard — split the package or reduce prints"
        )
    old_row = entry.get("row")

    # archive-on-supersede: keep the outgoing rev retrievable
    if old_row and old_row.get("storage_path") and old_row.get("rev") != entry["rev"]:
        _archive_object(supabase, book_meta["book_code"], old_row["storage_path"], old_row["section_code"], old_row["rev"])

    _upload(supabase, storage_path, pdf_bytes)

    # rename: remove the old object after the new upload succeeded — unless
    # another section in this run owns that path now (review finding M4)
    if old_row and old_row.get("storage_path") and old_row["storage_path"] != storage_path:
        if not target_paths or old_row["storage_path"] not in target_paths:
            try:
                supabase.storage.from_(BUCKET).remove([old_row["storage_path"]])
            except Exception as ex:
                logger.warning(f"Design book: could not remove renamed object {old_row['storage_path']}: {ex}")

    row_data = {
        "book_id": book["id"],
        "section_code": code,
        "kind": d["kind"],
        "title": d.get("title") or "",
        "sort_order": d.get("sort_order", 0),
        "rev": entry["rev"],
        "identity": d.get("identity") or {},
        "display": d.get("display"),
        "content_hash": entry["content_hash"],
        "source": entry["hash_input"],
        "storage_path": storage_path,
        "page_count": page_count,
        "status": "current",
    }
    if old_row:
        supabase.table("design_book_sections").update(row_data).eq("id", old_row["id"]).execute()
    else:
        supabase.table("design_book_sections").insert(row_data).execute()

    results.append({"section_code": code, "rev": entry["rev"], "storage_path": storage_path, "page_count": page_count})


# ============================================================================
# Full merged book — byte-concat of the CURRENT stored section PDFs
# ============================================================================

def build_full_book(book_code: str) -> dict:
    """Merged book with nested bookmarks + per-section page labels.

    Never re-rendered: byte-identical to the modular truth (a re-render could
    bind print bytes never issued under the certified rev letters, because
    print storage paths are overwritten in place).
    """
    supabase = get_supabase_admin()
    book = _load_book(supabase, book_code)
    if book is None:
        raise BookNotFound(book_code)
    sections = [s for s in _load_sections(supabase, book["id"]) if s["status"] == "current" and s.get("storage_path")]
    if not sections:
        raise ValueError("No current sections to merge")

    # download all current section PDFs in parallel
    cache: dict[str, bytes] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {}
        for s in sections:
            futures[pool.submit(lambda p: supabase.storage.from_(BUCKET).download(p), s["storage_path"])] = s["section_code"]
        for fut in concurrent.futures.as_completed(futures):
            try:
                cache[futures[fut]] = fut.result()
            except Exception as e:
                logger.warning(f"Design book: full-book download failed for {futures[fut]}: {e}")

    writer = PdfWriter()
    groups = {
        "work_package": "SECTION I -- WORK PACKAGES",
        "assembly": "SECTION II -- ASSEMBLIES",
        "design_reference": "SECTION II -- ASSEMBLIES",
        "general_reference": "SECTION III -- GENERAL REFERENCE",
    }
    group_nodes: dict[str, object] = {}
    merged = 0
    for s in sections:
        data = cache.get(s["section_code"])
        if not data:
            continue
        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:
            logger.warning(f"Design book: bad section PDF {s['section_code']}: {e}")
            continue
        start = len(writer.pages)
        writer.append(reader, import_outline=False)
        end = len(writer.pages) - 1
        label = f"{s['section_code']} {s['title']} (rev {s['rev']})"
        if s["kind"] == "spine":
            writer.add_outline_item(_ascii(f"00-SPINE -- MASTER CHECKLIST + TOC (rev {s['rev']})"), start)
        else:
            gname = groups.get(s["kind"], "SECTIONS")
            if gname not in group_nodes:
                group_nodes[gname] = writer.add_outline_item(gname, start)
            writer.add_outline_item(_ascii(label), start, parent=group_nodes[gname])
        try:
            writer.set_page_label(start, end, style="/D", prefix=f"{s['section_code']} ", start=1)
        except Exception as e:
            logger.warning(f"Design book: page label failed for {s['section_code']}: {e}")
        merged += 1

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    pdf_bytes = out.read()

    stored_path = None
    full_path = f"{book_code}/full/{book_code}-master-design-book.pdf"
    if len(pdf_bytes) <= MAX_STORE_BYTES:
        try:
            _upload(supabase, full_path, pdf_bytes)
            stored_path = full_path
        except Exception as e:
            logger.warning(f"Design book: full-book store failed ({len(pdf_bytes) // 1048576}MB): {e}")
    else:
        logger.info(f"Design book {book_code}: full book {len(pdf_bytes) // 1048576}MB over guard -- streaming only")

    return {
        "pdf": pdf_bytes, "book_code": book_code, "book_rev": book["book_rev"],
        "pages": len(writer.pages), "sections": merged, "stored_path": stored_path,
    }


# ============================================================================
# Read endpoints
# ============================================================================

def list_books() -> list[dict]:
    supabase = get_supabase_admin()
    books = supabase.table("design_books").select("*").order("book_code").execute().data or []
    out = []
    for book in books:
        sections = _load_sections(supabase, book["id"])
        stale = _stale_prints(supabase, sections)
        out.append({
            "book_code": book["book_code"], "title": book["title"],
            "product_item_number": book["product_item_number"],
            "book_rev": book["book_rev"], "renderer_version": book["renderer_version"],
            "status": book["status"], "generated_at": book.get("generated_at"),
            "section_count": len([s for s in sections if s["status"] == "current"]),
            "stale_print_count": len(stale),
        })
    return out


def get_book_detail(book_code: str) -> dict:
    supabase = get_supabase_admin()
    book = _load_book(supabase, book_code)
    if book is None:
        raise BookNotFound(book_code)
    sections = _load_sections(supabase, book["id"])
    changes = _load_changes(supabase, book["id"])
    stale = _stale_prints(supabase, sections)
    return {
        "book_code": book["book_code"], "title": book["title"],
        "product_item_number": book["product_item_number"],
        "template_project_id": book.get("template_project_id"),
        "book_rev": book["book_rev"], "renderer_version": book["renderer_version"],
        "status": book["status"], "generated_at": book.get("generated_at"),
        "sections": [
            {"section_code": s["section_code"], "kind": s["kind"], "title": s["title"],
             "rev": s["rev"], "status": s["status"], "sort_order": s["sort_order"],
             "page_count": s.get("page_count"), "storage_path": s.get("storage_path"),
             "updated_at": s.get("updated_at")}
            for s in sections
        ],
        "stale_prints": stale,
        "changes": [
            {"from_rev": ch["from_rev"], "to_rev": ch["to_rev"], "created_at": ch.get("created_at"),
             "notice_path": ch.get("notice_storage_path")}
            for ch in changes
        ],
    }


def _stale_prints(supabase, sections: list[dict]) -> list[dict]:
    """Passive staleness hint: bound (file_id, revision, iteration) vs newest.

    Computed in Python (PostgREST can't lateral-join); ~100 items is one query.
    The authoritative detector remains /check's re-hash.
    """
    bound: list[tuple[str, dict]] = []
    for s in sections:
        if s["status"] != "current":
            continue
        for p in (s.get("source") or {}).get("prints") or []:
            if not p.get("missing"):
                bound.append((s["section_code"], p))
    if not bound:
        return []
    nums = list({p["item_number"] for _, p in bound})
    newest = _fetch_print_files(supabase, nums)
    stale = []
    for code, p in bound:
        nw = newest.get(p["item_number"])
        if nw is None:
            continue
        if (p.get("file_id"), p.get("revision"), p.get("iteration")) != (
            nw["file_id"], nw.get("revision"), nw.get("iteration")
        ):
            stale.append({
                "section_code": code, "item_number": p["item_number"],
                "bound_revision": p.get("revision"), "bound_iteration": p.get("iteration"),
                "newest_revision": nw.get("revision"), "newest_iteration": nw.get("iteration"),
            })
    return stale


def get_section_url(book_code: str, section_code: str) -> dict:
    supabase = get_supabase_admin()
    book = _load_book(supabase, book_code)
    if book is None:
        raise BookNotFound(book_code)
    sections = _load_sections(supabase, book["id"])
    row = next((s for s in sections if s["section_code"] == section_code and s["status"] == "current"), None)
    if row is None or not row.get("storage_path"):
        raise BookNotFound(f"{book_code}/{section_code}")
    signed = supabase.storage.from_(BUCKET).create_signed_url(row["storage_path"], 3600)
    url = signed.get("signedURL") or signed.get("signedUrl")
    return {"url": url, "rev": row["rev"], "storage_path": row["storage_path"], "expires_in": 3600}


def get_change_notice_url(book_code: str, to_rev: int) -> dict:
    supabase = get_supabase_admin()
    book = _load_book(supabase, book_code)
    if book is None:
        raise BookNotFound(book_code)
    changes = _load_changes(supabase, book["id"])
    row = next((c for c in changes if c["to_rev"] == to_rev and c.get("notice_storage_path")), None)
    if row is None:
        raise BookNotFound(f"{book_code}/changes/{to_rev}")
    signed = supabase.storage.from_(BUCKET).create_signed_url(row["notice_storage_path"], 3600)
    url = signed.get("signedURL") or signed.get("signedUrl")
    return {"url": url, "from_rev": row["from_rev"], "to_rev": row["to_rev"], "expires_in": 3600}
