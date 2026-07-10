"""Unit tests for the Master Design Book service — pure logic + renderers.

No Supabase access: covers rev letters, the ASCII chokepoint, canonical
hashing, reason derivation, the identity-keyed diff engine, and the section
renderers (via fixture descriptors + generated dummy print PDFs).
"""
import io
import copy

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas as rl_canvas

from app.services.master_design_book import (
    _ascii,
    dayLabel,
    next_rev,
    _rev_to_int,
    _int_to_rev,
    canonical_json,
    content_hash,
    build_hash_input,
    resolve_prints,
    derive_reasons,
    classify_sections,
    _notice_diff_entries,
    _section_filename,
    _bind_prints,
    _stamp_footer,
    render_section,
    render_change_notice,
    _spine_hash_input,
    _toc_rows,
)


# ============================================================================
# helpers / fixtures
# ============================================================================

def make_pdf(pages: int = 1, size=landscape(letter)) -> bytes:
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=size)
    for i in range(pages):
        c.setFont("Helvetica", 10)
        c.drawString(72, 72, f"dummy print page {i + 1}")
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def pkg_descriptor():
    return {
        "section_code": "I-SAW-1",
        "kind": "work_package",
        "title": "SAW",
        "sort_order": 100,
        "identity": {"station_code": "010", "occurrence": 1},
        "display": {"day": 0},
        "payload": {
            "stationName": "Saw",
            "stationAbbrev": "SAW",
            "estMin": 175,
            "lines": [
                {"item_number": "csp00010", "displayNumber": "csp00010", "name": "TUBE",
                 "qty": 2, "estMin": 20, "next": "PB", "feeds": ["II-CSA00030"], "source": None},
                {"item_number": "mmc90098a036", "displayNumber": "90098A036", "name": "WASHER",
                 "qty": 4, "estMin": 5, "next": None, "feeds": [], "source": "McMaster-Carr"},
            ],
            "stockPull": [{"description": "2x2x0.125 SS Square Tube", "qty": 48, "parts": 1}],
            "stageFor": ["II-CSA00030"],
        },
        "print_items": [{"item_number": "csp00010", "qty": 2}],
        "no_print_expected": ["mmc90098a036"],
    }


def kit_descriptor():
    return {
        "section_code": "II-CSA00030",
        "kind": "assembly",
        "title": "LOWER FRAME -- CSA00030",
        "sort_order": 500,
        "identity": {"item_number": "csa00030"},
        "display": {"startDay": 4, "endDay": 7},  # rid deliberately absent (finding M1)
        "payload": {
            "item_number": "csa00030",
            "name": "LOWER FRAME",
            "qty": 1,
            "estMin": 390,
            "parts": [
                {"rid": "P01", "item_number": "csp00010", "displayNumber": "csp00010",
                 "name": "TUBE", "qty": 2, "readyBy": "I-SAW-1", "readyDay": 0, "source": None},
            ],
            "weldSeq": [
                {"station": "Weld Jigging", "abbrev": "JIG", "estMin": 180, "day": 4,
                 # deliberate unicode — must transliterate, not crash
                 "notes": "Square to rails — gussets pull the frame ±1/16″ if welded free. Ø0.25 holes."},
                {"station": "Tig Welding", "abbrev": "TIG", "estMin": 180, "day": 5, "notes": None},
            ],
            "childAsms": [],
        },
        "print_items": [
            {"item_number": "csa00030", "qty": 1},
            {"item_number": "csp00010", "qty": 2},
        ],
        "no_print_expected": [],
    }


