"""Request-level smoke for ``GET /health``.

Exercises the real FastAPI routing stack through :class:`TestClient`, so
Pydantic serialisation, middleware (when later tasks add any), and the
response model declared on the route all run end-to-end — the template
every later backend endpoint test reuses.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_200_with_expected_shape(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "techscreen-backend"
    assert isinstance(body["version"], str)
    assert body["version"] != ""
