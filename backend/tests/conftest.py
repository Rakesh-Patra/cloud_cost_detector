import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set mock environment variables before importing app
os.environ["GEMINI_API_KEY"] = "mock-gemini-key"
os.environ["INSFORGE_PROJECT_URL"] = "https://mock.insforge.app"
os.environ["INSFORGE_ANON_KEY"] = "mock-anon-key"
os.environ["DB_PATH"] = ":memory:" # Use in-memory SQLite for testing

from main import app, get_current_user
import database

@pytest.fixture(autouse=True)
def init_in_memory_db():
    # Automatically initialize in-memory SQLite tables for every test
    database.init_db()
    yield

@pytest.fixture
def client():
    # Override authentication dependency
    app.dependency_overrides[get_current_user] = lambda: {
        "user": {"id": "test-user-id", "email": "test@example.com"},
        "token": "mock-jwt-token"
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