def spine_descriptor():
    return {
        "section_code": "00-SPINE",
        "kind": "spine",
        "title": "MASTER CHECKLIST + TOC",
        "sort_order": 0,
        "identity": {"singleton": "spine"},
        "display": None,
        "payload": {
            "summary": {"totalHours": 44.5, "totalDays": 18, "packageCount": 12,
                        "fabParts": 40, "assemblies": 15, "purchased": 28},
            "milestones": [{"op": 10, "title": "All purchased parts ordered"}],
            "checklist": [
                {"kind": "milestone", "day": -1, "stn": None, "text": "All purchased parts ordered",
                 "estH": None, "see": None, "op": 10},
                {"kind": "package", "day": 0, "stn": "SAW", "text": "Work package - saw 2 parts",
                 "estH": 0.7, "see": "I-SAW-1", "op": None},
                {"kind": "kit_step", "day": 4, "stn": "JIG", "text": "LOWER FRAME - step 10 weld jigging",
                 "estH": 3.0, "see": "II-CSA00030", "op": None},
            ],
            "buyList": [
                {"item_number": "mmc90098a036", "displayNumber": "90098A036",
                 "source": "McMaster-Carr", "name": "WASHER", "qty": 4, "longLead": False},
            ],
            "stock": [{"description": "2x2x0.125 SS Square Tube", "qty": 48, "parts": 1}],
        },
        "print_items": [],
        "no_print_expected": [],
    }


FILE_ROWS = {
    "csp00010": {"file_id": "f-1", "file_path": "pdm-drawings/csp00010/a.pdf", "revision": "B", "iteration": 2},
    "csa00030": {"file_id": "f-2", "file_path": "pdm-drawings/csa00030/a.pdf", "revision": "A", "iteration": 1},
}

BOOK_META = {"book_code": "spa-standard", "book_rev": 1, "title": "Standard Spa Master Design Book",
             "product_item_number": "csa00010", "template_project_code": "SPA0030", "gen_date": "2026-07-09"}


def incoming(descriptor, file_rows=FILE_ROWS, renderer_version=1):
    prints = resolve_prints(descriptor, file_rows)
    hi = build_hash_input(descriptor, prints, renderer_version)
    return {"descriptor": descriptor, "prints": prints, "hash_input": hi, "content_hash": content_hash(hi)}


def row_from(entry, status="current", rev=None):
    d = entry["descriptor"]
    return {
        "id": f"row-{d['section_code']}", "section_code": d["section_code"], "kind": d["kind"],
        "title": d["title"], "sort_order": d["sort_order"], "rev": rev or "A",
        "identity": d["identity"], "display": d.get("display"),
        "content_hash": entry["content_hash"], "source": entry["hash_input"],
        "storage_path": f"spa-standard/{_section_filename(d['section_code'])}",
        "page_count": 3, "status": status,
    }


# ============================================================================
# pure logic
# ============================================================================

class TestRevLetters:
    def test_sequence(self):
        assert next_rev(None) == "A"
        assert next_rev("A") == "B"
        assert next_rev("Z") == "AA"
        assert next_rev("AA") == "AB"
        assert next_rev("AZ") == "BA"

    def test_roundtrip(self):
        for n in (1, 25, 26, 27, 52, 53, 702, 703):
            assert _rev_to_int(_int_to_rev(n)) == n


class TestAscii:
    def test_transliterations(self):
        assert _ascii("D2–D4 — ±1/16 Ø0.25 ▸ ok…") == 'D2-D4 -- +/-1/16 dia 0.25 > ok...'
        assert _ascii(None) == ""
        assert _ascii("plain ASCII stays") == "plain ASCII stays"

    def test_strips_unknown_unicode(self):
        assert _ascii("weld″here§") == "weldhere"

    def test_day_label(self):
        assert dayLabel(0) == "D1"
        assert dayLabel(17) == "D18"


