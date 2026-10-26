from fastapi.testclient import TestClient

from app.core.deps import require_admin
from app.main import app


async def mock_require_admin():
    pass


def test_health_endpoint():
    app.dependency_overrides[require_admin] = mock_require_admin

    try:
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()
