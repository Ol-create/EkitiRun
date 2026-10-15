async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_errors_use_contract_shape(client):
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "HTTP_404"}


async def test_validation_errors_use_contract_shape(client):
    response = await client.post("/api/v1/auth/otp/request", json={"phone": "08031234567"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"].startswith("phone:")
    assert body["errors"][0]["loc"] == ["body", "phone"]