class TestHashing:
    def test_deterministic_and_order_insensitive_keys(self):
        a = {"x": 1, "y": [1, 2], "z": {"b": 2, "a": 1}}
        b = {"z": {"a": 1, "b": 2}, "y": [1, 2], "x": 1}
        assert canonical_json(a) == canonical_json(b)

    def test_whole_floats_normalize(self):
        assert canonical_json({"q": 4.0}) == canonical_json({"q": 4})
        assert canonical_json({"q": 4.5}) != canonical_json({"q": 4})

    def test_done_keys_stripped(self):
        assert canonical_json({"a": 1, "done": True, "n": [{"rowDone": True, "b": 2}]}) == \
            canonical_json({"a": 1, "n": [{"b": 2}]})

    def test_hash_changes_on_print_revision(self):
        e1 = incoming(pkg_descriptor())
        rows2 = copy.deepcopy(FILE_ROWS)
        rows2["csp00010"]["revision"] = "C"
        rows2["csp00010"]["iteration"] = 3
        e2 = incoming(pkg_descriptor(), rows2)
        assert e1["content_hash"] != e2["content_hash"]

    def test_hash_changes_on_inplace_file_update(self):
        # same file_id + path, only iteration moved (files rows update in place)
        rows2 = copy.deepcopy(FILE_ROWS)
        rows2["csp00010"]["iteration"] = 3
        assert incoming(pkg_descriptor())["content_hash"] != incoming(pkg_descriptor(), rows2)["content_hash"]

    def test_missing_print_participates(self):
        assert incoming(pkg_descriptor(), {})["content_hash"] != incoming(pkg_descriptor())["content_hash"]

    def test_renderer_version_participates(self):
        assert incoming(pkg_descriptor(), renderer_version=2)["content_hash"] != \
            incoming(pkg_descriptor())["content_hash"]


class TestReasons:
    def test_new(self):
        assert derive_reasons(None, incoming(pkg_descriptor())["hash_input"]) == ["NEW"]

    def test_print_revision(self):
        old = incoming(pkg_descriptor())["hash_input"]
        rows2 = copy.deepcopy(FILE_ROWS)
        rows2["csp00010"].update(revision="C", iteration=3, file_id="f-9")
        new = incoming(pkg_descriptor(), rows2)["hash_input"]
        assert derive_reasons(old, new) == ["PRINT csp00010 B->C"]

    def test_print_added_after_missing(self):
        old = incoming(pkg_descriptor(), {})["hash_input"]
        new = incoming(pkg_descriptor())["hash_input"]
        assert "PRINT ADDED csp00010" in derive_reasons(old, new)

    def test_day_move(self):
        old = incoming(pkg_descriptor())["hash_input"]
        d2 = pkg_descriptor()
        d2["display"]["day"] = 2
        new = incoming(d2)["hash_input"]
        assert "MOVED D1->D3" in derive_reasons(old, new)

    def test_parts_qty_change(self):
        old = incoming(pkg_descriptor())["hash_input"]
        d2 = pkg_descriptor()
        d2["payload"]["lines"][0]["qty"] = 6
        d2["print_items"][0]["qty"] = 6
        new = incoming(d2)["hash_input"]
        joined = "; ".join(derive_reasons(old, new))
        assert "QTY csp00010 2->6" in joined

    def test_notes_revision(self):
        old = incoming(kit_descriptor())["hash_input"]
        d2 = kit_descriptor()
        d2["payload"]["weldSeq"][0]["notes"] = "different note"
        new = incoming(d2)["hash_input"]
        assert "NOTES REVISED" in derive_reasons(old, new)

    def test_renderer_bump_keeps_data_reasons(self):
        # a renderer bump must PREPEND the layout reason but still surface the data
        # change that motivated it (Documentation/38 §4.5)
        old = incoming(pkg_descriptor())["hash_input"]
        d2 = pkg_descriptor()
        d2["display"]["day"] = 5
        new = incoming(d2, renderer_version=2)["hash_input"]
        reasons = derive_reasons(old, new)
        assert reasons[0] == "LAYOUT UPDATE (renderer v1->v2)"
        assert "MOVED D1->D6" in reasons

    def test_renderer_bump_alone_is_layout_only(self):
        # identical content, only the renderer bumped -> LAYOUT UPDATE by itself
        old = incoming(pkg_descriptor())["hash_input"]
        new = incoming(pkg_descriptor(), renderer_version=2)["hash_input"]
        assert derive_reasons(old, new) == ["LAYOUT UPDATE (renderer v1->v2)"]

    def test_capped_at_three_plus_more(self):
        old = incoming(pkg_descriptor())["hash_input"]
        d2 = pkg_descriptor()
        d2["display"]["day"] = 3          # MOVED
        d2["payload"]["lines"][0]["qty"] = 6   # PARTS
        d2["payload"]["stockPull"] = []        # STOCK PULL REVISED
        rows2 = copy.deepcopy(FILE_ROWS)
        rows2["csp00010"].update(revision="C", file_id="f-9")  # PRINT
        new = incoming(d2, rows2)["hash_input"]
        reasons = derive_reasons(old, new)
        assert len(reasons) == 4
        assert reasons[-1].startswith("+")


