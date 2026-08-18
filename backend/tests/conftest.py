import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MOCK_MODE", "true")
os.environ.setdefault("WORKFLOW_STORE_PATH", "./data/test-workflows.json")
# Keep the suite hermetic: don't let a developer's real LLM_API_KEY (loaded
# from backend/.env) make live planning calls during tests.
os.environ.setdefault("LLM_API_KEY", "")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
