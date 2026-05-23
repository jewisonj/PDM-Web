"""
Tests for Items API routes.

These tests mock the Supabase client to test API logic
without requiring a database connection.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestListItems:
    """Tests for GET /api/items endpoint."""

    def test_list_items_returns_items(self, client, sample_item):
        """Should return a list of items."""
        mock_result = MagicMock()
        mock_result.data = [
            {**sample_item, "projects": {"name": "Test Project"}}
        ]

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb
            mock_sb.table().select().or_().eq().eq().eq().order().range().execute.return_value = mock_result
            # Simpler chain without filters
            mock_sb.table().select().order().range().execute.return_value = mock_result

            response = client.get("/api/items")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_items_with_search_query(self, client, sample_item):
        """Should filter items by search query."""
        mock_result = MagicMock()
        mock_result.data = [{**sample_item, "projects": None}]

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb
            mock_sb.table().select().or_().order().range().execute.return_value = mock_result

            response = client.get("/api/items?q=stp00001")

        assert response.status_code == 200


class TestGetItem:
    """Tests for GET /api/items/{item_number} endpoint."""

    def test_get_item_success(self, client, sample_item, sample_file):
        """Should return item with files when found."""
        item_with_project = {**sample_item, "projects": {"name": "Test Project"}}

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            # Mock item query
            mock_item_result = MagicMock()
            mock_item_result.data = item_with_project
            mock_sb.table().select().eq().single().execute.return_value = mock_item_result

            # Mock files query
            mock_files_result = MagicMock()
            mock_files_result.data = [sample_file]
            mock_sb.table().select().eq().execute.return_value = mock_files_result

            response = client.get("/api/items/stp00001")

        assert response.status_code == 200
        data = response.json()
        assert data["item_number"] == "stp00001"
        assert "files" in data

    def test_get_item_not_found(self, client):
        """Should return 404 when item not found."""
        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb
            mock_sb.table().select().eq().single().execute.side_effect = Exception("Not found")

            response = client.get("/api/items/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestCreateItem:
    """Tests for POST /api/items endpoint."""

    def test_create_item_success(self, client, sample_item):
        """Should create and return new item."""
        new_item_data = {
            "item_number": "stp00002",
            "name": "New Test Part",
            "revision": "A"
        }

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            mock_result = MagicMock()
            mock_result.data = [{**sample_item, **new_item_data}]
            mock_sb.table().insert().execute.return_value = mock_result

            response = client.post("/api/items", json=new_item_data)

        assert response.status_code == 200
        data = response.json()
        assert data["item_number"] == "stp00002"

    def test_create_item_duplicate(self, client):
        """Should return 409 for duplicate item_number."""
        new_item_data = {
            "item_number": "stp00001",
            "name": "Duplicate Part"
        }

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb
            mock_sb.table().insert().execute.side_effect = Exception("duplicate key")

            response = client.post("/api/items", json=new_item_data)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_create_item_normalizes_item_number(self, client, sample_item):
        """Should lowercase item_number."""
        new_item_data = {
            "item_number": "STP00003",
            "name": "Uppercase Part",
            "revision": "A"
        }

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            mock_result = MagicMock()
            mock_result.data = [{**sample_item, "item_number": "stp00003"}]
            mock_sb.table().insert().execute.return_value = mock_result

            response = client.post("/api/items", json=new_item_data)

        assert response.status_code == 200
        # Verify the insert was called with lowercase
        insert_call = mock_sb.table().insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0] if insert_call[0] else insert_call[1].get('data', {})
            if isinstance(inserted_data, dict):
                assert inserted_data.get("item_number", "").islower()


class TestUpdateItem:
    """Tests for PATCH /api/items/{item_number} endpoint."""

    def test_update_item_success(self, client, sample_item):
        """Should update and return item."""
        update_data = {"name": "Updated Name"}

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            mock_result = MagicMock()
            mock_result.data = [{**sample_item, **update_data}]
            mock_sb.table().update().eq().execute.return_value = mock_result

            response = client.patch("/api/items/stp00001", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    def test_update_item_not_found(self, client):
        """Should return 404 when item not found."""
        update_data = {"name": "Updated Name"}

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            mock_result = MagicMock()
            mock_result.data = []  # Empty = not found
            mock_sb.table().update().eq().execute.return_value = mock_result

            response = client.patch("/api/items/nonexistent", json=update_data)

        assert response.status_code == 404

    def test_update_item_upsert_creates_new(self, client, sample_item):
        """Should create item when upsert=True and item doesn't exist."""
        update_data = {"name": "Upserted Part", "material": "A36"}

        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            # First update returns empty (not found)
            mock_update_result = MagicMock()
            mock_update_result.data = []
            mock_sb.table().update().eq().execute.return_value = mock_update_result

            # Insert creates new item
            mock_insert_result = MagicMock()
            mock_insert_result.data = [{
                **sample_item,
                "item_number": "stp00099",
                **update_data
            }]
            mock_sb.table().insert().execute.return_value = mock_insert_result

            response = client.patch("/api/items/stp00099?upsert=true", json=update_data)

        assert response.status_code == 200


class TestDeleteItem:
    """Tests for DELETE /api/items/{item_number} endpoint."""

    def test_delete_item_success(self, client, sample_item):
        """Should delete item and return success message."""
        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            mock_result = MagicMock()
            mock_result.data = [sample_item]
            mock_sb.table().delete().eq().execute.return_value = mock_result

            response = client.delete("/api/items/stp00001")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

    def test_delete_item_not_found(self, client):
        """Should return 404 when item not found."""
        with patch("app.routes.items.get_supabase_admin") as mock_get_sb:
            mock_sb = MagicMock()
            mock_get_sb.return_value = mock_sb

            mock_result = MagicMock()
            mock_result.data = []
            mock_sb.table().delete().eq().execute.return_value = mock_result

            response = client.delete("/api/items/nonexistent")

        assert response.status_code == 404