class TestDiffEngine:
    def test_unchanged(self):
        e = incoming(pkg_descriptor())
        diff = classify_sections([row_from(e)], [e])
        assert len(diff["unchanged"]) == 1
        assert not diff["added"] and not diff["changed"] and not diff["retired"]

    def test_changed_bumps_rev(self):
        e_old = incoming(pkg_descriptor())
        d2 = pkg_descriptor()
        d2["payload"]["lines"][0]["qty"] = 6
        e_new = incoming(d2)
        diff = classify_sections([row_from(e_old, rev="B")], [e_new])
        assert len(diff["changed"]) == 1
        assert diff["changed"][0]["old_rev"] == "B"
        assert diff["changed"][0]["rev"] == "C"

    def test_rename_same_content_is_replace(self):
        e_old = incoming(pkg_descriptor())
        d2 = pkg_descriptor()
        d2["section_code"] = "I-SAW-9"  # identity unchanged, printed code changed
        e_new = incoming(d2)
        diff = classify_sections([row_from(e_old)], [e_new])
        assert len(diff["changed"]) == 1
        assert "RENAMED FROM I-SAW-1" in diff["changed"][0]["reasons"]

    def test_added_and_retired(self):
        e_pkg = incoming(pkg_descriptor())
        e_kit = incoming(kit_descriptor())
        diff = classify_sections([row_from(e_pkg)], [e_kit])
        assert len(diff["added"]) == 1 and diff["added"][0]["rev"] == "A"
        assert len(diff["retired"]) == 1
        assert diff["retired"][0]["row"]["section_code"] == "I-SAW-1"

    def test_reinstated_continues_letters(self):
        e = incoming(kit_descriptor())
        retired_row = row_from(e, status="retired", rev="C")
        diff = classify_sections([retired_row], [e])
        assert len(diff["added"]) == 1
        assert diff["added"][0]["rev"] == "D"
        assert diff["added"][0]["reasons"] == ["REINSTATED"]

    def test_rebaseline_refreshes_without_rev(self):
        e = incoming(pkg_descriptor())
        diff = classify_sections([row_from(e, rev="B")], [e], rebaseline=True)
        assert len(diff["unchanged"]) == 1
        assert diff["unchanged"][0].get("refresh") is True
        assert diff["unchanged"][0]["rev"] == "B"

    def test_notice_entries_actions(self):
        e_pkg = incoming(pkg_descriptor())
        d2 = pkg_descriptor()
        d2["payload"]["lines"][0]["qty"] = 6
        e_new = incoming(d2)
        e_kit = incoming(kit_descriptor())
        diff = classify_sections([row_from(e_pkg)], [e_new, e_kit])
        entries = _notice_diff_entries(diff)
        actions = {e["action"] for e in entries}
        assert actions == {"REPLACE", "INSERT"}


class TestSpineHash:
    def test_spine_revs_when_any_section_revs(self):
        spine = spine_descriptor()
        e1 = incoming(pkg_descriptor())
        toc1 = _toc_rows([{**e1, "rev": "A"}])
        h1 = content_hash(_spine_hash_input(spine, toc1, 1))
        toc2 = _toc_rows([{**e1, "rev": "B"}])
        h2 = content_hash(_spine_hash_input(spine, toc2, 1))
        assert h1 != h2

    def test_page_counts_do_not_affect_spine_hash(self):
        spine = spine_descriptor()
        e1 = {**incoming(pkg_descriptor()), "rev": "A"}
        toc1 = _toc_rows([e1])
        toc2 = _toc_rows([{**e1, "page_count": 99}])
        toc2[0]["page_count"] = 99
        assert content_hash(_spine_hash_input(spine, toc1, 1)) == \
            content_hash(_spine_hash_input(spine, toc2, 1))


