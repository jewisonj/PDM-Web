"""Update-algorithm tests: crash recovery, convergence, code adoption (finding M6).

Runs update_master_book against an in-memory fake Supabase (tables + storage +
failure injection) — verifies the ordering invariants the spec replaces
transactions with: DB never leads storage, book_rev bump is the commit point,
re-running after any mid-run crash converges, archives are never clobbered.
"""
import copy
from unittest.mock import patch

import pytest

from app.services.master_design_book import update_master_book, check_master_book


# ============================================================================
# Fake Supabase (tables + storage + failure injection)
# ============================================================================

class _Result:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table_name = table
        self.filters = []
        self._order = None
        self._limit = None
        self._single = False
        self._op = ("select", None)
        self._negate = False

    def select(self, *_a, **_k):
        return self

    def insert(self, payload):
        self._op = ("insert", payload)
        return self

    def update(self, payload):
        self._op = ("update", payload)
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def gt(self, col, val):
        self.filters.append(("gt", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    @property
    def not_(self):
        self._negate = True
        return self

    def is_(self, col, val):
        self.filters.append(("not_is" if self._negate else "is", col, val))
        self._negate = False
        return self

    def order(self, col, desc=False, nullsfirst=None):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    def _match(self, r):
        for op, col, val in self.filters:
            v = r.get(col)
            if op == "eq" and v != val:
                return False
            if op == "gt" and not (v is not None and v > val):
                return False
            if op == "in" and v not in val:
                return False
            if op == "not_is" and val == "null" and v is None:
                return False
            if op == "is" and val == "null" and v is not None:
                return False
        return True

    def _enforce_partial_unique(self, rows):
        seen = set()
        for r in rows:
            if r.get("status") == "current":
                key = (r.get("book_id"), r.get("section_code"))
                if key in seen:
                    raise Exception(
                        "duplicate key value violates unique index design_book_sections_current_code_key"
                    )
                seen.add(key)

    def execute(self):
        self.db.maybe_fail(f"{self.table_name}.{self._op[0]}")
        rows = self.db.tables.setdefault(self.table_name, [])
        # results are DEEP COPIES — real PostgREST returns detached dicts, so
        # service-held references must never alias the stored rows
        if self._op[0] == "insert":
            payload = dict(self._op[1])
            payload.setdefault("id", f"{self.table_name}-{self.db.next_id()}")
            payload.setdefault("created_at", "2026-07-09T00:00:00Z")
            if self.table_name == "design_book_sections":
                payload.setdefault("status", "current")
                self._enforce_partial_unique(rows + [payload])
            rows.append(payload)
            return _Result([copy.deepcopy(payload)])
        matched = [r for r in rows if self._match(r)]
        if self._op[0] == "update":
            for r in matched:
                r.update(copy.deepcopy(self._op[1]))
            if self.table_name == "design_book_sections":
                self._enforce_partial_unique(rows)
            return _Result([copy.deepcopy(r) for r in matched])
        if self._order:
            col, desc = self._order
            matched = sorted(matched, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._single:
            return _Result(copy.deepcopy(matched[0]) if matched else None)
        return _Result([copy.deepcopy(r) for r in matched])


class FakeBucket:
    def __init__(self, db):
        self.db = db

    def upload(self, path, data, file_options=None):
        self.db.maybe_fail(f"storage.upload:{path}")
        upsert = (file_options or {}).get("upsert") == "true"
        if path in self.db.storage_files and not upsert:
            raise Exception("The resource already exists")
        self.db.storage_files[path] = bytes(data)
        self.db.uploads.append(path)

    def remove(self, paths):
        for p in paths:
            self.db.storage_files.pop(p, None)

    def copy(self, src, dst):
        if dst in self.db.storage_files:
            raise Exception("The resource already exists")
        if src not in self.db.storage_files:
            raise Exception("Object not found")
        self.db.storage_files[dst] = self.db.storage_files[src]

    def download(self, path):
        return self.db.storage_files[path]

    def create_signed_url(self, path, _ttl):
        return {"signedURL": f"https://fake/{path}"}


class _FakeStorage:
    def __init__(self, db):
        self.db = db

    def from_(self, _bucket):
        return FakeBucket(self.db)


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list] = {}
        self.storage_files: dict[str, bytes] = {}
        self.uploads: list[str] = []
        self.fail_on: dict[str, int] = {}  # substring -> fail on Nth matching call
        self._id = 0
        self.storage = _FakeStorage(self)

    def next_id(self):
        self._id += 1
        return self._id

    def table(self, name):
        return FakeQuery(self, name)

    def maybe_fail(self, opname):
        for pattern in list(self.fail_on):
            if pattern in opname:
                self.fail_on[pattern] -= 1
                if self.fail_on[pattern] <= 0:
                    del self.fail_on[pattern]
                    raise RuntimeError(f"injected failure at {opname}")


# ============================================================================
# payload fixture (minimal valid book: spine + pkg + kit + ref + general)
# ============================================================================

def make_payload(pkg_qty=2, pkg_identity=None, pkg_code="I-SAW-1"):
    return {
        "meta": {"title": "Test Book", "product_item_number": "csa00010",
                 "template_project_code": None, "create": True,
                 "rebaseline": False, "expected_book_rev": None,
                 "allow_qty_mismatch": False},
        "sections": [
            {
                "section_code": "00-SPINE", "kind": "spine", "title": "MASTER CHECKLIST + TOC",
                "sort_order": 0, "identity": {"singleton": "spine"}, "display": None,
                "payload": {
                    "summary": {"totalHours": 10, "totalDays": 3, "packageCount": 1,
                                "fabParts": 1, "assemblies": 1, "purchased": 0},
                    "milestones": [], "checklist": [], "buyList": [], "stock": [],
                },
                "print_items": [], "no_print_expected": [],
            },
            {
                "section_code": pkg_code, "kind": "work_package", "title": "SAW",
                "sort_order": 100,
                "identity": pkg_identity or {"station_code": "010", "occurrence": 1},
                "display": {"day": 0},
                "payload": {
                    "stationName": "Saw", "stationAbbrev": "SAW", "estMin": 40,
                    "lines": [{"item_number": "csp00010", "displayNumber": "csp00010",
                               "name": "TUBE", "qty": pkg_qty, "estMin": 20,
                               "next": None, "feeds": ["II-CSA00030"], "source": None}],
                    "stockPull": [], "stageFor": ["II-CSA00030"],
                },
                "print_items": [], "no_print_expected": [],
            },
            {
                "section_code": "II-CSA00030", "kind": "assembly", "title": "LOWER FRAME -- CSA00030",
                "sort_order": 5000, "identity": {"item_number": "csa00030"},
                "display": {"startDay": 1, "endDay": 2},
                "payload": {
                    "item_number": "csa00030", "name": "LOWER FRAME", "qty": 1, "estMin": 120,
                    "parts": [{"rid": "P01", "item_number": "csp00010", "displayNumber": "csp00010",
                               "name": "TUBE", "qty": pkg_qty, "readyBy": pkg_code,
                               "readyDay": 0, "source": None}],
                    "weldSeq": [{"station": "Light Weld", "abbrev": "LW", "estMin": 120,
                                 "day": 1, "notes": None}],
                    "childAsms": [],
                },
                "print_items": [], "no_print_expected": [],
            },
            {
                "section_code": "II-REF", "kind": "design_reference", "title": "DESIGN REFERENCE",
                "sort_order": 9000, "identity": {"singleton": "design_reference"}, "display": None,
                "payload": {"docs": []}, "print_items": [], "no_print_expected": [],
            },
            {
                "section_code": "III-00", "kind": "general_reference", "title": "GENERAL REFERENCE",
                "sort_order": 9500, "identity": {"singleton": "general_reference", "index": 0},
                "display": None,
                "payload": {"template_version": 1, "notesPages": 1, "photoPages": 1},
                "print_items": [], "no_print_expected": [],
            },
        ],
    }


@pytest.fixture
def fake():
    db = FakeSupabase()
    with patch("app.services.master_design_book.get_supabase_admin", return_value=db):
        yield db


def sections_of(db, **filt):
    rows = db.tables.get("design_book_sections", [])
    return [r for r in rows if all(r.get(k) == v for k, v in filt.items())]


def book_of(db):
    return db.tables["design_books"][0]


# ============================================================================
# tests
# ============================================================================

class TestFirstPublish:
    def test_first_publish_rev1_no_notice(self, fake):
        result = update_master_book("test-book", make_payload())
        assert result["book_rev"] == 1 and result["previous_rev"] == 0
        assert len(result["added"]) == 5
        assert result["change_notice_path"] is None  # no holders yet
        assert book_of(fake)["book_rev"] == 1
        assert book_of(fake)["status"] == "current"
        assert len(sections_of(fake, status="current")) == 5
        assert "test-book/manifest.json" in fake.storage_files
        assert "test-book/00-spine.pdf" in fake.storage_files
        assert not any("changes/" in p for p in fake.storage_files)
        # change history row exists for issue 1
        ch = fake.tables["design_book_changes"][0]
        assert (ch["from_rev"], ch["to_rev"]) == (0, 1)

    def test_second_run_is_noop(self, fake):
        update_master_book("test-book", make_payload())
        uploads_before = len(fake.uploads)
        payload2 = make_payload()
        payload2["meta"]["create"] = False
        result = update_master_book("test-book", payload2)
        assert result["book_rev"] == 1 and result["previous_rev"] == 1
        assert not result["added"] and not result["changed"] and not result["retired"]
        assert len(fake.uploads) == uploads_before  # nothing re-uploaded

    def test_failed_first_gen_can_resume_with_create(self, fake):
        # crash mid-first-publish, retry with create:true must not 400
        fake.fail_on["storage.upload:test-book/ii-ref.pdf"] = 1
        with pytest.raises(RuntimeError):
            update_master_book("test-book", make_payload())
        assert book_of(fake)["book_rev"] == 0
        result = update_master_book("test-book", make_payload())  # create still true
        assert result["book_rev"] == 1
        assert len(sections_of(fake, status="current")) == 5


class TestIncremental:
    def test_change_revs_section_and_spine_and_issues_notice(self, fake):
        update_master_book("test-book", make_payload())
        payload2 = make_payload(pkg_qty=6)
        payload2["meta"]["create"] = False
        result = update_master_book("test-book", payload2)
        assert result["book_rev"] == 2
        changed_codes = {e["section_code"] for e in result["changed"]}
        # package + kit (its parts qty) + spine all rev
        assert {"I-SAW-1", "II-CSA00030", "00-SPINE"} <= changed_codes
        assert result["change_notice_path"] == "test-book/changes/CHANGE-NOTICE-rev002.pdf"
        assert result["change_notice_path"] in fake.storage_files
        pkg_row = sections_of(fake, section_code="I-SAW-1", status="current")[0]
        assert pkg_row["rev"] == "B"
        ref_row = sections_of(fake, section_code="II-REF", status="current")[0]
        assert ref_row["rev"] == "A"  # untouched

    def test_reasons_recorded_in_change_row(self, fake):
        update_master_book("test-book", make_payload())
        payload2 = make_payload(pkg_qty=6)
        payload2["meta"]["create"] = False
        update_master_book("test-book", payload2)
        ch = [c for c in fake.tables["design_book_changes"] if c["to_rev"] == 2][0]
        entry = next(e for e in ch["diff"] if e["section_code"] == "I-SAW-1")
        assert any("QTY csp00010 2->6" in r for r in entry["reasons"])


class TestCrashRecovery:
    def test_crash_before_book_rev_bump_resumes(self, fake):
        """Finding C1: sections committed, book_rev bump crashed -> resume."""
        update_master_book("test-book", make_payload())
        payload2 = make_payload(pkg_qty=6)
        payload2["meta"]["create"] = False
        fake.fail_on["design_books.update"] = 1  # step 11: the commit point
        with pytest.raises(RuntimeError):
            update_master_book("test-book", payload2)
        assert book_of(fake)["book_rev"] == 1  # bump never happened
        assert sections_of(fake, section_code="I-SAW-1", status="current")[0]["rev"] == "B"

        result = update_master_book("test-book", payload2)  # re-run converges
        assert result.get("resumed") is True
        assert result["book_rev"] == 2
        assert book_of(fake)["book_rev"] == 2
        assert "test-book/changes/CHANGE-NOTICE-rev002.pdf" in fake.storage_files
        # idempotent afterwards
        result3 = update_master_book("test-book", payload2)
        assert result3["book_rev"] == 2 and not result3.get("resumed")

    def test_crash_before_notice_row_update_resumes(self, fake):
        update_master_book("test-book", make_payload())
        payload2 = make_payload(pkg_qty=6)
        payload2["meta"]["create"] = False
        # first design_book_changes.update in run 2 is the write-ahead merge? no —
        # run 2 has no open row, so step 7 INSERTS; the first UPDATE is step 10
        fake.fail_on["design_book_changes.update"] = 1
        with pytest.raises(RuntimeError):
            update_master_book("test-book", payload2)
        assert book_of(fake)["book_rev"] == 1
        result = update_master_book("test-book", payload2)
        assert result.get("resumed") is True and result["book_rev"] == 2
        ch = [c for c in fake.tables["design_book_changes"] if c["to_rev"] == 2][0]
        assert ch["notice_storage_path"] == "test-book/changes/CHANGE-NOTICE-rev002.pdf"

    def test_crash_between_upload_and_row_update_converges(self, fake):
        """Invariant I2: storage may lead DB; re-run re-renders and converges."""
        update_master_book("test-book", make_payload())
        payload2 = make_payload(pkg_qty=6)
        payload2["meta"]["create"] = False
        fake.fail_on["design_book_sections.update"] = 1  # row commit of the changed pkg
        with pytest.raises(RuntimeError):
            update_master_book("test-book", payload2)
        assert sections_of(fake, section_code="I-SAW-1")[0]["rev"] == "A"  # row still old
        result = update_master_book("test-book", payload2)
        assert result["book_rev"] == 2
        assert sections_of(fake, section_code="I-SAW-1", status="current")[0]["rev"] == "B"
        # diff history merged, not lost
        ch = [c for c in fake.tables["design_book_changes"] if c["to_rev"] == 2][0]
        assert any(e["section_code"] == "I-SAW-1" for e in ch["diff"])

    def test_archive_never_clobbered_on_rerun(self, fake):
        """Finding M3: the rev-A archive must survive a crashed re-render."""
        update_master_book("test-book", make_payload())
        rev_a_bytes = fake.storage_files["test-book/i-saw-1.pdf"]
        payload2 = make_payload(pkg_qty=6)
        payload2["meta"]["create"] = False
        fake.fail_on["design_book_sections.update"] = 1  # crash AFTER upload
        with pytest.raises(RuntimeError):
            update_master_book("test-book", payload2)
        archive_path = "test-book/archive/i-saw-1-revA.pdf"
        assert fake.storage_files[archive_path] == rev_a_bytes
        update_master_book("test-book", payload2)  # re-run re-archives the live (rev-B) object
        assert fake.storage_files[archive_path] == rev_a_bytes  # NOT clobbered


class TestCodeAdoption:
    def test_new_identity_adopts_retired_code(self, fake):
        """Finding M4: retire + same-code add in one run must succeed."""
        update_master_book("test-book", make_payload())
        payload2 = make_payload(pkg_identity={"station_code": "020", "occurrence": 1})
        payload2["meta"]["create"] = False
        result = update_master_book("test-book", payload2)
        assert result["book_rev"] == 2
        rows = sections_of(fake, section_code="I-SAW-1")
        statuses = sorted(r["status"] for r in rows)
        assert statuses == ["current", "retired"]
        current = next(r for r in rows if r["status"] == "current")
        assert current["identity"] == {"station_code": "020", "occurrence": 1}
        assert current["rev"] == "A"
        retired = next(r for r in rows if r["status"] == "retired")
        assert retired["storage_path"] is None
        assert "test-book/i-saw-1.pdf" in fake.storage_files  # adopter's object live
