from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_me_sin_token_devuelve_401():
    response = client.get("/api/platform/me")
    assert response.status_code == 401  # HTTPBearer sin credenciales


def test_me_con_token_invalido_devuelve_401():
    response = client.get("/api/platform/me", headers={"Authorization": "Bearer token-invalido"})
    assert response.status_code == 401