# ============================================================================
# renderers
# ============================================================================

def _all_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestRenderers:
    def test_package_section_renders_with_prints_and_footers(self):
        e = incoming(pkg_descriptor())
        cache = {"csp00010": make_pdf(pages=2)}
        pdf, page_count = render_section(e["descriptor"], e["prints"], cache, BOOK_META, "B")
        assert page_count == 3  # 1 body + 2 print pages
        text = _all_text(pdf)
        assert "I-SAW-1 REV B" in text          # footer on every page
        assert "PAGE 3 OF 3" in text            # section-local numbering incl prints
        assert "QTY 2" in text                  # qty stamp on the print
        assert "90098A036" in text              # purchased display number
        assert "McMaster-Carr" in text          # purchased source
        assert "mmc90098a036" not in text       # raw prefix never prints

    def test_kit_section_unicode_notes_transliterated(self):
        e = incoming(kit_descriptor())
        cache = {"csp00010": make_pdf(), "csa00030": make_pdf()}
        pdf, page_count = render_section(e["descriptor"], e["prints"], cache, BOOK_META, "A")
        text = _all_text(pdf)
        assert "+/-1/16" in text
        assert "dia 0.25" in text
        assert "±" not in text and "Ø" not in text
        assert "I-SAW-1 - D1" in text            # READY BY cross-reference
        assert "PLAN D5-D8" in text              # relative-day plan
        assert "(D5)" in text                    # step day tag

    def test_assembly_parts_list_is_stage_set_not_kit(self):
        # "kit" now means a vendor purchase bundle; the assembly parts list is a STAGE SET
        e = incoming(kit_descriptor())
        cache = {"csp00010": make_pdf(), "csa00030": make_pdf()}
        pdf, _ = render_section(e["descriptor"], e["prints"], cache, BOOK_META, "A")
        text = _all_text(pdf)
        assert "STAGE SET -- PARTS REQUIRED" in text
        assert "IN SET ORDER" in text
        assert "KIT -- PARTS REQUIRED" not in text
        assert "IN KIT ORDER" not in text

    def test_package_bundle_band_and_for_set_column(self):
        d = pkg_descriptor()
        d["section_code"] = "I-RCV-1"
        d["payload"]["stationName"] = "Receiving"
        d["payload"]["lines"][0]["source"] = "KIT-001"  # bundled tube
        d["payload"]["bundles"] = [
            {"kit_number": "KIT-001", "kit_name": "Tube Laser Bundle",
             "vendor": "Precision Tube Laser", "partCount": 18}
        ]
        e = incoming(d)
        pdf, _ = render_section(e["descriptor"], e["prints"], {"csp00010": make_pdf()}, BOOK_META, "B")
        text = _all_text(pdf)
        assert "BUNDLE KIT-001 TUBE LASER BUNDLE" in text
        assert "Precision Tube Laser" in text
        assert "VERIFY 18 PARTS AGAINST PRINTS ON RECEIPT" in text
        assert "FOR SET" in text and "FOR KIT" not in text
        assert "KIT-001" in text  # the tube's source on its line

    def test_package_singular_part_in_bundle_band(self):
        d = pkg_descriptor()
        d["payload"]["bundles"] = [
            {"kit_number": "KIT-002", "kit_name": "Solo", "vendor": None, "partCount": 1}
        ]
        e = incoming(d)
        pdf, _ = render_section(e["descriptor"], e["prints"], {"csp00010": make_pdf()}, BOOK_META, "A")
        text = _all_text(pdf)
        assert "VERIFY 1 PART AGAINST" in text  # singular

    def test_kit_missing_print_flagged(self):
        e = incoming(kit_descriptor(), {"csp00010": FILE_ROWS["csp00010"]})  # csa00030 missing
        cache = {"csp00010": make_pdf()}
        pdf, _ = render_section(e["descriptor"], e["prints"], cache, BOOK_META, "A")
        text = _all_text(pdf)
        assert "MISSING PRINTS (1): csa00030" in text

    def test_spine_renders_checklist_buylist_toc(self):
        spine = spine_descriptor()
        e1 = {**incoming(pkg_descriptor()), "rev": "A", "page_count": 5}
        toc = _toc_rows([e1])
        pdf, page_count = render_section(
            spine, [], {}, BOOK_META, "A",
            spine_extra={"toc_rows": toc, "rev_history": []},
        )
        assert page_count >= 4  # cover, buy list, checklist, TOC
        text = _all_text(pdf)
        assert "MASTER DESIGN CHECKLIST" in text
        assert "BUY LIST" in text
        assert "TABLE OF CONTENTS" in text
        assert "I-SAW-1" in text
        assert "D1" in text
        assert "00-SPINE REV A" in text

    def test_spine_bundles_block_no_prices(self):
        spine = spine_descriptor()
        spine["payload"]["bundles"] = [
            {"kit_number": "KIT-001", "kit_name": "Tube Laser Bundle",
             "vendor": "Precision Tube Laser", "partCount": 18}
        ]
        e1 = {**incoming(pkg_descriptor()), "rev": "A", "page_count": 5}
        pdf, _ = render_section(
            spine, [], {}, BOOK_META, "A",
            spine_extra={"toc_rows": _toc_rows([e1]), "rev_history": []},
        )
        text = _all_text(pdf)
        assert "BUNDLES -- FINISHED PARTS" in text
        assert "KIT-001" in text
        assert "Precision Tube Laser" in text
        assert "18 parts" in text
        assert "PURCHASED PARTS" in text          # loose purchases still listed
        assert "90098A036" in text
        assert "$" not in text and "850" not in text  # never priced on shop paper

    def test_change_notice_renders_actions(self):
        diff = [
            {"action": "REPLACE", "section_code": "I-SAW-1", "title": "SAW",
             "old_rev": "A", "new_rev": "B", "page_count": 5, "reasons": ["MOVED D1->D2"]},
            {"action": "INSERT", "section_code": "II-CSA00099", "title": "NEW SUB",
             "old_rev": None, "new_rev": "A", "reasons": ["NEW"]},
            {"action": "REMOVE", "section_code": "I-HP-1", "title": "HOLE PUNCH",
             "old_rev": "A", "new_rev": None, "reasons": ["RETIRED -- DO NOT REPLACE"]},
        ]
        pdf = render_change_notice(BOOK_META, 1, 2, diff)
        text = _all_text(pdf)
        assert "CHANGE NOTICE No. 2" in text
        assert "REPLACE" in text and "INSERT" in text and "REMOVE" in text
        assert "MOVED D1->D2" in text
        assert "SHOP WALL" in text

    def test_bind_prints_dedupes_and_sums_qty(self):
        writer = PdfWriter()
        cache = {"csp00010": make_pdf()}
        prints = [
            {"item_number": "csp00010", "qty": 2, "file_id": "f-1", "file_path": "x", "revision": "B", "iteration": 1},
            {"item_number": "csp00010", "qty": 3, "file_id": "f-1", "file_path": "x", "revision": "B", "iteration": 1},
        ]
        bound = _bind_prints(writer, prints, cache, "I-SAW-1")
        assert bound == 1
        assert len(writer.pages) == 1
        out = io.BytesIO()
        writer.write(out)
        assert "QTY 5" in _all_text(out.getvalue())

    def test_footer_stamp_handles_rotated_pages(self):
        data = make_pdf(pages=1)
        reader = PdfReader(io.BytesIO(data))
        page = reader.pages[0]
        page.rotate(90)
        _stamp_footer(page, "L", "C-1 REV A", "PAGE 1 OF 1")
        writer = PdfWriter()
        writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        assert "C-1 REV A" in _all_text(out.getvalue())

    def test_section_filenames(self):
        assert _section_filename("00-SPINE") == "00-spine.pdf"
        assert _section_filename("I-SAW-1") == "i-saw-1.pdf"
        assert _section_filename("II-CSA00020") == "ii-csa00020.pdf"
