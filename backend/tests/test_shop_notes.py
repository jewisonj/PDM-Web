"""Shop Companion API tests (PIN login, token auth, BOM item split)."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.shop_auth import create_shop_token, decode_shop_token


def _settings(pin="1010"):
    s = MagicMock()
    s.supabase_service_key = "x" * 40
    s.shop_pin = pin
    return s


@pytest.fixture(autouse=True)
def fixed_settings():
    with patch("app.services.shop_auth.get_settings", return_value=_settings()):
        yield


def test_pin_login_ok(client):
    r = client.post("/api/shop-notes/login", json={"pin": "1010"})
    assert r.status_code == 200
    body = r.json()
    assert decode_shop_token(body["token"])["type"] == "shop"
    assert "expires_at" in body


def test_pin_login_wrong(client):
    r = client.post("/api/shop-notes/login", json={"pin": "0000"})
    assert r.status_code == 401


def test_pin_login_ignores_whitespace(client):
    r = client.post("/api/shop-notes/login", json={"pin": " 1010 "})
    assert r.status_code == 200


def test_worker_endpoints_require_token(client):
    assert client.get("/api/shop-notes/projects").status_code == 401
    assert client.get("/api/shop-notes/projects", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_reviewer_endpoints_reject_shop_token(client):
    """A shop device token must not be able to list/patch/delete notes."""
    token, _ = create_shop_token()
    h = {"Authorization": f"Bearer {token}"}
    with patch("app.routes.shop_notes._is_staff_token", return_value=False):
        assert client.get("/api/shop-notes", headers=h).status_code == 401
        assert client.get("/api/shop-notes/summary", headers=h).status_code == 401
        assert client.delete("/api/shop-notes/00000000-0000-0000-0000-000000000000", headers=h).status_code == 401


def test_create_note_requires_note_or_photo(client):
    token, _ = create_shop_token()
    r = client.post("/api/shop-notes", headers={"Authorization": f"Bearer {token}"}, data={"note": "   "})
    assert r.status_code == 400


def test_project_items_splits_assemblies_and_parts(client):
    """Assemblies = items with BOM children (plus top assembly); parts carry parent_ids."""
    token, _ = create_shop_token()
    h = {"Authorization": f"Bearer {token}"}

    top, weld, plate, bolt = "T", "W", "P", "B"

    supa = MagicMock()

    def table(name):
        t = MagicMock()
        chain = t.select.return_value
        for m in ("eq", "in_", "order", "limit"):
            getattr(chain, m).return_value = chain
        if name == "mrp_projects":
            chain.execute.return_value.data = [{"id": "proj", "project_code": "SPA0040", "top_assembly_id": top}]
        elif name == "mrp_project_parts":
            chain.execute.return_value.data = [
                {"item_id": weld, "quantity": 1, "items": {"id": weld, "item_number": "wma20120", "name": "Frame weldment"}},
                {"item_id": plate, "quantity": 2, "items": {"id": plate, "item_number": "csp0030", "name": "Side plate"}},
                {"item_id": bolt, "quantity": 8, "items": {"id": bolt, "item_number": "mmc12345", "name": "Bolt"}},
                {"item_id": "Z", "quantity": 1, "items": {"id": "Z", "item_number": "zzz00001", "name": "Reference"}},
            ]
        elif name == "items":
            chain.execute.return_value.data = [{"id": top, "item_number": "asm00100", "name": "Top"}]
        elif name == "bom":
            chain.execute.return_value.data = [
                {"parent_item_id": top, "child_item_id": weld},
                {"parent_item_id": weld, "child_item_id": plate},
                {"parent_item_id": top, "child_item_id": bolt},
            ]
        else:
            chain.execute.return_value.data = []
        return t

    supa.table.side_effect = table

    with patch("app.routes.shop_notes.get_supabase_admin", return_value=supa):
        r = client.get("/api/shop-notes/projects/00000000-0000-0000-0000-000000000000/items", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()
    asm_numbers = {a["item_number"]: a for a in body["assemblies"]}
    assert set(asm_numbers) == {"asm00100", "wma20120"}
    assert asm_numbers["asm00100"]["is_top"] is True

    parts = {p["item_number"]: p for p in body["parts"]}
    assert "zzz00001" not in parts
    assert parts["csp0030"]["parent_ids"] == [weld]
    assert parts["wma20120"]["parent_ids"] == [top]
    assert parts["mmc12345"]["parent_ids"] == [top]
    assert "asm00100" in parts  # top assembly is selectable as a part too
