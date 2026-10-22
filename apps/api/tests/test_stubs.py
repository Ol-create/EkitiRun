"""Phase 0 stub endpoints return the shapes in docs/api-contract.md.

When a stub is replaced by a real implementation, move its checks into that
module's own tests and delete them here.
"""

import uuid

import pytest

from app.core.config import settings
from app.core.security import create_scanner_token
from app.modules.gps import service as gps_service
from app.stubs import race

API = "/api/v1"
ADMIN = {"Authorization": "Bearer dev-admin"}
PHONE = "+2348031234567"


# ---------------------------------------------------------------- runners


async def test_runner_search_by_bib_and_name(client):
    by_bib = (await client.get(f"{API}/runners/search", params={"q": "h0004"})).json()
    assert [r["bib_number"] for r in by_bib] == ["H0004"]

    name = race.runner_by_bib("H0004").last_name
    by_name = (await client.get(f"{API}/runners/search", params={"q": name.lower()})).json()
    assert 0 < len(by_name) <= 20
    assert set(by_name[0]) == {"bib_number", "full_name", "category_code"}

    short = await client.get(f"{API}/runners/search", params={"q": "a"})
    assert short.status_code == 422


async def test_runner_detail_is_public_safe(client):
    response = await client.get(f"{API}/runners/F0001")
    assert response.status_code == 200
    body = response.json()
    assert body["category"]["code"] == "FULL"
    assert body["status"] in {"registered", "started", "finished", "dnf"}
    for private in ("phone", "email", "date_of_birth", "emergency_contact_name"):
        assert private not in body

    missing = await client.get(f"{API}/runners/X9999")
    assert missing.status_code == 404
    assert missing.json()["code"] == "RUNNER_NOT_FOUND"


# ---------------------------------------------------------------- sponsors


async def test_sponsor_tiers(client):
    tiers = (await client.get(f"{API}/sponsor-tiers")).json()
    assert [t["name"] for t in tiers] == ["Platinum", "Gold", "Silver"]

    new = {"name": "Bronze", "amount_kobo": 10_000_000, "benefits": ["Thanks"], "sort_order": 4}
    assert (await client.post(f"{API}/admin/sponsor-tiers", json=new)).status_code == 401
    created = await client.post(f"{API}/admin/sponsor-tiers", json=new, headers=ADMIN)
    assert created.status_code == 201
    patched = await client.patch(
        f"{API}/admin/sponsor-tiers/2", json={"name": "Gold+"}, headers=ADMIN
    )
    assert patched.json()["name"] == "Gold+"
    deleted = await client.delete(f"{API}/admin/sponsor-tiers/3", headers=ADMIN)
    assert deleted.status_code == 204


@pytest.mark.parametrize(
    ("company", "status"),
    [("Acme Ltd", "paid"), ("Fail Foods", "failed"), ("Pending Plc", "pending")],
)
async def test_pledge_flow(client, company, status):
    pledge = {
        "tier_id": 2,
        "company_name": company,
        "contact_name": "Bola Ade",
        "email": "bola@example.com",
        "phone": PHONE,
    }
    created = await client.post(f"{API}/sponsors/pledges", json=pledge)
    assert created.status_code == 201
    ref = created.json()["reference"]
    assert created.json()["authorization_url"].endswith(f"reference={ref}")

    got = (await client.get(f"{API}/sponsors/pledges/{ref}")).json()
    assert got["status"] == status
    assert (got["receipt_pdf_url"] is not None) == (status == "paid")

    invoice = await client.get(
        created.json()["invoice_pdf_url"].removeprefix("http://localhost:8000")
    )
    assert invoice.headers["content-type"] == "application/pdf"
    assert invoice.content.startswith(b"%PDF")


async def test_pledge_needs_exactly_one_amount(client):
    base = {
        "company_name": "Acme",
        "contact_name": "Bola",
        "email": "b@example.com",
        "phone": PHONE,
    }
    both = await client.post(
        f"{API}/sponsors/pledges", json=base | {"tier_id": 1, "custom_amount_kobo": 2_000_000}
    )
    neither = await client.post(f"{API}/sponsors/pledges", json=base)
    too_small = await client.post(
        f"{API}/sponsors/pledges", json=base | {"custom_amount_kobo": 100}
    )
    assert both.status_code == neither.status_code == too_small.status_code == 422


