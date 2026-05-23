"""
Pytest fixtures for backend tests.

These tests use mocked Supabase clients to avoid requiring
a real database connection during CI.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_supabase():
    """
    Create a mock Supabase client for testing.

    Returns a MagicMock that can be configured per-test.
    """
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_supabase_admin(mock_supabase):
    """
    Patch get_supabase_admin to return a mock client.

    Usage:
        def test_something(client, mock_supabase_admin, mock_supabase):
            mock_supabase.table().select().execute.return_value.data = [...]
            response = client.get("/api/items")
    """
    with patch("app.services.supabase.get_supabase_admin", return_value=mock_supabase):
        yield mock_supabase


# Sample test data fixtures
@pytest.fixture
def sample_item():
    """Sample item data for testing."""
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "item_number": "stp00001",
        "name": "Test Part",
        "revision": "A",
        "iteration": 1,
        "lifecycle_state": "Design",
        "material": "A36",
        "thickness": 0.25,
        "mass": 1.5,
        "is_supplier_part": False,
        "project_id": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_file():
    """Sample file data for testing."""
    return {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "item_id": "550e8400-e29b-41d4-a716-446655440000",
        "file_type": "STEP",
        "file_name": "stp00001.step",
        "file_path": "pdm-files/stp00001/stp00001.step",
        "file_size": 12345,
        "revision": "A",
        "iteration": 1,
        "created_at": "2024-01-01T00:00:00Z"
    }
