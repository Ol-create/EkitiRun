import pytest

from app.core import security
from app.core.config import settings
from app.core.security import create_scanner_token
from scripts import create_admin
from scripts.create_admin import AdminError

LOGIN = "/api/v1/admin/auth/login"
ME = "/api/v1/admin/auth/me"
ADMIN_ONLY = "/api/v1/scanner/devices"  # any admin endpoint
PASSWORD = "correct horse battery staple"


@pytest.fixture
async def ada(session):
    return await create_admin.create(session, " Ada@EkitiRun.ng ", "Ada Okafor", PASSWORD)


async def sign_in(client, email="ada@ekitirun.ng", password=PASSWORD):
    return await client.post(LOGIN, json={"email": email, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_sign_in_and_use_admin_endpoints(db_client, ada):
    response = await sign_in(db_client, email="ADA@ekitirun.ng")

    assert response.status_code == 200
    body = response.json()
    assert body["admin"] == {"id": ada.id, "email": "ada@ekitirun.ng", "name": "Ada Okafor"}
    token = body["token"]
    assert (await db_client.get(ME, headers=bearer(token))).json()["email"] == "ada@ekitirun.ng"
    assert (await db_client.get(ADMIN_ONLY, headers=bearer(token))).status_code == 200


@pytest.mark.parametrize(
    ("email", "password"), [("ada@ekitirun.ng", "wrong password!"), ("bola@ekitirun.ng", PASSWORD)]
)
async def test_wrong_password_and_unknown_email_look_the_same(db_client, ada, email, password):
    response = await sign_in(db_client, email, password)

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Email or password is not correct.",
        "code": "LOGIN_INVALID",
    }


async def test_failed_sign_ins_are_limited_per_email(db_client, ada):
    for _ in range(5):
        await sign_in(db_client, password="wrong password!")

    blocked = await sign_in(db_client)  # even the right password waits now

    assert blocked.json()["code"] == "LOGIN_RATE_LIMITED"


async def test_failed_sign_ins_are_limited_per_ip(db_client, ada):
    for n in range(10):
        await sign_in(db_client, email=f"guess{n}@ekitirun.ng")

    assert (await sign_in(db_client)).json()["code"] == "LOGIN_RATE_LIMITED"


async def test_a_successful_sign_in_clears_earlier_failures(db_client, ada):
    for _ in range(4):
        await sign_in(db_client, password="wrong password!")
    assert (await sign_in(db_client)).status_code == 200

    for _ in range(4):
        await sign_in(db_client, password="wrong password!")
    assert (await sign_in(db_client)).status_code == 200


@pytest.mark.parametrize("action", ["sign_out", "deactivate", "reset_password"])
async def test_ending_sessions(db_client, session, ada, action):
    token = (await sign_in(db_client)).json()["token"]

    if action == "sign_out":
        await create_admin.sign_out(session, ada.email)
    elif action == "deactivate":
        await create_admin.set_active(session, ada.email, False)
    else:
        await create_admin.reset_password(session, ada.email, "a brand new long password")

    response = await db_client.get(ADMIN_ONLY, headers=bearer(token))
    assert (response.status_code, response.json()["code"]) == (401, "ADMIN_AUTH_REQUIRED")
    again = await sign_in(db_client)
    assert again.status_code == (200 if action == "sign_out" else 401)


async def test_new_password_works_after_a_reset(db_client, session, ada):
    await create_admin.reset_password(session, ada.email, "a brand new long password")

    assert (await sign_in(db_client, password="a brand new long password")).status_code == 200


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer not-a-token",
        f"Bearer {create_scanner_token('phone', 1)}",  # another kind of token
        f"Bearer {security.create_admin_token(999_999, 1)}",  # an admin that doesn't exist
    ],
)
async def test_bad_admin_tokens(db_client, authorization):
    headers = {"Authorization": authorization} if authorization else {}

    response = await db_client.get(ADMIN_ONLY, headers=headers)

    assert (response.status_code, response.json()["code"]) == (401, "ADMIN_AUTH_REQUIRED")


async def test_production_refuses_the_dev_token_but_not_real_logins(db_client, ada, monkeypatch):
    token = (await sign_in(db_client)).json()["token"]
    monkeypatch.setattr(settings, "environment", "production")

    dev = await db_client.get(ADMIN_ONLY, headers=bearer(settings.admin_dev_token))
    real = await db_client.get(ADMIN_ONLY, headers=bearer(token))

    assert dev.status_code == 401
    assert real.status_code == 200


async def test_dev_token_still_works_in_development(db_client):
    assert (await db_client.get(ADMIN_ONLY, headers=bearer("dev-admin"))).status_code == 200
    assert (await db_client.get(ME, headers=bearer("dev-admin"))).json()["code"] == "DEV_TOKEN"


async def test_account_rules(session, ada):
    with pytest.raises(AdminError, match="already has an account"):
        await create_admin.create(session, "ada@ekitirun.ng", "Ada again", PASSWORD)
    with pytest.raises(AdminError, match="at least 12"):
        await create_admin.create(session, "bola@ekitirun.ng", "Bola", "short")
    with pytest.raises(AdminError, match="No admin"):
        await create_admin.sign_out(session, "nobody@ekitirun.ng")


def test_password_hashing():
    first = security.hash_password(PASSWORD)
    second = security.hash_password(PASSWORD)

    assert first != second  # a fresh salt each time
    assert first.startswith("scrypt$") and PASSWORD not in first
    assert security.verify_password(PASSWORD, first)
    assert not security.verify_password(PASSWORD + "!", first)
    assert not security.verify_password(PASSWORD, "not a hash")