# ---------------------------------------------------------------- race day


async def test_route(client):
    body = (await client.get(f"{API}/route", params={"category": "half"})).json()
    assert body["route"]["type"] == "LineString"
    assert abs(body["length_km"] - 21.0975) < 0.01
    names = [c["name"] for c in body["checkpoints"]]
    assert names[0] == "Start" and names[-1] == "Finish"
    assert (await client.get(f"{API}/route", params={"category": "NOPE"})).status_code == 404


async def test_results(client):
    body = (await client.get(f"{API}/results", params={"category": "10K", "limit": 5})).json()
    assert len(body["items"]) == 5
    assert body["total"] >= 5
    assert [i["position"] for i in body["items"]] == [1, 2, 3, 4, 5]
    women = (await client.get(f"{API}/results", params={"gender": "F"})).json()["items"]
    assert all(i["gender"] == "F" for i in women)


async def test_scan_batch(client):
    good, bad = str(uuid.uuid4()), str(uuid.uuid4())
    body = {
        "device_id": "phone-1",
        "checkpoint_id": 1,
        "scans": [
            {"client_id": good, "qr_token": "H0004", "scanned_at": "2027-03-01T07:10:00Z"},
            {"client_id": bad, "qr_token": "garbage", "scanned_at": "2027-03-01T07:10:01Z"},
        ],
    }
    headers = {"Authorization": f"Bearer {create_scanner_token('phone-1', 1)}"}
    response = await client.post(f"{API}/scans/batch", json=body, headers=headers)
    results = response.json()["results"]
    assert [r["status"] for r in results] == ["accepted", "invalid"]


# ---------------------------------------------------------------- GPS, trackers, kit


async def test_gps_ingest_needs_gateway_secret(client):
    body = {
        "positions": [
            {"device_id": "x", "lat": 7.6, "lng": 5.2, "recorded_at": "2027-03-01T07:00:00Z"}
        ]
    }
    assert (await client.post(f"{API}/gps/positions", json=body)).status_code == 401
    ok = await client.post(
        f"{API}/gps/positions", json=body, headers={"X-Gateway-Secret": settings.gateway_secret}
    )
    assert ok.status_code == 202
    assert ok.json() == {"accepted": 1}


async def test_positions_snapshot(client):
    body = (await client.get(f"{API}/positions", params={"category": "FULL"})).json()
    assert body["runners"]
    assert all(r["category_code"] == "FULL" for r in body["runners"])


async def test_position_stream(client):
    assert (await client.get(f"{API}/stream/positions", params={"bib": "X9999"})).status_code == 404
    runner = race.runner_by_bib("F0001")
    first = await anext(gps_service.position_events(runner))
    assert first.bib_number == "F0001"
    assert -90 <= first.lat <= 90


async def test_trackers_admin(client):
    assert (await client.get(f"{API}/admin/trackers")).status_code == 401
    lost = (
        await client.get(f"{API}/admin/trackers", params={"status": "lost"}, headers=ADMIN)
    ).json()
    assert [t["label"] for t in lost] == ["TRK-0040"]
    dup = await client.post(
        f"{API}/admin/trackers", json={"device_id": "new", "label": "TRK-0001"}, headers=ADMIN
    )
    assert dup.json()["code"] == "TRACKER_EXISTS"


async def test_kit_assign_and_return(client):
    free_runner = next(
        r.bib_number for r in race.runners() if r.has_tracker and r.bib_number.startswith("R")
    )
    ok = await client.post(
        f"{API}/kit/assign", json={"qr_token": free_runner, "tracker_label": "TRK-0031"}
    )
    assert ok.status_code == 200, ok.json()
    in_use = await client.post(
        f"{API}/kit/assign", json={"qr_token": free_runner, "tracker_label": "TRK-0040"}
    )
    assert in_use.json()["code"] == "TRACKER_IN_USE"
    returned = await client.post(f"{API}/kit/return", json={"tracker_label": "TRK-0001"})
    assert returned.status_code == 200
